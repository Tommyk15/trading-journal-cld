"""IBKR Worker Process - Runs IBKR connection in a separate process.

This solves the event loop conflict between ib_insync and uvicorn by running
the IBKR connection in its own process with its own event loop.

Communication happens via multiprocessing Queues.
"""

import asyncio
import logging
import multiprocessing as mp
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from queue import Empty
from typing import Any

# Note: ib_insync imports are done inside the worker process to avoid
# importing util.patchAsyncio() in the main process which conflicts with uvloop

logger = logging.getLogger(__name__)


class RequestType(Enum):
    """Types of requests the worker can handle."""

    CONNECT = "connect"
    DISCONNECT = "disconnect"
    STOCK_QUOTE = "stock_quote"
    OPTION_DATA = "option_data"
    PORTFOLIO = "portfolio"
    ACCOUNT_PNL = "account_pnl"
    FETCH_EXECUTIONS = "fetch_executions"
    SHUTDOWN = "shutdown"
    PING = "ping"


@dataclass
class WorkerRequest:
    """Request to the IBKR worker."""

    request_id: str
    request_type: RequestType
    params: dict


@dataclass
class WorkerResponse:
    """Response from the IBKR worker."""

    request_id: str
    success: bool
    data: Any = None
    error: str | None = None


class IBKRWorker:
    """Worker that runs IBKR connection in a separate process."""

    def __init__(
        self,
        request_queue: mp.Queue,
        response_queue: mp.Queue,
        host: str = "127.0.0.1",
        port: int = 7496,
        client_id: int = 50,
    ):
        """Initialize worker.

        Args:
            request_queue: Queue to receive requests from main process
            response_queue: Queue to send responses to main process
            host: IBKR TWS/Gateway host
            port: IBKR TWS/Gateway port (7496=live, 7497=paper)
            client_id: Client ID for IBKR connection
        """
        self.request_queue = request_queue
        self.response_queue = response_queue
        self.host = host
        self.port = port
        self.client_id = client_id
        self.ib = None  # Will be set after importing ib_insync
        self.connected = False
        self._running = True
        self._IB = None  # IB class reference
        self._Stock = None  # Stock class reference
        self._Option = None  # Option class reference

    def _import_ib_insync(self):
        """Import ib_insync in the worker process."""
        if self._IB is None:
            from ib_insync import IB, Option, Stock, util
            util.patchAsyncio()  # Safe in separate process
            self._IB = IB
            self._Stock = Stock
            self._Option = Option

    async def connect(self) -> bool:
        """Connect to IBKR."""
        self._import_ib_insync()

        if self.connected and self.ib and self.ib.isConnected():
            return True

        try:
            self.ib = self._IB()
            await self.ib.connectAsync(
                self.host,
                self.port,
                clientId=self.client_id,
            )
            self.connected = True
            logger.info(f"IBKR Worker connected to {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"IBKR Worker connection failed: {e}")
            self.connected = False
            return False

    async def disconnect(self) -> None:
        """Disconnect from IBKR."""
        if self.ib and self.ib.isConnected():
            self.ib.disconnect()
        self.connected = False
        logger.info("IBKR Worker disconnected")

    async def get_stock_quote(self, symbol: str) -> dict | None:
        """Get stock quote from IBKR."""
        if not self.connected or not self.ib:
            return None

        try:
            contract = self._Stock(symbol, "SMART", "USD")
            self.ib.qualifyContracts(contract)

            ticker = self.ib.reqMktData(contract, "", False, False)
            await asyncio.sleep(2)  # Wait for data

            result = {
                "symbol": symbol,
                "bid": float(ticker.bid) if ticker.bid and ticker.bid > 0 else None,
                "ask": float(ticker.ask) if ticker.ask and ticker.ask > 0 else None,
                "last": float(ticker.last) if ticker.last and ticker.last > 0 else None,
                "close": float(ticker.close) if ticker.close and ticker.close > 0 else None,
                "volume": ticker.volume if ticker.volume and ticker.volume > 0 else None,
            }

            # Calculate price (prefer last, then mid, then close)
            if result["last"]:
                result["price"] = result["last"]
            elif result["bid"] and result["ask"]:
                result["price"] = (result["bid"] + result["ask"]) / 2
            elif result["close"]:
                result["price"] = result["close"]
            else:
                result["price"] = None

            self.ib.cancelMktData(contract)
            return result

        except Exception as e:
            logger.error(f"Error getting stock quote for {symbol}: {e}")
            return None

    async def get_option_data(
        self,
        underlying: str,
        expiration: str,  # YYYYMMDD format
        strike: float,
        option_type: str,  # "C" or "P"
    ) -> dict | None:
        """Get option quote and Greeks from IBKR."""
        if not self.connected or not self.ib:
            return None

        try:
            # Parse expiration
            exp_date = datetime.strptime(expiration, "%Y%m%d").strftime("%Y%m%d")

            contract = self._Option(
                underlying,
                exp_date,
                strike,
                option_type,
                "SMART",
                multiplier=100,
                currency="USD",
            )
            self.ib.qualifyContracts(contract)

            ticker = self.ib.reqMktData(contract, "", False, False)
            await asyncio.sleep(2)  # Wait for data

            result = {
                "symbol": contract.localSymbol or f"{underlying}{expiration}{option_type}{strike}",
                "underlying": underlying,
                "strike": strike,
                "expiration": expiration,
                "option_type": option_type,
                "bid": float(ticker.bid) if ticker.bid and ticker.bid > 0 else None,
                "ask": float(ticker.ask) if ticker.ask and ticker.ask > 0 else None,
                "last": float(ticker.last) if ticker.last and ticker.last > 0 else None,
                "volume": ticker.volume if ticker.volume and ticker.volume > 0 else None,
                "open_interest": ticker.openInterest if hasattr(ticker, "openInterest") else None,
            }

            # Calculate mid price
            if result["bid"] and result["ask"]:
                result["mid"] = (result["bid"] + result["ask"]) / 2
            else:
                result["mid"] = result["last"]

            # Get Greeks from model
            greeks = {}
            if ticker.modelGreeks:
                mg = ticker.modelGreeks
                greeks = {
                    "delta": float(mg.delta) if mg.delta else None,
                    "gamma": float(mg.gamma) if mg.gamma else None,
                    "theta": float(mg.theta) if mg.theta else None,
                    "vega": float(mg.vega) if mg.vega else None,
                    "iv": float(mg.impliedVol) if mg.impliedVol else None,
                }
            result["greeks"] = greeks

            self.ib.cancelMktData(contract)
            return result

        except Exception as e:
            logger.error(f"Error getting option data: {e}")
            return None

    async def get_portfolio(self) -> list[dict]:
        """Get portfolio positions from IBKR."""
        if not self.connected or not self.ib:
            return []

        try:
            positions = self.ib.portfolio()
            result = []

            for pos in positions:
                contract = pos.contract
                result.append({
                    "symbol": contract.localSymbol or contract.symbol,
                    "underlying": contract.symbol,
                    "security_type": contract.secType,
                    "strike": float(contract.strike) if contract.strike else None,
                    "expiration": contract.lastTradeDateOrContractMonth,
                    "option_type": contract.right if contract.right else None,
                    "position": int(pos.position),
                    "market_price": float(pos.marketPrice) if pos.marketPrice else None,
                    "market_value": float(pos.marketValue),
                    "avg_cost": float(pos.averageCost),
                    "unrealized_pnl": float(pos.unrealizedPNL),
                    "realized_pnl": float(pos.realizedPNL),
                })

            return result

        except Exception as e:
            logger.error(f"Error getting portfolio: {e}")
            return []

    async def get_account_pnl(self) -> dict | None:
        """Get account P&L from IBKR."""
        if not self.connected or not self.ib:
            return None

        try:
            # Get account summary
            summary = self.ib.accountSummary()
            pnl_data = {}

            for item in summary:
                if item.tag == "UnrealizedPnL":
                    pnl_data["unrealized_pnl"] = float(item.value)
                elif item.tag == "RealizedPnL":
                    pnl_data["realized_pnl"] = float(item.value)

            # Request P&L
            pnl = self.ib.reqPnL(self.ib.managedAccounts()[0])
            await asyncio.sleep(1)

            if pnl:
                pnl_data["daily_pnl"] = float(pnl.dailyPnL) if pnl.dailyPnL else None
                pnl_data["unrealized_pnl"] = float(pnl.unrealizedPnL) if pnl.unrealizedPnL else pnl_data.get("unrealized_pnl")
                pnl_data["realized_pnl"] = float(pnl.realizedPnL) if pnl.realizedPnL else pnl_data.get("realized_pnl")
                pnl_data["account"] = self.ib.managedAccounts()[0] if self.ib.managedAccounts() else None

            return pnl_data

        except Exception as e:
            logger.error(f"Error getting account P&L: {e}")
            return None

    async def fetch_executions(self) -> list[dict]:
        """Fetch executions from IBKR."""
        if not self.connected or not self.ib:
            return []

        try:
            fills = await self.ib.reqExecutionsAsync()
            executions = []

            for fill in fills:
                exec_dict = self._parse_fill(fill)
                if exec_dict:
                    executions.append(exec_dict)

            return executions

        except Exception as e:
            logger.error(f"Error fetching executions: {e}")
            return []

    def _parse_fill(self, fill) -> dict | None:
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

            # Parse execution time
            exec_time = datetime.strptime(execution.time, "%Y%m%d %H:%M:%S")

            # Base execution data
            exec_data = {
                "exec_id": execution.execId,
                "order_id": execution.orderId,
                "perm_id": execution.permId,
                "execution_time": exec_time.isoformat(),
                "underlying": contract.symbol,
                "security_type": contract.secType,
                "exchange": execution.exchange,
                "currency": contract.currency or "USD",
                "side": execution.side,
                "quantity": float(execution.shares),
                "price": float(execution.price),
                "account_id": execution.acctNumber,
            }

            # Option-specific fields
            if contract.secType == "OPT":
                exp_date = datetime.strptime(
                    contract.lastTradeDateOrContractMonth, "%Y%m%d"
                )
                exec_data.update({
                    "option_type": contract.right,  # C or P
                    "strike": float(contract.strike),
                    "expiration": exp_date.isoformat(),
                    "multiplier": int(contract.multiplier or 100),
                })
            else:
                exec_data.update({
                    "option_type": None,
                    "strike": None,
                    "expiration": None,
                    "multiplier": None,
                })

            # Commission data
            if commission_report:
                exec_data["commission"] = float(commission_report.commission)
            else:
                exec_data["commission"] = 0.0

            # Calculate net amount (price * quantity * multiplier)
            multiplier = exec_data.get("multiplier") or 1
            net_amount = exec_data["price"] * exec_data["quantity"] * multiplier

            # Adjust for buy vs sell
            if exec_data["side"] == "BOT":
                net_amount = -net_amount  # Money out for buys

            exec_data["net_amount"] = net_amount

            return exec_data

        except Exception as e:
            logger.error(f"Error parsing fill: {e}")
            return None

    async def handle_request(self, request: WorkerRequest) -> WorkerResponse:
        """Handle a request from the main process."""
        try:
            if request.request_type == RequestType.PING:
                return WorkerResponse(
                    request_id=request.request_id,
                    success=True,
                    data={"connected": self.connected, "timestamp": datetime.now().isoformat()},
                )

            elif request.request_type == RequestType.CONNECT:
                success = await self.connect()
                return WorkerResponse(
                    request_id=request.request_id,
                    success=success,
                    data={"connected": success},
                )

            elif request.request_type == RequestType.DISCONNECT:
                await self.disconnect()
                return WorkerResponse(
                    request_id=request.request_id,
                    success=True,
                    data={"connected": False},
                )

            elif request.request_type == RequestType.STOCK_QUOTE:
                data = await self.get_stock_quote(request.params["symbol"])
                return WorkerResponse(
                    request_id=request.request_id,
                    success=data is not None,
                    data=data,
                    error="No data available" if data is None else None,
                )

            elif request.request_type == RequestType.OPTION_DATA:
                data = await self.get_option_data(
                    underlying=request.params["underlying"],
                    expiration=request.params["expiration"],
                    strike=request.params["strike"],
                    option_type=request.params["option_type"],
                )
                return WorkerResponse(
                    request_id=request.request_id,
                    success=data is not None,
                    data=data,
                    error="No data available" if data is None else None,
                )

            elif request.request_type == RequestType.PORTFOLIO:
                data = await self.get_portfolio()
                return WorkerResponse(
                    request_id=request.request_id,
                    success=True,
                    data=data,
                )

            elif request.request_type == RequestType.ACCOUNT_PNL:
                data = await self.get_account_pnl()
                return WorkerResponse(
                    request_id=request.request_id,
                    success=data is not None,
                    data=data,
                    error="No data available" if data is None else None,
                )

            elif request.request_type == RequestType.FETCH_EXECUTIONS:
                data = await self.fetch_executions()
                return WorkerResponse(
                    request_id=request.request_id,
                    success=True,
                    data=data,
                )

            elif request.request_type == RequestType.SHUTDOWN:
                self._running = False
                await self.disconnect()
                return WorkerResponse(
                    request_id=request.request_id,
                    success=True,
                    data={"shutdown": True},
                )

            else:
                return WorkerResponse(
                    request_id=request.request_id,
                    success=False,
                    error=f"Unknown request type: {request.request_type}",
                )

        except Exception as e:
            logger.error(f"Error handling request {request.request_id}: {e}")
            return WorkerResponse(
                request_id=request.request_id,
                success=False,
                error=str(e),
            )

    async def run(self) -> None:
        """Main worker loop."""
        logger.info("IBKR Worker starting...")

        # Try to connect on startup
        await self.connect()

        while self._running:
            try:
                # Check for requests (non-blocking with timeout)
                try:
                    request_data = self.request_queue.get(timeout=0.1)
                    # Convert request_type string back to enum
                    request_data["request_type"] = RequestType(request_data["request_type"])
                    request = WorkerRequest(**request_data)
                    response = await self.handle_request(request)
                    self.response_queue.put({
                        "request_id": response.request_id,
                        "success": response.success,
                        "data": response.data,
                        "error": response.error,
                    })
                except Empty:
                    pass

                # Keep connection alive
                if self.ib and self.connected:
                    self.ib.sleep(0)  # Process IB events

                await asyncio.sleep(0.01)  # Small delay to prevent busy loop

            except Exception as e:
                logger.error(f"Worker loop error: {e}")
                await asyncio.sleep(1)

        logger.info("IBKR Worker stopped")


def run_worker(
    request_queue: mp.Queue,
    response_queue: mp.Queue,
    host: str,
    port: int,
    client_id: int,
) -> None:
    """Entry point for the worker process."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    worker = IBKRWorker(
        request_queue=request_queue,
        response_queue=response_queue,
        host=host,
        port=port,
        client_id=client_id,
    )

    asyncio.run(worker.run())


class IBKRWorkerClient:
    """Client for communicating with the IBKR worker process."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7496,
        client_id: int = 50,
    ):
        """Initialize client.

        Args:
            host: IBKR TWS/Gateway host
            port: IBKR TWS/Gateway port
            client_id: Client ID for IBKR connection
        """
        self.host = host
        self.port = port
        self.client_id = client_id
        self.request_queue: mp.Queue | None = None
        self.response_queue: mp.Queue | None = None
        self.process: mp.Process | None = None
        self._request_counter = 0
        self._pending_responses: dict[str, Any] = {}

    def start(self) -> bool:
        """Start the worker process."""
        if self.process and self.process.is_alive():
            return True

        try:
            self.request_queue = mp.Queue()
            self.response_queue = mp.Queue()

            self.process = mp.Process(
                target=run_worker,
                args=(
                    self.request_queue,
                    self.response_queue,
                    self.host,
                    self.port,
                    self.client_id,
                ),
                daemon=True,
            )
            self.process.start()
            logger.info("IBKR Worker process started")
            return True

        except Exception as e:
            logger.error(f"Failed to start IBKR Worker: {e}")
            return False

    def stop(self) -> None:
        """Stop the worker process."""
        if self.process and self.process.is_alive():
            try:
                self._send_request(RequestType.SHUTDOWN, {}, timeout=2)
            except Exception:
                pass
            self.process.terminate()
            self.process.join(timeout=5)
            logger.info("IBKR Worker process stopped")

    def is_running(self) -> bool:
        """Check if worker is running."""
        return self.process is not None and self.process.is_alive()

    def _generate_request_id(self) -> str:
        """Generate unique request ID."""
        self._request_counter += 1
        return f"req_{self._request_counter}_{datetime.now().timestamp()}"

    def _send_request(
        self,
        request_type: RequestType,
        params: dict,
        timeout: float = 10.0,
    ) -> WorkerResponse | None:
        """Send request to worker and wait for response."""
        if not self.is_running() or not self.request_queue or not self.response_queue:
            return None

        request_id = self._generate_request_id()

        self.request_queue.put({
            "request_id": request_id,
            "request_type": request_type.value,
            "params": params,
        })

        # Wait for response
        start_time = datetime.now()
        while (datetime.now() - start_time).total_seconds() < timeout:
            try:
                response_data = self.response_queue.get(timeout=0.1)
                if response_data["request_id"] == request_id:
                    return WorkerResponse(**response_data)
                else:
                    # Store for later (shouldn't happen often)
                    self._pending_responses[response_data["request_id"]] = response_data
            except Empty:
                continue

        logger.warning(f"Request {request_id} timed out")
        return None

    def ping(self) -> bool:
        """Ping the worker to check if it's alive and connected."""
        response = self._send_request(RequestType.PING, {}, timeout=5)
        return response is not None and response.success

    def connect(self) -> bool:
        """Request worker to connect to IBKR."""
        response = self._send_request(RequestType.CONNECT, {}, timeout=30)
        return response is not None and response.success

    def get_stock_quote(self, symbol: str) -> dict | None:
        """Get stock quote via worker."""
        response = self._send_request(
            RequestType.STOCK_QUOTE,
            {"symbol": symbol},
            timeout=10,
        )
        return response.data if response and response.success else None

    def get_option_data(
        self,
        underlying: str,
        expiration: str,
        strike: float,
        option_type: str,
    ) -> dict | None:
        """Get option data via worker."""
        response = self._send_request(
            RequestType.OPTION_DATA,
            {
                "underlying": underlying,
                "expiration": expiration,
                "strike": strike,
                "option_type": option_type,
            },
            timeout=10,
        )
        return response.data if response and response.success else None

    def get_portfolio(self) -> list[dict]:
        """Get portfolio via worker."""
        response = self._send_request(RequestType.PORTFOLIO, {}, timeout=30)
        return response.data if response and response.success else []

    def get_account_pnl(self) -> dict | None:
        """Get account P&L via worker."""
        response = self._send_request(RequestType.ACCOUNT_PNL, {}, timeout=10)
        return response.data if response and response.success else None

    def fetch_executions(self) -> list[dict]:
        """Fetch executions via worker.

        Returns:
            List of execution dictionaries from IBKR (same-day only due to API limits)
        """
        response = self._send_request(RequestType.FETCH_EXECUTIONS, {}, timeout=30)
        return response.data if response and response.success else []
