"""Service for managing Greeks data - fetching, storing, and retrieving."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.models.greeks import Greeks
from trading_journal.models.position import Position
from trading_journal.services.ibkr_service import IBKRService


class GreeksService:
    """Service for Greeks data management."""

    def __init__(self, session: AsyncSession):
        """Initialize Greeks service.

        Args:
            session: Database session
        """
        self.session = session

    async def fetch_and_store_greeks(
        self,
        position_id: int,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ) -> Optional[Greeks]:
        """Fetch Greeks from IBKR and store in database.

        Args:
            position_id: Position database ID
            host: IBKR host (optional)
            port: IBKR port (optional)

        Returns:
            Greeks model or None if fetch failed
        """
        # Get position
        position = await self.get_position(position_id)
        if not position:
            raise ValueError(f"Position {position_id} not found")

        # Only fetch Greeks for options
        if not position.option_type:
            raise ValueError(f"Position {position_id} is not an option")

        # Fetch Greeks from IBKR
        async with IBKRService() as ibkr:
            if host and port:
                await ibkr.connect(host=host, port=port)

            greeks_data = await ibkr.fetch_greeks_for_position(
                underlying=position.underlying,
                option_type=position.option_type,
                strike=position.strike,
                expiration=position.expiration,
            )

        if not greeks_data:
            return None

        # Store Greeks
        greeks = await self.create_greeks_record(position_id, greeks_data)
        await self.session.commit()

        return greeks

    async def fetch_all_positions_greeks(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ) -> dict:
        """Fetch Greeks for all open positions from IBKR.

        Args:
            host: IBKR host (optional)
            port: IBKR port (optional)

        Returns:
            Dictionary with fetch statistics
        """
        stats = {
            "positions_processed": 0,
            "greeks_fetched": 0,
            "errors": 0,
        }

        # Get all open positions (options only)
        stmt = (
            select(Position)
            .where(Position.option_type.isnot(None))
            .order_by(Position.underlying, Position.expiration)
        )
        result = await self.session.execute(stmt)
        positions = list(result.scalars().all())

        stats["positions_processed"] = len(positions)

        # Fetch Greeks from IBKR
        async with IBKRService() as ibkr:
            if host and port:
                await ibkr.connect(host=host, port=port)

            for position in positions:
                try:
                    greeks_data = await ibkr.fetch_greeks_for_position(
                        underlying=position.underlying,
                        option_type=position.option_type,
                        strike=position.strike,
                        expiration=position.expiration,
                    )

                    if greeks_data:
                        await self.create_greeks_record(position.id, greeks_data)
                        stats["greeks_fetched"] += 1

                except Exception as e:
                    print(f"Error fetching Greeks for position {position.id}: {e}")
                    stats["errors"] += 1

        await self.session.commit()
        return stats

    async def create_greeks_record(
        self,
        position_id: int,
        greeks_data: dict,
    ) -> Greeks:
        """Create a Greeks record in the database.

        Args:
            position_id: Position database ID
            greeks_data: Greeks data dictionary

        Returns:
            Created Greeks model
        """
        greeks = Greeks(
            position_id=position_id,
            timestamp=datetime.utcnow(),
            delta=greeks_data.get("delta"),
            gamma=greeks_data.get("gamma"),
            theta=greeks_data.get("theta"),
            vega=greeks_data.get("vega"),
            rho=None,  # IBKR doesn't provide rho
            implied_volatility=greeks_data.get("implied_volatility"),
            underlying_price=greeks_data.get("underlying_price"),
            option_price=greeks_data.get("option_price"),
            model_type="IBKR",
        )

        self.session.add(greeks)
        await self.session.flush()
        return greeks

    async def get_latest_greeks(self, position_id: int) -> Optional[Greeks]:
        """Get latest Greeks for a position.

        Args:
            position_id: Position database ID

        Returns:
            Latest Greeks or None
        """
        stmt = (
            select(Greeks)
            .where(Greeks.position_id == position_id)
            .order_by(Greeks.timestamp.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_greeks_history(
        self,
        position_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[Greeks]:
        """Get historical Greeks for a position.

        Args:
            position_id: Position database ID
            start_date: Start date filter
            end_date: End date filter
            limit: Maximum results

        Returns:
            List of Greeks records
        """
        stmt = (
            select(Greeks)
            .where(Greeks.position_id == position_id)
            .order_by(Greeks.timestamp.desc())
        )

        if start_date:
            stmt = stmt.where(Greeks.timestamp >= start_date)
        if end_date:
            stmt = stmt.where(Greeks.timestamp <= end_date)

        stmt = stmt.limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_position(self, position_id: int) -> Optional[Position]:
        """Get position by ID.

        Args:
            position_id: Position database ID

        Returns:
            Position or None
        """
        stmt = select(Position).where(Position.id == position_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
