"""FRED API service for fetching risk-free rate data."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx

from trading_journal.config import get_settings

logger = logging.getLogger(__name__)

# FRED API base URL
FRED_BASE_URL = "https://api.stlouisfed.org/fred"

# Default risk-free rate fallback (5%)
DEFAULT_RISK_FREE_RATE = Decimal("0.05")

# Cache duration (24 hours)
CACHE_DURATION_HOURS = 24

# 3-Month Treasury Bill rate series ID
TREASURY_3M_SERIES = "DTB3"


@dataclass
class RiskFreeRate:
    """Risk-free rate data."""

    rate: Decimal  # Annualized rate as decimal (e.g., 0.05 for 5%)
    series_id: str
    observation_date: datetime
    fetched_at: datetime
    source: str  # "FRED" or "FALLBACK"


class FredServiceError(Exception):
    """Base exception for FRED service errors."""

    pass


class FredAPIError(FredServiceError):
    """API error from FRED."""

    pass


class FredService:
    """Service for fetching risk-free rate from FRED API.

    Uses the 3-month Treasury Bill rate (DTB3) as the risk-free rate
    for options pricing calculations. Results are cached for 24 hours.
    Falls back to a default rate if the API is unavailable.
    """

    def __init__(self, api_key: str | None = None):
        """Initialize FRED service.

        Args:
            api_key: FRED API key. If not provided, reads from settings.
                    Note: FRED API works without a key for basic access,
                    but rate limits are more restrictive.
        """
        settings = get_settings()
        self.api_key = api_key or settings.fred_api_key
        self._client: httpx.AsyncClient | None = None
        self._cache: dict[str, RiskFreeRate] = {}
        self._cache_expiry: dict[str, datetime] = {}

    async def __aenter__(self) -> "FredService":
        """Async context manager entry."""
        self._client = httpx.AsyncClient(
            base_url=FRED_BASE_URL,
            timeout=30.0,
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
                base_url=FRED_BASE_URL,
                timeout=30.0,
            )
        return self._client

    def _is_cache_valid(self, series_id: str) -> bool:
        """Check if cached data is still valid."""
        if series_id not in self._cache:
            return False
        expiry = self._cache_expiry.get(series_id)
        if expiry is None:
            return False
        return datetime.now(UTC) < expiry

    def _get_cached(self, series_id: str) -> RiskFreeRate | None:
        """Get cached rate if valid."""
        if self._is_cache_valid(series_id):
            return self._cache[series_id]
        return None

    def _set_cache(self, series_id: str, rate: RiskFreeRate) -> None:
        """Cache rate data."""
        self._cache[series_id] = rate
        self._cache_expiry[series_id] = datetime.now(UTC) + timedelta(hours=CACHE_DURATION_HOURS)

    async def get_risk_free_rate(
        self,
        series_id: str = TREASURY_3M_SERIES,
        use_cache: bool = True,
    ) -> RiskFreeRate:
        """Fetch the current risk-free rate.

        Uses the 3-month Treasury Bill rate by default. Results are cached
        for 24 hours. Falls back to a default rate if the API fails.

        Args:
            series_id: FRED series ID (default: DTB3 for 3-month T-bill)
            use_cache: Whether to use cached data if available

        Returns:
            RiskFreeRate object with current rate
        """
        # Check cache first
        if use_cache:
            cached = self._get_cached(series_id)
            if cached:
                logger.debug(f"Using cached risk-free rate: {cached.rate}")
                return cached

        # Try to fetch from FRED
        try:
            rate = await self._fetch_rate(series_id)
            self._set_cache(series_id, rate)
            return rate
        except FredServiceError as e:
            logger.warning(f"Failed to fetch risk-free rate from FRED: {e}")
            # Return fallback rate
            return self._get_fallback_rate()

    async def _fetch_rate(self, series_id: str) -> RiskFreeRate:
        """Fetch rate from FRED API.

        Args:
            series_id: FRED series ID

        Returns:
            RiskFreeRate object

        Raises:
            FredAPIError: If API request fails
        """
        client = await self._ensure_client()

        params = {
            "series_id": series_id,
            "file_type": "json",
            "sort_order": "desc",
            "limit": "1",
        }

        # Add API key if available
        if self.api_key:
            params["api_key"] = self.api_key

        try:
            response = await client.get("/series/observations", params=params)

            if response.status_code == 400:
                data = response.json()
                error_msg = data.get("error_message", "Bad request")
                raise FredAPIError(f"FRED API error: {error_msg}")

            if response.status_code == 429:
                raise FredAPIError("FRED API rate limit exceeded")

            response.raise_for_status()
            data = response.json()

        except httpx.HTTPStatusError as e:
            raise FredAPIError(f"HTTP error: {e.response.status_code}") from e
        except httpx.RequestError as e:
            raise FredAPIError(f"Request failed: {e}") from e

        observations = data.get("observations", [])
        if not observations:
            raise FredAPIError(f"No observations found for series {series_id}")

        # Get the most recent observation
        latest = observations[0]
        value = latest.get("value")

        # Handle missing or invalid data (FRED uses "." for missing values)
        if value is None or value == ".":
            raise FredAPIError(f"No valid rate data for series {series_id}")

        # FRED returns rate as percentage (e.g., 4.5 for 4.5%)
        # Convert to decimal (e.g., 0.045)
        rate_percent = Decimal(value)
        rate_decimal = rate_percent / Decimal("100")

        observation_date = datetime.strptime(latest["date"], "%Y-%m-%d")

        return RiskFreeRate(
            rate=rate_decimal,
            series_id=series_id,
            observation_date=observation_date.replace(tzinfo=UTC),
            fetched_at=datetime.now(UTC),
            source="FRED",
        )

    def _get_fallback_rate(self) -> RiskFreeRate:
        """Get fallback risk-free rate when API is unavailable."""
        return RiskFreeRate(
            rate=DEFAULT_RISK_FREE_RATE,
            series_id="FALLBACK",
            observation_date=datetime.now(UTC),
            fetched_at=datetime.now(UTC),
            source="FALLBACK",
        )

    async def get_treasury_rates(self) -> dict[str, RiskFreeRate]:
        """Fetch multiple treasury rates for different maturities.

        Returns:
            Dictionary of rates by maturity
        """
        series_ids = {
            "1M": "DTB4WK",   # 4-week T-bill
            "3M": "DTB3",     # 3-month T-bill
            "6M": "DTB6",     # 6-month T-bill
            "1Y": "DTB1YR",   # 1-year T-bill
        }

        rates = {}
        for maturity, series_id in series_ids.items():
            try:
                rates[maturity] = await self.get_risk_free_rate(series_id)
            except FredServiceError:
                rates[maturity] = self._get_fallback_rate()

        return rates

    def clear_cache(self) -> None:
        """Clear the rate cache."""
        self._cache.clear()
        self._cache_expiry.clear()

    async def check_api_status(self) -> bool:
        """Check if FRED API is accessible.

        Returns:
            True if API is accessible, False otherwise
        """
        try:
            await self._fetch_rate(TREASURY_3M_SERIES)
            return True
        except FredServiceError:
            return False
