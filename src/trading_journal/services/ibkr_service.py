"""IBKR service for fetching executions and Greeks data."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

from ib_insync import IB, Fill

from trading_journal.config import get_settings

settings = get_settings()


def _sync_ibkr_operation(host: str, port: int, client_id: int, operation_func):
    """
    Run an IBKR operation with its own event loop.

    This function creates a new event loop, connects to IBKR,
    runs the operation, disconnects, and cleans up.
    """
    loop = None
    ib = None
    try:
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Create IB instance and connect
        ib = IB()
        loop.run_until_complete(ib.connectAsync(host, port, clientId=client_id))

        # Run the operation
        result = operation_func(ib)

        return result
    except Exception as e:
        raise ConnectionError(f"Failed to connect to IBKR: {e}")
    finally:
        # Cleanup
        if ib and ib.isConnected():
            ib.disconnect()
        if loop:
            loop.close()


class IBKRService:
    """Service for interacting with Interactive Brokers API."""

    def __init__(self):
        """Initialize IBKR service."""
        self.ib = IB()
        self.connected = False

    async def connect(
        self,
        host: str | None = None,
        port: int | None = None,
        client_id: int | None = None,
    ) -> bool:
        """Connect to IBKR TWS/Gateway.

        Args:
            host: IBKR host (defaults to config)
            port: IBKR port (defaults to config)
            client_id: Client ID (defaults to config)

        Returns:
            True if connected successfully

        Raises:
            ConnectionError: If connection fails
        """
        host = host or settings.ibkr_host
        port = port or settings.ibkr_port
        client_id = client_id or settings.ibkr_client_id

        def connect_op(ib):
            self.ib = ib
            self.connected = True
            return True

        # Run in executor with its own event loop
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, _sync_ibkr_operation, host, port, client_id, connect_op
        )

    async def disconnect(self) -> None:
        """Disconnect from IBKR."""
        if self.connected:
            self.ib.disconnect()
            self.connected = False

    async def fetch_executions(
        self,
        days_back: int = 7,
    ) -> list[dict]:
        """Fetch executions from IBKR.

        Args:
            days_back: Number of days to look back (default: 7)

        Returns:
            List of execution dictionaries

        Raises:
            ConnectionError: If not connected to IBKR
        """
        if not self.connected:
            raise ConnectionError("Not connected to IBKR. Call connect() first.")

        executions = []

        # Request fills (combines execution + commission data)
        fills = await self.ib.reqExecutionsAsync()

        for fill in fills:
            exec_dict = self._parse_fill(fill)
            if exec_dict:
                executions.append(exec_dict)

        return executions

    def _parse_fill(self, fill: Fill) -> dict | None:
        """Parse IBKR Fill object into dict.

        Args:
            fill: IBKR Fill object

        Returns:
            Execution dictionary or None if invalid
        """
        try:
            execution = fill.execution
            contract = fill.contract
            commission_report = fill.commissionReport

            # Base execution data
            exec_data = {
                "exec_id": execution.execId,
                "order_id": execution.orderId,
                "perm_id": execution.permId,
                "execution_time": datetime.strptime(
                    execution.time, "%Y%m%d %H:%M:%S"
                ).replace(tzinfo=UTC),
                "underlying": contract.symbol,
                "security_type": contract.secType,
                "exchange": execution.exchange,
                "currency": contract.currency or "USD",
                "side": execution.side,
                "quantity": Decimal(str(execution.shares)),
                "price": Decimal(str(execution.price)),
                "account_id": execution.acctNumber,
            }

            # Option-specific fields
            if contract.secType == "OPT":
                exec_data.update(
                    {
                        "option_type": contract.right,  # C or P
                        "strike": Decimal(str(contract.strike)),
                        "expiration": datetime.strptime(
                            contract.lastTradeDateOrContractMonth, "%Y%m%d"
                        ).replace(tzinfo=UTC),
                        "multiplier": int(contract.multiplier or 100),
                    }
                )
            else:
                exec_data.update(
                    {
                        "option_type": None,
                        "strike": None,
                        "expiration": None,
                        "multiplier": None,
                    }
                )

            # Commission data
            if commission_report:
                exec_data["commission"] = Decimal(str(commission_report.commission))
            else:
                exec_data["commission"] = Decimal("0.00")

            # Calculate net amount (price * quantity * multiplier)
            multiplier = exec_data.get("multiplier") or 1
            net_amount = exec_data["price"] * exec_data["quantity"] * multiplier

            # Adjust for buy vs sell
            if exec_data["side"] == "BOT":
                net_amount = -net_amount  # Money out for buys
            else:
                net_amount = net_amount  # Money in for sells

            exec_data["net_amount"] = net_amount

            return exec_data

        except Exception as e:
            # Log error but don't crash
            print(f"Error parsing fill: {e}")
            return None

    async def fetch_greeks_for_position(
        self,
        underlying: str,
        option_type: str,
        strike: Decimal,
        expiration: datetime,
    ) -> dict | None:
        """Fetch Greeks for a specific option position.

        Args:
            underlying: Underlying symbol
            option_type: 'C' for call, 'P' for put
            strike: Strike price
            expiration: Expiration date

        Returns:
            Greeks dictionary or None if unavailable
        """
        if not self.connected:
            raise ConnectionError("Not connected to IBKR. Call connect() first.")

        from ib_insync import Option

        # Create option contract
        contract = Option(
            symbol=underlying,
            lastTradeDateOrContractMonth=expiration.strftime("%Y%m%d"),
            strike=float(strike),
            right=option_type,
            exchange="SMART",
            currency="USD",
        )

        # Request market data with Greeks
        self.ib.reqMktData(contract, genericTickList="106", snapshot=False)

        # Wait for ticker to update (ib-insync handles this async)
        await asyncio.sleep(2)

        # Get ticker
        ticker = self.ib.ticker(contract)

        # Cancel market data subscription
        self.ib.cancelMktData(contract)

        if ticker and hasattr(ticker, "modelGreeks") and ticker.modelGreeks:
            greeks = ticker.modelGreeks

            # Extract Greeks data
            greeks_dict = {
                "delta": Decimal(str(greeks.delta)) if greeks.delta and greeks.delta > -9e37 else None,
                "gamma": Decimal(str(greeks.gamma)) if greeks.gamma and greeks.gamma > -9e37 else None,
                "theta": Decimal(str(greeks.theta)) if greeks.theta and greeks.theta > -9e37 else None,
                "vega": Decimal(str(greeks.vega)) if greeks.vega and greeks.vega > -9e37 else None,
                "implied_volatility": Decimal(str(greeks.impliedVol)) if greeks.impliedVol and greeks.impliedVol > -9e37 else None,
                "underlying_price": Decimal(str(greeks.undPrice)) if greeks.undPrice and greeks.undPrice > 0 else None,
                "option_price": Decimal(str(ticker.marketPrice())) if ticker.marketPrice() else None,
            }

            return greeks_dict

        return None

    async def fetch_all_position_greeks(self) -> list[dict]:
        """Fetch Greeks for all open option positions.

        Returns:
            List of dictionaries with position and Greeks data
        """
        if not self.connected:
            raise ConnectionError("Not connected to IBKR. Call connect() first.")

        positions_with_greeks = []

        # Get all positions
        positions = self.ib.positions()

        for position in positions:
            contract = position.contract

            # Only process option positions
            if contract.secType != "OPT":
                continue

            # Fetch Greeks for this position
            expiration = datetime.strptime(contract.lastTradeDateOrContractMonth, "%Y%m%d")

            greeks = await self.fetch_greeks_for_position(
                underlying=contract.symbol,
                option_type=contract.right,
                strike=Decimal(str(contract.strike)),
                expiration=expiration,
            )

            if greeks:
                positions_with_greeks.append({
                    "underlying": contract.symbol,
                    "option_type": contract.right,
                    "strike": Decimal(str(contract.strike)),
                    "expiration": expiration,
                    "quantity": int(position.position),
                    "avg_cost": Decimal(str(position.avgCost)),
                    "greeks": greeks,
                })

        return positions_with_greeks

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self.connected:
            self.ib.disconnect()

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()
