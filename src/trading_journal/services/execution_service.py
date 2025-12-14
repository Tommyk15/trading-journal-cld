"""Service for managing executions - syncing from IBKR to database."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.models.execution import Execution
from trading_journal.services.ibkr_service import IBKRService


class ExecutionService:
    """Service for execution management."""

    def __init__(self, session: AsyncSession):
        """Initialize execution service.

        Args:
            session: Database session
        """
        self.session = session

    async def sync_from_ibkr(
        self,
        days_back: int = 7,
        host: str | None = None,
        port: int | None = None,
    ) -> dict:
        """Sync executions from IBKR to database.

        Args:
            days_back: Number of days to look back
            host: IBKR host (optional)
            port: IBKR port (optional)

        Returns:
            Dictionary with sync statistics

        Raises:
            ConnectionError: If IBKR connection fails
        """
        stats = {
            "fetched": 0,
            "new": 0,
            "existing": 0,
            "errors": 0,
        }

        # Connect to IBKR and fetch executions
        async with IBKRService() as ibkr:
            if host and port:
                await ibkr.connect(host=host, port=port)

            executions_data = await ibkr.fetch_executions(days_back=days_back)
            stats["fetched"] = len(executions_data)

            # Process each execution
            for exec_data in executions_data:
                try:
                    # Check if execution already exists
                    existing = await self.get_by_exec_id(exec_data["exec_id"])

                    if existing:
                        stats["existing"] += 1
                        continue

                    # Create new execution
                    await self.create_execution(exec_data)
                    stats["new"] += 1

                except Exception as e:
                    print(f"Error processing execution {exec_data.get('exec_id')}: {e}")
                    stats["errors"] += 1

            await self.session.commit()

        return stats

    async def create_execution(self, exec_data: dict) -> Execution:
        """Create a new execution record.

        Args:
            exec_data: Execution data dictionary

        Returns:
            Created Execution model
        """
        execution = Execution(**exec_data)
        self.session.add(execution)
        await self.session.flush()
        return execution

    async def get_by_exec_id(self, exec_id: str) -> Execution | None:
        """Get execution by exec_id.

        Args:
            exec_id: IBKR execution ID

        Returns:
            Execution or None if not found
        """
        stmt = select(Execution).where(Execution.exec_id == exec_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, execution_id: int) -> Execution | None:
        """Get execution by database ID.

        Args:
            execution_id: Database ID

        Returns:
            Execution or None if not found
        """
        stmt = select(Execution).where(Execution.id == execution_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_executions(
        self,
        underlying: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Execution]:
        """List executions with optional filters.

        Args:
            underlying: Filter by underlying symbol
            start_date: Filter by start date
            end_date: Filter by end date
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of Execution models
        """
        stmt = select(Execution)

        # Apply filters
        if underlying:
            stmt = stmt.where(Execution.underlying == underlying)
        if start_date:
            stmt = stmt.where(Execution.execution_time >= start_date)
        if end_date:
            stmt = stmt.where(Execution.execution_time <= end_date)

        # Apply ordering and pagination
        stmt = stmt.order_by(Execution.execution_time.desc())
        stmt = stmt.limit(limit).offset(offset)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_executions_by_underlying(
        self, underlying: str
    ) -> list[Execution]:
        """Get all executions for a specific underlying.

        Args:
            underlying: Underlying symbol

        Returns:
            List of Execution models
        """
        stmt = (
            select(Execution)
            .where(Execution.underlying == underlying)
            .order_by(Execution.execution_time)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_executions_with_filter(
        self,
        unassigned_only: bool = False,
        opens_only: bool = False,
        underlying: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Execution], int]:
        """List executions with optional filters including unassigned filter.

        Args:
            unassigned_only: Filter to only executions not assigned to a trade
            opens_only: Filter to only opening transactions (O indicator)
            underlying: Filter by underlying symbol
            start_date: Filter by start date
            end_date: Filter by end date
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            Tuple of (list of Execution models, total count)
        """
        stmt = select(Execution)

        # Apply filters
        if unassigned_only:
            stmt = stmt.where(Execution.trade_id.is_(None))
        if opens_only:
            stmt = stmt.where(Execution.open_close_indicator == 'O')
        if underlying:
            stmt = stmt.where(Execution.underlying == underlying)
        if start_date:
            stmt = stmt.where(Execution.execution_time >= start_date)
        if end_date:
            stmt = stmt.where(Execution.execution_time <= end_date)

        # Get total count with same filters
        count_stmt = select(func.count(Execution.id))
        if unassigned_only:
            count_stmt = count_stmt.where(Execution.trade_id.is_(None))
        if opens_only:
            count_stmt = count_stmt.where(Execution.open_close_indicator == 'O')
        if underlying:
            count_stmt = count_stmt.where(Execution.underlying == underlying)
        if start_date:
            count_stmt = count_stmt.where(Execution.execution_time >= start_date)
        if end_date:
            count_stmt = count_stmt.where(Execution.execution_time <= end_date)

        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0

        # Apply ordering and pagination
        stmt = stmt.order_by(Execution.execution_time.desc())
        stmt = stmt.limit(limit).offset(offset)

        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def get_executions_by_ids(self, execution_ids: list[int]) -> list[Execution]:
        """Get multiple executions by their database IDs.

        Args:
            execution_ids: List of database IDs

        Returns:
            List of Execution models
        """
        if not execution_ids:
            return []
        stmt = (
            select(Execution)
            .where(Execution.id.in_(execution_ids))
            .order_by(Execution.execution_time)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_matching_closes_fifo(self, open_execution: Execution) -> list[Execution]:
        """Find matching closing transactions for an opening execution using FIFO.

        Matches closing transactions (BTC/STC) to opening transactions based on:
        - Same underlying symbol
        - Same option contract (strike, expiry, type) for options
        - Opposite side (close indicator = 'C')
        - Not yet assigned to a trade
        - FIFO order (oldest first)

        Args:
            open_execution: The opening execution to find closes for

        Returns:
            List of matching closing Execution models (up to the open quantity)
        """
        # Build query for matching closes
        stmt = select(Execution).where(
            Execution.underlying == open_execution.underlying,
            Execution.open_close_indicator == 'C',
            Execution.trade_id.is_(None),  # Unassigned only
            Execution.execution_time >= open_execution.execution_time,  # After the open
        )

        # For options, match by contract details
        if open_execution.security_type == 'OPT':
            stmt = stmt.where(
                Execution.security_type == 'OPT',
                Execution.strike == open_execution.strike,
                Execution.expiration == open_execution.expiration,
                Execution.option_type == open_execution.option_type,
            )
        else:
            # For stocks, just match the security type
            stmt = stmt.where(Execution.security_type == 'STK')

        # Order by execution time (FIFO)
        stmt = stmt.order_by(Execution.execution_time)

        result = await self.session.execute(stmt)
        closes = list(result.scalars().all())

        # Return closes up to the quantity needed
        matched_closes = []
        remaining_qty = open_execution.quantity

        for close in closes:
            if remaining_qty <= 0:
                break
            matched_closes.append(close)
            remaining_qty -= close.quantity

        return matched_closes

    async def assign_execution_to_trade(self, execution_id: int, trade_id: int) -> Execution:
        """Assign an execution to a trade.

        Args:
            execution_id: Execution database ID
            trade_id: Trade database ID

        Returns:
            Updated Execution model
        """
        stmt = select(Execution).where(Execution.id == execution_id)
        result = await self.session.execute(stmt)
        execution = result.scalar_one_or_none()

        if execution:
            execution.trade_id = trade_id
            await self.session.flush()

        return execution

    async def assign_executions_to_trade(self, execution_ids: list[int], trade_id: int) -> list[Execution]:
        """Assign multiple executions to a trade.

        Args:
            execution_ids: List of execution database IDs
            trade_id: Trade database ID

        Returns:
            List of updated Execution models
        """
        if not execution_ids:
            return []

        stmt = select(Execution).where(Execution.id.in_(execution_ids))
        result = await self.session.execute(stmt)
        executions = list(result.scalars().all())

        for execution in executions:
            execution.trade_id = trade_id

        await self.session.flush()
        return executions
