"""Market Data Service - Multi-source market data with caching.

Data Source Priority:
1. IBKR (real-time, pre-calculated P&L, requires TWS) - via separate worker process
2. Polygon (15-min delay, Greeks/IV, $29/mo)
3. yfinance (free backup, delayed, calculate Greeks)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any

from trading_journal.config import get_settings

logger = logging.getLogger(__name__)

# Global IBKR worker client instance
_ibkr_worker_client = None


class DataSource(Enum):
    """Data source identifier."""

    IBKR = "IBKR"
    POLYGON = "POLYGON"
    YFINANCE = "YFINANCE"
    CACHED = "CACHED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass
class CacheEntry:
    """Cache entry with timestamp."""

    data: Any
    timestamp: datetime
    source: DataSource
    ttl_seconds: int = 300  # 5 minutes default

    @property
    def is_stale(self) -> bool:
        """Check if cache entry is stale."""
        return datetime.now() - self.timestamp > timedelta(seconds=self.ttl_seconds)

    @property
    def age_seconds(self) -> float:
        """Age of cache entry in seconds."""
        return (datetime.now() - self.timestamp).total_seconds()


@dataclass
class OptionQuote:
    """Option quote data."""

    symbol: str
    underlying: str
    strike: Decimal
    expiration: datetime
    option_type: str  # C or P
    bid: Decimal | None = None
    ask: Decimal | None = None
    last: Decimal | None = None
    mid: Decimal | None = None
    volume: int | None = None
    open_interest: int | None = None
    source: DataSource = DataSource.UNAVAILABLE


@dataclass
class OptionGreeks:
    """Greeks for an option."""

    delta: Decimal | None = None
    gamma: Decimal | None = None
    theta: Decimal | None = None
    vega: Decimal | None = None
    rho: Decimal | None = None
    iv: Decimal | None = None
    source: DataSource = DataSource.UNAVAILABLE


@dataclass
class StockQuote:
    """Stock quote data."""

    symbol: str
    price: Decimal | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    last: Decimal | None = None
    close: Decimal | None = None
    volume: int | None = None
    source: DataSource = DataSource.UNAVAILABLE


@dataclass
class PositionMarketData:
    """Market data for a position/trade."""

    trade_id: int
    underlying: str
    underlying_price: Decimal | None = None
    legs: list[dict] = field(default_factory=list)
    total_market_value: Decimal | None = None
    total_cost_basis: Decimal = Decimal("0")
    unrealized_pnl: Decimal | None = None
    unrealized_pnl_percent: Decimal | None = None
    net_delta: Decimal | None = None
    net_theta: Decimal | None = None
    net_gamma: Decimal | None = None
    net_vega: Decimal | None = None
    source: DataSource = DataSource.UNAVAILABLE
    timestamp: datetime = field(default_factory=datetime.now)
    is_stale: bool = False


class MarketDataService:
    """Service for fetching market data from multiple sources.

    Prioritizes IBKR for real-time data, falls back to Polygon,
    then yfinance for free delayed data.
    """

    def __init__(self, use_ibkr: bool = True):
        """Initialize market data service.

        Args:
            use_ibkr: If True, use IBKR via separate worker process.
                     The worker runs ib_insync in its own process to avoid
                     event loop conflicts with uvicorn.
        """
        self.settings = get_settings()
        self._cache: dict[str, CacheEntry] = {}
        self._use_ibkr = use_ibkr
        self._ibkr_worker = None
        self._polygon_service = None
        self._stock_cache_ttl = 300  # 5 minutes
        self._option_cache_ttl = 300  # 5 minutes
        self._closed_market_ttl = 900  # 15 minutes when market closed

    # =========================================================================
    # Connection Management
    # =========================================================================

    def _get_ibkr_worker(self):
        """Get or create IBKR worker client."""
        global _ibkr_worker_client

        if not self._use_ibkr:
            return None

        # Use global singleton for worker
        if _ibkr_worker_client is None:
            try:
                from trading_journal.services.ibkr_worker import IBKRWorkerClient

                import random
                # Use random client ID to avoid conflicts with previous processes
                client_id = random.randint(200, 999)
                _ibkr_worker_client = IBKRWorkerClient(
                    host=self.settings.ibkr_host,
                    port=self.settings.ibkr_port,
                    client_id=client_id,
                )
                _ibkr_worker_client.start()
                logger.info("IBKR worker process started")
            except Exception as e:
                logger.warning(f"Failed to start IBKR worker: {e}")
                return None

        return _ibkr_worker_client

    async def connect_ibkr(self) -> bool:
        """Connect to IBKR TWS/Gateway via worker process.

        Returns:
            True if connected successfully
        """
        if not self._use_ibkr:
            return False

        worker = self._get_ibkr_worker()
        if not worker:
            return False

        if not worker.is_running():
            worker.start()

        # Check if worker is connected
        return worker.ping()

    async def disconnect_ibkr(self) -> None:
        """Disconnect from IBKR."""
        global _ibkr_worker_client
        if _ibkr_worker_client:
            _ibkr_worker_client.stop()
            _ibkr_worker_client = None

    def _get_polygon_service(self):
        """Get or create Polygon service instance."""
        if self._polygon_service is None:
            try:
                from trading_journal.services.polygon_service import PolygonService

                self._polygon_service = PolygonService()
            except Exception as e:
                logger.warning(f"Polygon service not available: {e}")
        return self._polygon_service

    # =========================================================================
    # Cache Management
    # =========================================================================

    def _cache_key(self, prefix: str, *args) -> str:
        """Generate cache key."""
        return f"{prefix}:{':'.join(str(a) for a in args)}"

    def _get_cached(self, key: str) -> CacheEntry | None:
        """Get cached entry if not stale."""
        entry = self._cache.get(key)
        if entry and not entry.is_stale:
            return entry
        return None

    def _set_cache(
        self, key: str, data: Any, source: DataSource, ttl: int | None = None
    ) -> None:
        """Set cache entry."""
        self._cache[key] = CacheEntry(
            data=data,
            timestamp=datetime.now(),
            source=source,
            ttl_seconds=ttl or self._stock_cache_ttl,
        )

    def clear_cache(self) -> None:
        """Clear all cached data."""
        self._cache.clear()

    # =========================================================================
    # Stock Quotes
    # =========================================================================

    async def get_stock_quote(self, symbol: str) -> StockQuote:
        """Get stock quote from best available source.

        Args:
            symbol: Stock ticker symbol

        Returns:
            StockQuote with price data
        """
        cache_key = self._cache_key("stock", symbol)
        cached = self._get_cached(cache_key)
        if cached:
            quote = cached.data
            quote.source = DataSource.CACHED
            return quote

        # Try IBKR first
        quote = await self._get_stock_quote_ibkr(symbol)
        if quote.price is not None:
            self._set_cache(cache_key, quote, DataSource.IBKR)
            return quote

        # Fall back to Polygon
        quote = await self._get_stock_quote_polygon(symbol)
        if quote.price is not None:
            self._set_cache(cache_key, quote, DataSource.POLYGON)
            return quote

        # Fall back to yfinance
        quote = await self._get_stock_quote_yfinance(symbol)
        if quote.price is not None:
            self._set_cache(cache_key, quote, DataSource.YFINANCE)
            return quote

        return StockQuote(symbol=symbol, source=DataSource.UNAVAILABLE)

    async def _get_stock_quote_ibkr(self, symbol: str) -> StockQuote:
        """Get stock quote from IBKR via worker process."""
        quote = StockQuote(symbol=symbol, source=DataSource.IBKR)

        worker = self._get_ibkr_worker()
        if not worker or not worker.is_running():
            return quote

        try:
            # Call worker in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                worker.get_stock_quote,
                symbol,
            )

            if result:
                quote.price = Decimal(str(result["price"])) if result.get("price") else None
                quote.bid = Decimal(str(result["bid"])) if result.get("bid") else None
                quote.ask = Decimal(str(result["ask"])) if result.get("ask") else None
                quote.last = Decimal(str(result["last"])) if result.get("last") else None
                quote.close = Decimal(str(result["close"])) if result.get("close") else None
                quote.volume = result.get("volume")

        except Exception as e:
            logger.error(f"IBKR stock quote error for {symbol}: {e}")

        return quote

    async def _get_stock_quote_polygon(self, symbol: str) -> StockQuote:
        """Get stock quote from Polygon."""
        quote = StockQuote(symbol=symbol, source=DataSource.POLYGON)

        polygon = self._get_polygon_service()
        if not polygon:
            return quote

        try:
            async with polygon:
                result = await polygon.get_underlying_price(symbol)
                if result:
                    quote.price = result.price
                    quote.close = result.close
                    quote.volume = result.volume
        except Exception as e:
            logger.error(f"Polygon stock quote error for {symbol}: {e}")

        return quote

    async def _get_stock_quote_yfinance(self, symbol: str) -> StockQuote:
        """Get stock quote from yfinance."""
        quote = StockQuote(symbol=symbol, source=DataSource.YFINANCE)

        try:
            import yfinance as yf

            ticker = yf.Ticker(symbol)
            info = ticker.info

            price = info.get("currentPrice") or info.get("regularMarketPrice")
            quote.price = Decimal(str(price)) if price else None
            quote.close = Decimal(str(info.get("previousClose"))) if info.get("previousClose") else None
            quote.volume = info.get("volume")
        except ImportError:
            logger.warning("yfinance not installed")
        except Exception as e:
            logger.error(f"yfinance stock quote error for {symbol}: {e}")

        return quote

    # =========================================================================
    # Option Quotes and Greeks
    # =========================================================================

    async def get_option_data(
        self,
        underlying: str,
        expiration: datetime,
        strike: Decimal,
        option_type: str,
    ) -> tuple[OptionQuote, OptionGreeks]:
        """Get option quote and Greeks from best available source.

        Args:
            underlying: Underlying symbol
            expiration: Expiration date
            strike: Strike price
            option_type: 'C' or 'P'

        Returns:
            Tuple of (OptionQuote, OptionGreeks)
        """
        exp_str = expiration.strftime("%Y%m%d")
        cache_key = self._cache_key("option", underlying, exp_str, str(strike), option_type)

        cached = self._get_cached(cache_key)
        if cached:
            quote, greeks = cached.data
            quote.source = DataSource.CACHED
            greeks.source = DataSource.CACHED
            return quote, greeks

        # Try IBKR first
        quote, greeks = await self._get_option_data_ibkr(
            underlying, expiration, strike, option_type
        )
        if quote.last is not None or quote.bid is not None:
            self._set_cache(cache_key, (quote, greeks), DataSource.IBKR)
            return quote, greeks

        # Fall back to Polygon
        quote, greeks = await self._get_option_data_polygon(
            underlying, expiration, strike, option_type
        )
        if quote.last is not None or greeks.delta is not None:
            self._set_cache(cache_key, (quote, greeks), DataSource.POLYGON)
            return quote, greeks

        # Fall back to yfinance
        quote, greeks = await self._get_option_data_yfinance(
            underlying, expiration, strike, option_type
        )
        if quote.last is not None:
            self._set_cache(cache_key, (quote, greeks), DataSource.YFINANCE)
            return quote, greeks

        return (
            OptionQuote(
                symbol="",
                underlying=underlying,
                strike=strike,
                expiration=expiration,
                option_type=option_type,
                source=DataSource.UNAVAILABLE,
            ),
            OptionGreeks(source=DataSource.UNAVAILABLE),
        )

    async def _get_option_data_ibkr(
        self,
        underlying: str,
        expiration: datetime,
        strike: Decimal,
        option_type: str,
    ) -> tuple[OptionQuote, OptionGreeks]:
        """Get option data from IBKR via worker process."""
        exp_str = expiration.strftime("%Y%m%d")
        quote = OptionQuote(
            symbol="",
            underlying=underlying,
            strike=strike,
            expiration=expiration,
            option_type=option_type,
            source=DataSource.IBKR,
        )
        greeks = OptionGreeks(source=DataSource.IBKR)

        worker = self._get_ibkr_worker()
        if not worker or not worker.is_running():
            return quote, greeks

        try:
            # Call worker in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                worker.get_option_data,
                underlying,
                exp_str,
                float(strike),
                option_type,
            )

            if result:
                quote.symbol = result.get("symbol", "")

                # Quote data
                if result.get("bid"):
                    quote.bid = Decimal(str(result["bid"]))
                if result.get("ask"):
                    quote.ask = Decimal(str(result["ask"]))
                if result.get("last"):
                    quote.last = Decimal(str(result["last"]))
                if result.get("mid"):
                    quote.mid = Decimal(str(result["mid"]))
                quote.volume = result.get("volume")
                quote.open_interest = result.get("open_interest")

                # Greeks from model
                g = result.get("greeks", {})
                if g.get("delta"):
                    greeks.delta = Decimal(str(g["delta"]))
                if g.get("gamma"):
                    greeks.gamma = Decimal(str(g["gamma"]))
                if g.get("theta"):
                    greeks.theta = Decimal(str(g["theta"]))
                if g.get("vega"):
                    greeks.vega = Decimal(str(g["vega"]))
                if g.get("iv"):
                    greeks.iv = Decimal(str(g["iv"]))

        except Exception as e:
            logger.error(f"IBKR option data error: {e}")

        return quote, greeks

    async def _get_option_data_polygon(
        self,
        underlying: str,
        expiration: datetime,
        strike: Decimal,
        option_type: str,
    ) -> tuple[OptionQuote, OptionGreeks]:
        """Get option data from Polygon."""
        quote = OptionQuote(
            symbol="",
            underlying=underlying,
            strike=strike,
            expiration=expiration,
            option_type=option_type,
            source=DataSource.POLYGON,
        )
        greeks = OptionGreeks(source=DataSource.POLYGON)

        polygon = self._get_polygon_service()
        if not polygon:
            return quote, greeks

        try:
            async with polygon:
                result = await polygon.get_option_greeks(
                    underlying=underlying,
                    expiration=expiration,
                    option_type=option_type,
                    strike=strike,
                    fetch_underlying_price=False,
                )

                if result:
                    quote.last = result.option_price
                    quote.bid = result.bid
                    quote.ask = result.ask
                    if quote.bid and quote.ask:
                        quote.mid = (quote.bid + quote.ask) / 2
                    quote.open_interest = result.open_interest
                    quote.volume = result.volume

                    greeks.delta = result.delta
                    greeks.gamma = result.gamma
                    greeks.theta = result.theta
                    greeks.vega = result.vega
                    greeks.iv = result.iv
        except Exception as e:
            logger.error(f"Polygon option data error: {e}")

        return quote, greeks

    async def _get_option_data_yfinance(
        self,
        underlying: str,
        expiration: datetime,
        strike: Decimal,
        option_type: str,
    ) -> tuple[OptionQuote, OptionGreeks]:
        """Get option data from yfinance."""
        quote = OptionQuote(
            symbol="",
            underlying=underlying,
            strike=strike,
            expiration=expiration,
            option_type=option_type,
            source=DataSource.YFINANCE,
        )
        greeks = OptionGreeks(source=DataSource.YFINANCE)

        try:
            import yfinance as yf

            ticker = yf.Ticker(underlying)
            exp_str = expiration.strftime("%Y-%m-%d")

            if exp_str in ticker.options:
                chain = ticker.option_chain(exp_str)
                options = chain.calls if option_type == "C" else chain.puts

                # Find matching strike
                match = options[options["strike"] == float(strike)]
                if not match.empty:
                    row = match.iloc[0]
                    quote.last = Decimal(str(row["lastPrice"])) if row["lastPrice"] else None
                    quote.bid = Decimal(str(row["bid"])) if row["bid"] else None
                    quote.ask = Decimal(str(row["ask"])) if row["ask"] else None
                    if quote.bid and quote.ask:
                        quote.mid = (quote.bid + quote.ask) / 2
                    quote.volume = int(row["volume"]) if row["volume"] else None
                    quote.open_interest = int(row["openInterest"]) if row["openInterest"] else None

                    # yfinance provides IV but not other Greeks
                    if row["impliedVolatility"]:
                        greeks.iv = Decimal(str(row["impliedVolatility"]))
        except ImportError:
            logger.warning("yfinance not installed")
        except Exception as e:
            logger.error(f"yfinance option data error: {e}")

        return quote, greeks

    # =========================================================================
    # Portfolio Data (IBKR only)
    # =========================================================================

    async def get_portfolio_positions(self) -> list[dict]:
        """Get all portfolio positions from IBKR with market data.

        Returns:
            List of position dictionaries with market values and P&L
        """
        worker = self._get_ibkr_worker()
        if not worker or not worker.is_running():
            return []

        try:
            # Call worker in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            positions = await loop.run_in_executor(None, worker.get_portfolio)

            # Convert to Decimal where needed
            for pos in positions:
                if pos.get("strike"):
                    pos["strike"] = Decimal(str(pos["strike"]))
                if pos.get("market_price"):
                    pos["market_price"] = Decimal(str(pos["market_price"]))
                if pos.get("market_value"):
                    pos["market_value"] = Decimal(str(pos["market_value"]))
                if pos.get("avg_cost"):
                    pos["avg_cost"] = Decimal(str(pos["avg_cost"]))
                if pos.get("unrealized_pnl"):
                    pos["unrealized_pnl"] = Decimal(str(pos["unrealized_pnl"]))
                if pos.get("realized_pnl"):
                    pos["realized_pnl"] = Decimal(str(pos["realized_pnl"]))

            return positions

        except Exception as e:
            logger.error(f"Error getting portfolio: {e}")
            return []

    async def get_account_pnl(self) -> dict:
        """Get account-level P&L from IBKR.

        Returns:
            Dictionary with daily, unrealized, and realized P&L
        """
        worker = self._get_ibkr_worker()
        if not worker or not worker.is_running():
            return {}

        try:
            # Call worker in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            pnl = await loop.run_in_executor(None, worker.get_account_pnl)

            if pnl:
                # Convert to Decimal where needed
                if pnl.get("daily_pnl"):
                    pnl["daily_pnl"] = Decimal(str(pnl["daily_pnl"]))
                if pnl.get("unrealized_pnl"):
                    pnl["unrealized_pnl"] = Decimal(str(pnl["unrealized_pnl"]))
                if pnl.get("realized_pnl"):
                    pnl["realized_pnl"] = Decimal(str(pnl["realized_pnl"]))
                return pnl

            return {}

        except Exception as e:
            logger.error(f"Error getting account P&L: {e}")
            return {}

    # =========================================================================
    # Trade/Position Market Data
    # =========================================================================

    async def get_position_market_data(
        self,
        trade_id: int,
        underlying: str,
        legs: list[dict],
        cost_basis: Decimal,
    ) -> PositionMarketData:
        """Get market data for a trade/position with multiple legs.

        Args:
            trade_id: Trade ID
            underlying: Underlying symbol
            legs: List of leg dictionaries with strike, expiration, option_type, quantity
            cost_basis: Total cost basis for the position

        Returns:
            PositionMarketData with aggregated values
        """
        result = PositionMarketData(
            trade_id=trade_id,
            underlying=underlying,
            total_cost_basis=cost_basis,
        )

        # Get underlying price
        stock_quote = await self.get_stock_quote(underlying)
        result.underlying_price = stock_quote.price
        result.source = stock_quote.source

        total_market_value = Decimal("0")
        net_delta = Decimal("0")
        net_gamma = Decimal("0")
        net_theta = Decimal("0")
        net_vega = Decimal("0")
        all_legs_priced = True

        for leg in legs:
            expiration = leg.get("expiration")
            if isinstance(expiration, str):
                expiration = datetime.strptime(expiration, "%Y%m%d")

            strike = Decimal(str(leg["strike"]))
            option_type = leg["option_type"]
            quantity = leg["quantity"]
            multiplier = leg.get("multiplier", 100)

            quote, greeks = await self.get_option_data(
                underlying=underlying,
                expiration=expiration,
                strike=strike,
                option_type=option_type,
            )

            # Calculate leg market value
            leg_price = quote.mid or quote.last
            if leg_price:
                leg_market_value = leg_price * quantity * multiplier
                total_market_value += leg_market_value
            else:
                all_legs_priced = False

            # Aggregate Greeks (weighted by quantity)
            if greeks.delta:
                net_delta += greeks.delta * quantity
            if greeks.gamma:
                net_gamma += greeks.gamma * quantity
            if greeks.theta:
                net_theta += greeks.theta * quantity
            if greeks.vega:
                net_vega += greeks.vega * quantity

            result.legs.append({
                "strike": float(strike),
                "expiration": expiration.strftime("%Y-%m-%d"),
                "option_type": option_type,
                "quantity": quantity,
                "price": float(leg_price) if leg_price else None,
                "market_value": float(leg_market_value) if leg_price else None,
                "delta": float(greeks.delta) if greeks.delta else None,
                "gamma": float(greeks.gamma) if greeks.gamma else None,
                "theta": float(greeks.theta) if greeks.theta else None,
                "vega": float(greeks.vega) if greeks.vega else None,
                "iv": float(greeks.iv) if greeks.iv else None,
                "source": greeks.source.value,
            })

        if all_legs_priced:
            result.total_market_value = total_market_value
            result.unrealized_pnl = total_market_value - cost_basis
            if cost_basis != 0:
                result.unrealized_pnl_percent = (result.unrealized_pnl / abs(cost_basis)) * 100

        result.net_delta = net_delta if net_delta else None
        result.net_gamma = net_gamma if net_gamma else None
        result.net_theta = net_theta if net_theta else None
        result.net_vega = net_vega if net_vega else None
        result.is_stale = stock_quote.source == DataSource.CACHED

        return result

    # =========================================================================
    # Context Manager
    # =========================================================================

    async def __aenter__(self) -> "MarketDataService":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.disconnect_ibkr()
