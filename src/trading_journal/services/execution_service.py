"""Service for managing executions - syncing from IBKR to database."""

from datetime import datetime
from typing import Optional

from sqlalchemy import select
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
        host: Optional[str] = None,
        port: Optional[int] = None,
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

    async def get_by_exec_id(self, exec_id: str) -> Optional[Execution]:
        """Get execution by exec_id.

        Args:
            exec_id: IBKR execution ID

        Returns:
            Execution or None if not found
        """
        stmt = select(Execution).where(Execution.exec_id == exec_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, execution_id: int) -> Optional[Execution]:
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
        underlying: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
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
