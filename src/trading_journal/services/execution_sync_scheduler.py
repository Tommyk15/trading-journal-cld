"""Scheduled background sync for IBKR executions and Greeks.

This service provides automatic synchronization of:
- Executions from IBKR real-time API (every minute)
- Executions from IBKR Flex Query (daily reconciliation)
- Greeks and analytics for newly created trades
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.config import Settings
from trading_journal.core.database import AsyncSessionLocal
from trading_journal.models.execution import Execution
from trading_journal.models.trade import Trade

logger = logging.getLogger(__name__)


@dataclass
class SyncStats:
    """Statistics from a sync run."""

    sync_type: str  # "realtime" or "flex_query"
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    executions_fetched: int = 0
    executions_new: int = 0
    executions_existing: int = 0
    executions_errors: int = 0
    trades_created: int = 0
    trades_updated: int = 0
    greeks_fetched: int = 0
    greeks_failed: int = 0
    analytics_populated: int = 0
    max_profit_risk_populated: int = 0
    commissions_updated: int = 0
    error_message: str | None = None


class ExecutionSyncScheduler:
    """Background scheduler for automatic execution sync.

    Features:
    - Real-time sync every minute via IBKR API
    - Daily Flex Query reconciliation at midnight
    - Automatic Greeks fetching for new trades
    - Analytics population (max profit/risk, PoP, IV metrics)
    """

    def __init__(self, settings: Settings):
        """Initialize the scheduler.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self.scheduler = AsyncIOScheduler()
        self._running = False

        # Stats tracking
        self._stats: dict[str, Any] = {
            "total_syncs": 0,
            "last_sync": None,
            "last_stats": None,
            "consecutive_errors": 0,
            "history": [],  # Last 10 sync results
        }

    async def start(self) -> None:
        """Start the scheduler with configured jobs."""
        if self._running:
            logger.warning("Scheduler already running")
            return

        # Add real-time sync job (every minute)
        self.scheduler.add_job(
            self._run_realtime_sync,
            'interval',
            minutes=self.settings.execution_sync_interval_minutes,
            id='realtime_sync',
            replace_existing=True,
            max_instances=1,  # Prevent overlapping runs
        )

        # Add daily Flex Query reconciliation job
        self.scheduler.add_job(
            self._run_flex_query_sync,
            'cron',
            hour=self.settings.flex_query_daily_hour,
            minute=self.settings.flex_query_daily_minute,
            id='daily_flex_sync',
            replace_existing=True,
            max_instances=1,
        )

        self.scheduler.start()
        self._running = True

        logger.info(
            f"Execution sync scheduler started "
            f"(interval: {self.settings.execution_sync_interval_minutes}min, "
            f"daily flex at {self.settings.flex_query_daily_hour:02d}:{self.settings.flex_query_daily_minute:02d})"
        )

    async def stop(self) -> None:
        """Stop the scheduler gracefully."""
        if self._running:
            self.scheduler.shutdown(wait=False)
            self._running = False
            logger.info("Execution sync scheduler stopped")

    async def trigger_sync(self, sync_type: str = "realtime") -> SyncStats:
        """Manually trigger a sync.

        Args:
            sync_type: "realtime" or "flex_query"

        Returns:
            Sync statistics
        """
        if sync_type == "flex_query":
            return await self._run_flex_query_sync()
        return await self._run_realtime_sync()

    def get_status(self) -> dict[str, Any]:
        """Get current scheduler status.

        Returns:
            Status dictionary with scheduler info and stats
        """
        realtime_job = self.scheduler.get_job('realtime_sync')
        flex_job = self.scheduler.get_job('daily_flex_sync')

        return {
            "enabled": self._running,
            "interval_minutes": self.settings.execution_sync_interval_minutes,
            "fetch_greeks": self.settings.execution_sync_fetch_greeks,
            "flex_query_time": f"{self.settings.flex_query_daily_hour:02d}:{self.settings.flex_query_daily_minute:02d}",
            "next_realtime_sync": realtime_job.next_run_time.isoformat() if realtime_job and realtime_job.next_run_time else None,
            "next_flex_sync": flex_job.next_run_time.isoformat() if flex_job and flex_job.next_run_time else None,
            "total_syncs": self._stats["total_syncs"],
            "consecutive_errors": self._stats["consecutive_errors"],
            "last_sync": self._stats["last_sync"].isoformat() if self._stats["last_sync"] else None,
            "last_stats": self._stats["last_stats"],
            "history": self._stats["history"][-5:],  # Last 5 syncs
        }

    async def _run_realtime_sync(self) -> SyncStats:
        """Execute a real-time sync cycle via IBKR API.

        Returns:
            Sync statistics
        """
        stats = SyncStats(sync_type="realtime")
        logger.info("Starting real-time execution sync cycle")

        async with AsyncSessionLocal() as session:
            try:
                # 1. Fetch executions from IBKR worker
                exec_stats = await self._fetch_executions_from_worker(session)
                stats.executions_fetched = exec_stats["fetched"]
                stats.executions_new = exec_stats["new"]
                stats.executions_existing = exec_stats["existing"]
                stats.executions_errors = exec_stats["errors"]

                # 2. Group new executions into trades
                if stats.executions_new > 0:
                    trade_stats = await self._group_executions(session)
                    stats.trades_created = trade_stats.get("trades_created", 0)
                    stats.trades_updated = trade_stats.get("trades_updated", 0)

                # 3. Fetch Greeks for new trades (if enabled)
                if self.settings.execution_sync_fetch_greeks and stats.trades_created > 0:
                    greeks_stats = await self._fetch_greeks_for_pending(session)
                    stats.greeks_fetched = greeks_stats.get("succeeded", 0)
                    stats.greeks_failed = greeks_stats.get("failed", 0)

                # 4. Populate analytics for trades missing data
                analytics_stats = await self._populate_trade_analytics(session)
                stats.analytics_populated = analytics_stats.get("populated", 0)

                # 5. Populate max_profit/max_risk (doesn't require Greeks)
                max_profit_risk_stats = await self._populate_max_profit_risk(session)
                stats.max_profit_risk_populated = max_profit_risk_stats.get("populated", 0)

                # 6. Update missing commissions
                commission_stats = await self._update_missing_commissions(session)
                stats.commissions_updated = commission_stats.get("updated", 0)

                await session.commit()

                stats.completed_at = datetime.now(UTC)
                self._record_success(stats)

                logger.info(
                    f"Real-time sync completed: {stats.executions_new} new executions, "
                    f"{stats.trades_created} trades created, {stats.greeks_fetched} Greeks fetched"
                )

            except Exception as e:
                stats.error_message = str(e)
                stats.completed_at = datetime.now(UTC)
                self._record_error(stats)
                logger.error(f"Real-time sync failed: {e}")
                await session.rollback()

        return stats

    async def _run_flex_query_sync(self) -> SyncStats:
        """Execute daily Flex Query reconciliation.

        Returns:
            Sync statistics
        """
        stats = SyncStats(sync_type="flex_query")
        logger.info("Starting daily Flex Query sync")

        async with AsyncSessionLocal() as session:
            try:
                # Fetch executions from Flex Query (last 7 days)
                exec_stats = await self._fetch_executions_from_flex_query(session)
                stats.executions_fetched = exec_stats["fetched"]
                stats.executions_new = exec_stats["new"]
                stats.executions_existing = exec_stats["existing"]
                stats.executions_errors = exec_stats["errors"]

                # Group any new executions
                if stats.executions_new > 0:
                    trade_stats = await self._group_executions(session)
                    stats.trades_created = trade_stats.get("trades_created", 0)
                    stats.trades_updated = trade_stats.get("trades_updated", 0)

                # Fetch Greeks for new trades
                if self.settings.execution_sync_fetch_greeks and stats.trades_created > 0:
                    greeks_stats = await self._fetch_greeks_for_pending(session)
                    stats.greeks_fetched = greeks_stats.get("succeeded", 0)
                    stats.greeks_failed = greeks_stats.get("failed", 0)

                await session.commit()

                stats.completed_at = datetime.now(UTC)
                self._record_success(stats)

                logger.info(
                    f"Flex Query sync completed: {stats.executions_new} new executions, "
                    f"{stats.trades_created} trades created"
                )

            except Exception as e:
                stats.error_message = str(e)
                stats.completed_at = datetime.now(UTC)
                self._record_error(stats)
                logger.error(f"Flex Query sync failed: {e}")
                await session.rollback()

        return stats

    async def _fetch_executions_from_worker(self, session: AsyncSession) -> dict[str, int]:
        """Fetch executions from IBKR via worker process.

        Args:
            session: Database session

        Returns:
            Statistics dict with fetched, new, existing, errors counts
        """
        from trading_journal.services.market_data_service import MarketDataService

        stats = {"fetched": 0, "new": 0, "existing": 0, "errors": 0}

        try:
            # Get the IBKR worker client
            market_data = MarketDataService()
            worker = market_data._get_ibkr_worker()

            if not worker or not worker.is_running():
                logger.warning("IBKR worker not running, skipping execution fetch")
                return stats

            # Fetch executions via worker
            executions_data = worker.fetch_executions()
            stats["fetched"] = len(executions_data)

            # Import each execution
            for exec_data in executions_data:
                try:
                    # Check if already exists
                    stmt = select(Execution).where(Execution.exec_id == exec_data["exec_id"])
                    result = await session.execute(stmt)
                    existing = result.scalar_one_or_none()

                    if existing:
                        stats["existing"] += 1
                        continue

                    # Convert data types for database
                    db_data = self._convert_execution_data(exec_data)

                    # Create new execution
                    execution = Execution(**db_data)
                    session.add(execution)
                    stats["new"] += 1

                except Exception as e:
                    logger.error(f"Error importing execution {exec_data.get('exec_id')}: {e}")
                    stats["errors"] += 1

            await session.flush()

        except Exception as e:
            logger.error(f"Error fetching executions from worker: {e}")

        return stats

    async def _fetch_executions_from_flex_query(self, session: AsyncSession) -> dict[str, int]:
        """Fetch executions from IBKR Flex Query API.

        Args:
            session: Database session

        Returns:
            Statistics dict with fetched, new, existing, errors counts
        """
        from trading_journal.services.flex_query_service import FlexQueryService

        stats = {"fetched": 0, "new": 0, "existing": 0, "errors": 0}

        try:
            if not self.settings.ibkr_flex_token:
                logger.warning("Flex Query token not configured, skipping")
                return stats

            flex_service = FlexQueryService()
            executions_data = await flex_service.fetch_executions()
            stats["fetched"] = len(executions_data)

            for exec_data in executions_data:
                try:
                    # Check if already exists
                    stmt = select(Execution).where(Execution.exec_id == exec_data["exec_id"])
                    result = await session.execute(stmt)
                    existing = result.scalar_one_or_none()

                    if existing:
                        stats["existing"] += 1
                        # Update commission if existing has 0 and new data has commission
                        new_commission = exec_data.get("commission", Decimal("0"))
                        if existing.commission == 0 and new_commission > 0:
                            existing.commission = new_commission
                            # Also update net_amount to include commission if needed
                            if existing.trade_id:
                                # Mark trade for commission recalculation
                                trade_stmt = select(Trade).where(Trade.id == existing.trade_id)
                                trade_result = await session.execute(trade_stmt)
                                trade = trade_result.scalar_one_or_none()
                                if trade:
                                    # Get all executions for this trade to recalculate
                                    exec_stmt = select(Execution).where(Execution.trade_id == trade.id)
                                    exec_result = await session.execute(exec_stmt)
                                    trade_execs = list(exec_result.scalars().all())
                                    total_commission = sum(e.commission for e in trade_execs)
                                    trade.total_commission = total_commission
                                    if trade.status == "CLOSED":
                                        trade.realized_pnl = trade.closing_proceeds - trade.opening_cost - total_commission
                        continue

                    # Create new execution
                    execution = Execution(**exec_data)
                    session.add(execution)
                    stats["new"] += 1

                except Exception as e:
                    logger.error(f"Error importing Flex Query execution {exec_data.get('exec_id')}: {e}")
                    stats["errors"] += 1

            await session.flush()

        except Exception as e:
            logger.error(f"Error fetching from Flex Query: {e}")

        return stats

    async def _group_executions(self, session: AsyncSession) -> dict[str, int]:
        """Group unassigned executions into trades.

        Args:
            session: Database session

        Returns:
            Statistics dict
        """
        from trading_journal.services.trade_grouping_service import TradeGroupingService

        try:
            service = TradeGroupingService(session)
            stats = await service.process_new_executions()
            return stats
        except Exception as e:
            logger.error(f"Error grouping executions: {e}")
            return {"trades_created": 0, "trades_updated": 0}

    async def _fetch_greeks_for_pending(
        self,
        session: AsyncSession,
        limit: int = 5
    ) -> dict[str, int]:
        """Fetch Greeks for trades with greeks_pending=True.

        Args:
            session: Database session
            limit: Maximum trades to process per cycle (rate limiting)

        Returns:
            Statistics dict
        """
        from trading_journal.services.trade_analytics_service import TradeAnalyticsService

        stats = {"succeeded": 0, "failed": 0}

        try:
            # Find trades needing Greeks
            stmt = select(Trade).where(
                Trade.greeks_pending == True,  # noqa: E712
                Trade.status == "OPEN",
            ).limit(limit)

            result = await session.execute(stmt)
            trades = list(result.scalars().all())

            analytics_service = TradeAnalyticsService()

            for trade in trades:
                try:
                    success = await analytics_service.populate_all_trade_fields(
                        trade, session
                    )
                    if success:
                        stats["succeeded"] += 1
                    else:
                        stats["failed"] += 1
                except Exception as e:
                    logger.error(f"Error fetching Greeks for trade {trade.id}: {e}")
                    stats["failed"] += 1

                # Small delay for rate limiting
                await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"Error in Greeks fetch: {e}")

        return stats

    async def _populate_trade_analytics(
        self,
        session: AsyncSession,
        limit: int = 10
    ) -> dict[str, int]:
        """Populate analytics fields for trades missing data.

        Args:
            session: Database session
            limit: Maximum trades to process per cycle

        Returns:
            Statistics dict
        """
        from trading_journal.services.trade_analytics_service import TradeAnalyticsService

        stats = {"populated": 0}

        try:
            # Find trades with Greeks but missing analytics
            stmt = select(Trade).where(
                Trade.delta_open.isnot(None),  # Has Greeks
                Trade.max_profit.is_(None),  # Missing analytics
                Trade.status == "OPEN",
            ).limit(limit)

            result = await session.execute(stmt)
            trades = list(result.scalars().all())

            analytics_service = TradeAnalyticsService()

            for trade in trades:
                try:
                    success = await analytics_service.populate_analytics_only(
                        trade, session
                    )
                    if success:
                        stats["populated"] += 1
                except Exception as e:
                    logger.error(f"Error populating analytics for trade {trade.id}: {e}")

        except Exception as e:
            logger.error(f"Error in analytics population: {e}")

        return stats

    async def _populate_max_profit_risk(
        self,
        session,
        limit: int = 100,
    ) -> dict:
        """Populate max_profit/max_risk for trades missing them.

        Unlike _populate_analytics, this doesn't require Greeks to be present.
        It only needs execution data to calculate max profit and risk.

        Args:
            session: Database session
            limit: Maximum trades to process per cycle

        Returns:
            Statistics dict
        """
        from trading_journal.services.trade_analytics_service import TradeAnalyticsService

        stats = {"populated": 0}

        try:
            # Find trades missing max_profit (regardless of Greeks status)
            stmt = select(Trade).where(
                Trade.max_profit.is_(None),  # Missing max_profit
            ).limit(limit)

            result = await session.execute(stmt)
            trades = list(result.scalars().all())

            if trades:
                logger.info(f"Populating max_profit/risk for {len(trades)} trades")

            analytics_service = TradeAnalyticsService()

            for trade in trades:
                try:
                    success = await analytics_service.populate_max_profit_risk_only(
                        trade, session
                    )
                    if success:
                        stats["populated"] += 1
                except Exception as e:
                    logger.error(f"Error populating max profit/risk for trade {trade.id}: {e}")

        except Exception as e:
            logger.error(f"Error in max profit/risk population: {e}")

        return stats

    async def _update_missing_commissions(
        self,
        session,
        limit: int = 100,
    ) -> dict:
        """Update commissions for executions that have 0 commission.

        This fetches updated execution data from IBKR and updates the
        commission values for executions where commission is 0.

        Args:
            session: Database session
            limit: Maximum executions to process per cycle

        Returns:
            Statistics dict
        """
        stats = {"updated": 0, "trades_updated": 0}

        try:
            # Find executions with 0 commission from today
            from datetime import timedelta
            today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

            stmt = select(Execution).where(
                Execution.commission == 0,
                Execution.execution_time >= today_start - timedelta(days=7),  # Last 7 days
            ).limit(limit)

            result = await session.execute(stmt)
            zero_commission_execs = list(result.scalars().all())

            if not zero_commission_execs:
                return stats

            logger.info(f"Found {len(zero_commission_execs)} executions with 0 commission")

            # Fetch fresh execution data from IBKR worker
            from trading_journal.services.ibkr_client_service import IBKRClientService

            ibkr_client = IBKRClientService()
            fresh_executions = await ibkr_client.fetch_executions()

            if not fresh_executions:
                logger.debug("No executions returned from IBKR worker")
                return stats

            # Build a map of exec_id -> commission
            exec_commission_map = {
                exec_data["exec_id"]: Decimal(str(exec_data.get("commission", 0)))
                for exec_data in fresh_executions
            }

            # Update executions with new commission values
            trade_ids_to_update = set()
            for exec in zero_commission_execs:
                if exec.exec_id in exec_commission_map:
                    new_commission = exec_commission_map[exec.exec_id]
                    if new_commission > 0:
                        exec.commission = new_commission
                        stats["updated"] += 1
                        if exec.trade_id:
                            trade_ids_to_update.add(exec.trade_id)

            # Update trade total_commission for affected trades
            if trade_ids_to_update:
                for trade_id in trade_ids_to_update:
                    # Get all executions for this trade
                    exec_stmt = select(Execution).where(Execution.trade_id == trade_id)
                    exec_result = await session.execute(exec_stmt)
                    trade_execs = list(exec_result.scalars().all())

                    total_commission = sum(e.commission for e in trade_execs)

                    # Update the trade
                    trade_stmt = select(Trade).where(Trade.id == trade_id)
                    trade_result = await session.execute(trade_stmt)
                    trade = trade_result.scalar_one_or_none()

                    if trade:
                        trade.total_commission = total_commission
                        # Recalculate realized_pnl
                        if trade.status == "CLOSED":
                            trade.realized_pnl = trade.closing_proceeds - trade.opening_cost - total_commission
                        stats["trades_updated"] += 1

            if stats["updated"] > 0:
                logger.info(
                    f"Updated commissions: {stats['updated']} executions, "
                    f"{stats['trades_updated']} trades"
                )

        except Exception as e:
            logger.error(f"Error updating commissions: {e}")

        return stats

    def _convert_execution_data(self, exec_data: dict) -> dict:
        """Convert worker execution data to database-compatible format.

        Args:
            exec_data: Raw execution data from IBKR worker

        Returns:
            Converted data dict
        """
        from datetime import datetime

        result = dict(exec_data)

        # Convert execution_time string to datetime
        if isinstance(result.get("execution_time"), str):
            result["execution_time"] = datetime.fromisoformat(result["execution_time"])
            if result["execution_time"].tzinfo is None:
                result["execution_time"] = result["execution_time"].replace(tzinfo=UTC)

        # Convert expiration string to datetime
        if isinstance(result.get("expiration"), str):
            result["expiration"] = datetime.fromisoformat(result["expiration"])
            if result["expiration"].tzinfo is None:
                result["expiration"] = result["expiration"].replace(tzinfo=UTC)

        # Convert numeric fields to Decimal
        for field in ["quantity", "price", "commission", "net_amount", "strike"]:
            if result.get(field) is not None:
                result[field] = Decimal(str(result[field]))

        return result

    def _record_success(self, stats: SyncStats) -> None:
        """Record successful sync in stats."""
        self._stats["total_syncs"] += 1
        self._stats["last_sync"] = stats.completed_at
        self._stats["last_stats"] = {
            "type": stats.sync_type,
            "executions_new": stats.executions_new,
            "trades_created": stats.trades_created,
            "greeks_fetched": stats.greeks_fetched,
        }
        self._stats["consecutive_errors"] = 0

        # Add to history
        self._stats["history"].append({
            "type": stats.sync_type,
            "timestamp": stats.completed_at.isoformat() if stats.completed_at else None,
            "executions_new": stats.executions_new,
            "trades_created": stats.trades_created,
            "success": True,
        })

        # Keep only last 10 entries
        if len(self._stats["history"]) > 10:
            self._stats["history"] = self._stats["history"][-10:]

    def _record_error(self, stats: SyncStats) -> None:
        """Record failed sync in stats."""
        self._stats["total_syncs"] += 1
        self._stats["last_sync"] = stats.completed_at
        self._stats["last_stats"] = {
            "type": stats.sync_type,
            "error": stats.error_message,
        }
        self._stats["consecutive_errors"] += 1

        # Add to history
        self._stats["history"].append({
            "type": stats.sync_type,
            "timestamp": stats.completed_at.isoformat() if stats.completed_at else None,
            "success": False,
            "error": stats.error_message,
        })

        # Keep only last 10 entries
        if len(self._stats["history"]) > 10:
            self._stats["history"] = self._stats["history"][-10:]
