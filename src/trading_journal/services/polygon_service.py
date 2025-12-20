"""Polygon.io API service for fetching options Greeks and market data."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

import httpx

from trading_journal.config import get_settings

logger = logging.getLogger(__name__)

# Polygon API base URL
POLYGON_BASE_URL = "https://api.polygon.io"

# Rate limiting: Options Starter tier allows 5 calls/minute
RATE_LIMIT_CALLS = 5
RATE_LIMIT_PERIOD = 60  # seconds


@dataclass
class OptionGreeks:
    """Greeks data for an option contract."""

    delta: Decimal | None
    gamma: Decimal | None
    theta: Decimal | None
    vega: Decimal | None
    rho: Decimal | None
    iv: Decimal | None  # Implied volatility
    underlying_price: Decimal | None
    option_price: Decimal | None
    bid: Decimal | None
    ask: Decimal | None
    bid_ask_spread: Decimal | None
    open_interest: int | None
    volume: int | None
    timestamp: datetime | None


@dataclass
class UnderlyingQuote:
    """Quote data for an underlying asset."""

    symbol: str
    price: Decimal
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    volume: int | None
    timestamp: datetime | None


class PolygonServiceError(Exception):
    """Base exception for Polygon service errors."""

    pass


class PolygonRateLimitError(PolygonServiceError):
    """Rate limit exceeded."""

    pass


class PolygonAPIError(PolygonServiceError):
    """API error from Polygon."""

    pass


class PolygonService:
    """Service for interacting with Polygon.io API.

    Provides methods for fetching options Greeks, IV, and underlying prices.
    Includes rate limiting to stay within the Options Starter tier limits.
    """

    def __init__(self, api_key: str | None = None):
        """Initialize Polygon service.

        Args:
            api_key: Polygon API key. If not provided, reads from settings.
        """
        settings = get_settings()
        self.api_key = api_key or settings.polygon_api_key

        if not self.api_key:
            raise PolygonServiceError("Polygon API key not configured")

        self._client: httpx.AsyncClient | None = None
        self._call_times: list[float] = []

    async def __aenter__(self) -> "PolygonService":
        """Async context manager entry."""
        self._client = httpx.AsyncClient(
            base_url=POLYGON_BASE_URL,
            timeout=30.0,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure HTTP client is available."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=POLYGON_BASE_URL,
                timeout=30.0,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        return self._client

    async def _rate_limit(self) -> None:
        """Enforce rate limiting."""
        now = asyncio.get_event_loop().time()

        # Remove calls older than the rate limit period
        self._call_times = [t for t in self._call_times if now - t < RATE_LIMIT_PERIOD]

        # If at limit, wait
        if len(self._call_times) >= RATE_LIMIT_CALLS:
            wait_time = RATE_LIMIT_PERIOD - (now - self._call_times[0])
            if wait_time > 0:
                logger.warning(f"Rate limit reached, waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
                self._call_times = []

        self._call_times.append(now)

    async def _request(self, method: str, endpoint: str, **kwargs) -> dict[str, Any]:
        """Make a rate-limited API request.

        Args:
            method: HTTP method
            endpoint: API endpoint
            **kwargs: Additional request arguments

        Returns:
            JSON response data

        Raises:
            PolygonRateLimitError: If rate limited by API
            PolygonAPIError: If API returns an error
        """
        await self._rate_limit()
        client = await self._ensure_client()

        try:
            response = await client.request(method, endpoint, **kwargs)

            if response.status_code == 429:
                raise PolygonRateLimitError("Polygon API rate limit exceeded")

            if response.status_code == 403:
                raise PolygonAPIError("Invalid API key or insufficient permissions")

            if response.status_code == 404:
                return {}  # No data found

            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            raise PolygonAPIError(f"HTTP error: {e.response.status_code}") from e
        except httpx.RequestError as e:
            raise PolygonAPIError(f"Request failed: {e}") from e

    def _build_option_ticker(
        self,
        underlying: str,
        expiration: datetime,
        option_type: str,
        strike: Decimal,
    ) -> str:
        """Build OCC option ticker symbol.

        Format: O:UNDERLYING YYMMDD C/P STRIKE (with strike * 1000, zero-padded to 8 digits)
        Example: O:SPY251219C00600000 for SPY Dec 19 2025 600 Call

        Args:
            underlying: Underlying symbol (e.g., "SPY")
            expiration: Option expiration date
            option_type: "C" for call, "P" for put
            strike: Strike price

        Returns:
            OCC-formatted option ticker
        """
        date_str = expiration.strftime("%y%m%d")
        strike_int = int(strike * 1000)
        strike_str = f"{strike_int:08d}"
        return f"O:{underlying}{date_str}{option_type}{strike_str}"

    async def get_option_greeks(
        self,
        underlying: str,
        expiration: datetime,
        option_type: str,
        strike: Decimal,
        fetch_underlying_price: bool = True,
    ) -> OptionGreeks | None:
        """Fetch Greeks and market data for an option contract.

        Uses the Polygon Options Snapshot endpoint.

        Args:
            underlying: Underlying symbol (e.g., "SPY")
            expiration: Option expiration date
            option_type: "C" for call, "P" for put
            strike: Strike price
            fetch_underlying_price: If True, also fetch current underlying price

        Returns:
            OptionGreeks object or None if not found
        """
        option_ticker = self._build_option_ticker(underlying, expiration, option_type, strike)

        # Use the universal snapshot endpoint
        endpoint = f"/v3/snapshot/options/{underlying}/{option_ticker}"

        try:
            data = await self._request("GET", endpoint)
        except PolygonAPIError as e:
            logger.error(f"Failed to fetch Greeks for {option_ticker}: {e}")
            return None

        if not data or "results" not in data:
            logger.warning(f"No data found for option {option_ticker}")
            return None

        result = data["results"]
        greeks_data = result.get("greeks", {})
        day_data = result.get("day", {})
        last_quote = result.get("last_quote", {})

        bid = Decimal(str(last_quote.get("bid", 0))) if last_quote.get("bid") else None
        ask = Decimal(str(last_quote.get("ask", 0))) if last_quote.get("ask") else None

        # Fetch underlying price separately if requested (not included in option snapshot)
        underlying_price = None
        if fetch_underlying_price:
            quote = await self.get_underlying_price(underlying)
            if quote:
                underlying_price = quote.price

        return OptionGreeks(
            delta=Decimal(str(greeks_data["delta"])) if greeks_data.get("delta") else None,
            gamma=Decimal(str(greeks_data["gamma"])) if greeks_data.get("gamma") else None,
            theta=Decimal(str(greeks_data["theta"])) if greeks_data.get("theta") else None,
            vega=Decimal(str(greeks_data["vega"])) if greeks_data.get("vega") else None,
            rho=None,  # Polygon doesn't provide rho
            iv=Decimal(str(result["implied_volatility"])) if result.get("implied_volatility") else None,
            underlying_price=underlying_price,
            option_price=Decimal(str(day_data["close"])) if day_data.get("close") else None,
            bid=bid,
            ask=ask,
            bid_ask_spread=ask - bid if bid and ask else None,
            open_interest=result.get("open_interest"),
            volume=day_data.get("volume"),
            timestamp=datetime.now(),
        )

    async def get_underlying_price(self, symbol: str) -> UnderlyingQuote | None:
        """Fetch previous close price for an underlying asset.

        Args:
            symbol: Ticker symbol (e.g., "SPY")

        Returns:
            UnderlyingQuote object or None if not found
        """
        endpoint = f"/v2/aggs/ticker/{symbol}/prev"

        try:
            data = await self._request("GET", endpoint, params={"adjusted": "true"})
        except PolygonAPIError as e:
            logger.error(f"Failed to fetch price for {symbol}: {e}")
            return None

        if not data or "results" not in data or not data["results"]:
            logger.warning(f"No price data found for {symbol}")
            return None

        result = data["results"][0]

        return UnderlyingQuote(
            symbol=symbol,
            price=Decimal(str(result["c"])),  # close price
            open=Decimal(str(result["o"])) if result.get("o") else None,
            high=Decimal(str(result["h"])) if result.get("h") else None,
            low=Decimal(str(result["l"])) if result.get("l") else None,
            close=Decimal(str(result["c"])) if result.get("c") else None,
            volume=result.get("v"),
            timestamp=datetime.fromtimestamp(result["t"] / 1000) if result.get("t") else None,
        )

    async def get_option_chain_snapshot(
        self,
        underlying: str,
        expiration_date: datetime | None = None,
        strike_price_gte: Decimal | None = None,
        strike_price_lte: Decimal | None = None,
        contract_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Fetch option chain snapshot for an underlying.

        Args:
            underlying: Underlying symbol
            expiration_date: Filter by expiration date
            strike_price_gte: Minimum strike price
            strike_price_lte: Maximum strike price
            contract_type: "call" or "put"
            limit: Maximum results (max 250)

        Returns:
            List of option contract data
        """
        endpoint = f"/v3/snapshot/options/{underlying}"

        params: dict[str, Any] = {"limit": min(limit, 250)}

        if expiration_date:
            params["expiration_date"] = expiration_date.strftime("%Y-%m-%d")
        if strike_price_gte:
            params["strike_price.gte"] = float(strike_price_gte)
        if strike_price_lte:
            params["strike_price.lte"] = float(strike_price_lte)
        if contract_type:
            params["contract_type"] = contract_type

        try:
            data = await self._request("GET", endpoint, params=params)
        except PolygonAPIError as e:
            logger.error(f"Failed to fetch option chain for {underlying}: {e}")
            return []

        return data.get("results", [])

    async def get_option_contract_details(self, option_ticker: str) -> dict[str, Any] | None:
        """Fetch contract details for a specific option.

        Args:
            option_ticker: OCC option ticker (e.g., "O:SPY251219C00600000")

        Returns:
            Contract details or None
        """
        # Remove "O:" prefix if present for the reference endpoint
        ticker = option_ticker.replace("O:", "")
        endpoint = f"/v3/reference/options/contracts/{ticker}"

        try:
            data = await self._request("GET", endpoint)
        except PolygonAPIError as e:
            logger.error(f"Failed to fetch contract details for {option_ticker}: {e}")
            return None

        return data.get("results")

    async def check_api_status(self) -> dict[str, bool]:
        """Check API key validity and subscription tier.

        Returns:
            Dictionary with access levels:
            - "basic": True if basic stock data is accessible
            - "options": True if options data is accessible (requires Options Starter tier)
        """
        status = {"basic": False, "options": False}

        try:
            # Test basic access with stock quote
            data = await self._request("GET", "/v2/aggs/ticker/SPY/prev")
            status["basic"] = "results" in data
        except PolygonServiceError:
            return status

        try:
            # Test options access with options chain
            data = await self._request("GET", "/v3/snapshot/options/SPY", params={"limit": 1})
            status["options"] = "results" in data and len(data.get("results", [])) > 0
        except PolygonAPIError as e:
            # 403 means no options subscription
            if "403" in str(e) or "insufficient permissions" in str(e).lower():
                status["options"] = False
            else:
                raise

        return status

    async def has_options_access(self) -> bool:
        """Check if API key has options data access.

        Returns:
            True if options endpoints are accessible
        """
        status = await self.check_api_status()
        return status.get("options", False)

    async def get_stock_candles(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timespan: str = "day",
        multiplier: int = 1,
    ) -> list[dict[str, Any]]:
        """Fetch OHLC candle data for a stock.

        Args:
            symbol: Stock ticker symbol (e.g., "SPY")
            start_date: Start date for candles
            end_date: End date for candles
            timespan: Candle timespan ("minute", "hour", "day", "week", "month")
            multiplier: Timespan multiplier (e.g., 5 for 5-minute candles)

        Returns:
            List of candle dictionaries with timestamp, open, high, low, close, volume
        """
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        endpoint = f"/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{start_str}/{end_str}"

        try:
            data = await self._request(
                "GET",
                endpoint,
                params={"adjusted": "true", "sort": "desc", "limit": 5000},
            )
        except PolygonAPIError as e:
            logger.error(f"Failed to fetch candles for {symbol}: {e}")
            return []

        if not data or "results" not in data:
            logger.warning(f"No candle data found for {symbol}")
            return []

        candles = []
        for bar in data["results"]:
            candles.append({
                "timestamp": datetime.fromtimestamp(bar["t"] / 1000),
                "open": Decimal(str(bar["o"])),
                "high": Decimal(str(bar["h"])),
                "low": Decimal(str(bar["l"])),
                "close": Decimal(str(bar["c"])),
                "volume": bar.get("v"),
            })

        # Reverse to chronological order (API returns desc for most recent data first)
        candles.reverse()
        return candles
