"""Service for managing positions - syncing from IBKR and tracking open positions."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.models.position import Position
from trading_journal.models.trade import Trade


class PositionService:
    """Service for position management."""

    def __init__(self, session: AsyncSession):
        """Initialize position service.

        Args:
            session: Database session
        """
        self.session = session

    async def sync_positions_from_ibkr(
        self,
        host: str | None = None,
        port: int | None = None,
    ) -> dict:
        """Sync current positions from IBKR to database.

        Args:
            host: IBKR host (optional)
            port: IBKR port (optional)

        Returns:
            Dictionary with sync statistics
        """
        from trading_journal.config import get_settings
        from trading_journal.services.ibkr_service import _sync_ibkr_operation

        settings = get_settings()
        host = host or settings.ibkr_host
        port = port or settings.ibkr_port
        client_id = settings.ibkr_client_id

        stats = {
            "fetched": 0,
            "updated": 0,
            "created": 0,
            "errors": 0,
        }

        # Define operation to run in IBKR
        def fetch_positions(ib):
            return ib.positions()

        # Run in executor
        loop = asyncio.get_event_loop()
        ibkr_positions = await loop.run_in_executor(
            None, _sync_ibkr_operation, host, port, client_id, fetch_positions
        )

        stats["fetched"] = len(ibkr_positions)

        for ibkr_pos in ibkr_positions:
            try:
                contract = ibkr_pos.contract

                # Parse position data
                position_data = {
                    "underlying": contract.symbol,
                    "quantity": int(ibkr_pos.position),
                    "avg_cost": Decimal(str(ibkr_pos.avgCost)),
                }

                # Add option-specific fields
                if contract.secType == "OPT":
                    position_data.update({
                        "option_type": contract.right,
                        "strike": Decimal(str(contract.strike)),
                        "expiration": datetime.strptime(
                            contract.lastTradeDateOrContractMonth, "%Y%m%d"
                        ),
                    })
                else:
                    position_data.update({
                        "option_type": None,
                        "strike": None,
                        "expiration": None,
                    })

                # Find or create position
                # Note: This is simplified - in production, we'd match to existing trades
                existing = await self.find_matching_position(position_data)

                if existing:
                    # Update existing position
                    existing.quantity = position_data["quantity"]
                    existing.avg_cost = position_data["avg_cost"]
                    existing.updated_at = datetime.now(UTC)
                    stats["updated"] += 1
                else:
                    # Create new position (needs to be linked to a trade)
                    # For now, we'll create a placeholder trade
                    trade = await self.create_placeholder_trade(position_data)
                    await self.create_position(trade.id, position_data)
                    stats["created"] += 1

            except Exception as e:
                print(f"Error processing position: {e}")
                stats["errors"] += 1

        await self.session.commit()
        return stats

    async def find_matching_position(self, position_data: dict) -> Position | None:
        """Find existing position matching the criteria.

        Args:
            position_data: Position data dictionary

        Returns:
            Matching Position or None
        """
        stmt = select(Position).where(
            Position.underlying == position_data["underlying"]
        )

        if position_data.get("option_type"):
            stmt = stmt.where(
                Position.option_type == position_data["option_type"],
                Position.strike == position_data["strike"],
                Position.expiration == position_data["expiration"],
            )

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_placeholder_trade(self, position_data: dict) -> Trade:
        """Create a placeholder trade for orphaned positions.

        Args:
            position_data: Position data dictionary

        Returns:
            Created Trade model
        """
        trade = Trade(
            underlying=position_data["underlying"],
            strategy_type="Single",  # Placeholder
            status="OPEN",
            opened_at=datetime.now(UTC),
            closed_at=None,
            realized_pnl=Decimal("0.00"),
            unrealized_pnl=Decimal("0.00"),
            total_pnl=Decimal("0.00"),
            opening_cost=Decimal("0.00"),  # Will be calculated
            closing_proceeds=None,
            total_commission=Decimal("0.00"),
            num_legs=1,
            num_executions=0,  # No executions linked yet
            notes="Auto-created from IBKR position sync",
        )

        self.session.add(trade)
        await self.session.flush()
        return trade

    async def create_position(self, trade_id: int, position_data: dict) -> Position:
        """Create a position record.

        Args:
            trade_id: Trade database ID
            position_data: Position data dictionary

        Returns:
            Created Position model
        """
        position = Position(
            trade_id=trade_id,
            underlying=position_data["underlying"],
            option_type=position_data.get("option_type"),
            strike=position_data.get("strike"),
            expiration=position_data.get("expiration"),
            quantity=position_data["quantity"],
            avg_cost=position_data["avg_cost"],
            current_price=None,  # Will be updated separately
            unrealized_pnl=Decimal("0.00"),  # Will be calculated
        )

        self.session.add(position)
        await self.session.flush()
        return position

    async def update_position_price(
        self,
        position_id: int,
        current_price: Decimal,
    ) -> Position:
        """Update position with current market price and calculate P&L.

        Args:
            position_id: Position database ID
            current_price: Current market price

        Returns:
            Updated Position
        """
        position = await self.get_by_id(position_id)
        if not position:
            raise ValueError(f"Position {position_id} not found")

        position.current_price = current_price

        # Calculate unrealized P&L
        # For long positions: (current_price - avg_cost) * quantity
        # For short positions: (avg_cost - current_price) * quantity
        if position.quantity > 0:
            # Long position
            pnl_per_share = current_price - position.avg_cost
        else:
            # Short position
            pnl_per_share = position.avg_cost - current_price

        position.unrealized_pnl = pnl_per_share * abs(position.quantity)
        position.updated_at = datetime.now(UTC)

        await self.session.flush()
        return position

    async def get_by_id(self, position_id: int) -> Position | None:
        """Get position by ID.

        Args:
            position_id: Position database ID

        Returns:
            Position or None
        """
        stmt = select(Position).where(Position.id == position_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_open_positions(
        self,
        underlying: str | None = None,
    ) -> list[Position]:
        """Get all open positions.

        Args:
            underlying: Filter by underlying (optional)

        Returns:
            List of Position models
        """
        stmt = select(Position).order_by(Position.underlying, Position.expiration)

        if underlying:
            stmt = stmt.where(Position.underlying == underlying)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_option_positions(self) -> list[Position]:
        """Get all option positions.

        Returns:
            List of option Position models
        """
        stmt = (
            select(Position)
            .where(Position.option_type.isnot(None))
            .order_by(Position.underlying, Position.expiration)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
