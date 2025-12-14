"""Service for fetching executions from IBKR Flex Query API."""

import csv
import io
import xml.etree.ElementTree as ET
from datetime import datetime
from decimal import Decimal
from typing import Any

import httpx

from trading_journal.config import get_settings

settings = get_settings()

# IBKR Flex Query API endpoints
FLEX_REQUEST_URL = "https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest"
FLEX_FETCH_URL = "https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.GetStatement"


class FlexQueryService:
    """Service for fetching executions from IBKR Flex Query API."""

    def __init__(self, token: str | None = None, query_id: str | None = None):
        """Initialize the service.

        Args:
            token: IBKR Flex Web Service token (defaults to config)
            query_id: Flex Query ID (defaults to config, which is 1348073)
        """
        self.token = token or settings.ibkr_flex_token
        self.query_id = query_id or settings.ibkr_flex_query_id

        if not self.token:
            raise ValueError(
                "IBKR Flex Token not configured. "
                "Set IBKR_FLEX_TOKEN in environment or .env file."
            )

    async def fetch_executions(self, max_retries: int = 30) -> list[dict[str, Any]]:
        """Fetch executions from IBKR Flex Query.

        Args:
            max_retries: Maximum retries when waiting for report generation

        Returns:
            List of execution dictionaries

        Raises:
            ConnectionError: If unable to connect to IBKR
            ValueError: If response parsing fails
        """
        # Step 1: Request the report
        reference_code = await self._request_report()

        # Step 2: Fetch the report (with retries as it takes time to generate)
        report_content = await self._fetch_report(reference_code, max_retries)

        # Step 3: Parse executions from report (CSV or XML)
        executions = self._parse_executions(report_content)

        return executions

    async def _request_report(self) -> str:
        """Request a Flex Query report.

        Returns:
            Reference code for fetching the report

        Raises:
            ConnectionError: If request fails
            ValueError: If IBKR returns an error
        """
        params = {
            "t": self.token,
            "q": self.query_id,
            "v": "3",
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    FLEX_REQUEST_URL, params=params, timeout=30.0
                )
                response.raise_for_status()

                # Parse XML response
                root = ET.fromstring(response.content)

                status = root.find(".//Status")
                if status is not None and status.text == "Success":
                    reference_code = root.find(".//ReferenceCode")
                    if reference_code is not None:
                        return reference_code.text
                    raise ValueError("No reference code in response")
                else:
                    error_code = root.find(".//ErrorCode")
                    error_msg = root.find(".//ErrorMessage")
                    error_text = (
                        f"{error_code.text if error_code is not None else 'Unknown'}"
                        f" - {error_msg.text if error_msg is not None else 'Unknown error'}"
                    )
                    raise ValueError(f"IBKR error: {error_text}")

            except httpx.RequestError as e:
                raise ConnectionError(f"Failed to request Flex Query: {e}")
            except ET.ParseError as e:
                raise ValueError(f"Failed to parse IBKR response: {e}")

    async def _fetch_report(
        self, reference_code: str, max_retries: int
    ) -> str:
        """Fetch the generated Flex Query report.

        Args:
            reference_code: Reference code from request step
            max_retries: Maximum number of retries

        Returns:
            Report content as string (CSV or XML)

        Raises:
            ConnectionError: If request fails
            ValueError: If report generation times out or fails
        """
        params = {
            "t": self.token,
            "q": reference_code,
            "v": "3",
        }

        async with httpx.AsyncClient() as client:
            for _attempt in range(max_retries):
                try:
                    response = await client.get(
                        FLEX_FETCH_URL, params=params, timeout=30.0
                    )
                    response.raise_for_status()

                    content = response.text

                    # Check if still generating
                    if (
                        "Statement generation in progress" in content
                        or "Statement is being generated" in content
                    ):
                        await self._sleep(3)
                        continue

                    # Check for XML error response
                    if content.startswith("<?xml"):
                        try:
                            root = ET.fromstring(content)
                            status = root.find(".//Status")
                            if status is not None and status.text != "Success":
                                error_code = root.find(".//ErrorCode")
                                error_msg = root.find(".//ErrorMessage")
                                if error_code is not None:
                                    raise ValueError(
                                        f"IBKR error: {error_code.text} - "
                                        f"{error_msg.text if error_msg is not None else 'Unknown'}"
                                    )
                        except ET.ParseError:
                            pass

                    # Check if we have actual data (CSV starts with quotes or XML with data)
                    if content.startswith('"') or (content.startswith("<?xml") and "<Trade" in content):
                        return content

                    # Unknown response, wait and retry
                    await self._sleep(3)

                except httpx.RequestError as e:
                    raise ConnectionError(f"Failed to fetch Flex Query report: {e}")

            raise ValueError(
                f"Report not ready after {max_retries} attempts. "
                "The query may be too large or IBKR servers are slow."
            )

    async def _sleep(self, seconds: float):
        """Sleep asynchronously."""
        import asyncio

        await asyncio.sleep(seconds)

    def _parse_executions(self, report_content: str) -> list[dict[str, Any]]:
        """Parse executions from Flex Query report (CSV or XML).

        Args:
            report_content: Report content as string

        Returns:
            List of execution dictionaries
        """
        executions = []

        if report_content.startswith('"'):
            # CSV format
            reader = csv.DictReader(io.StringIO(report_content))
            for row in reader:
                execution = self._parse_csv_row(row)
                if execution:
                    executions.append(execution)
        else:
            # XML format
            root = ET.fromstring(report_content)
            trades = root.findall(".//Trade")
            for trade in trades:
                execution = self._parse_trade_element(trade)
                if execution:
                    executions.append(execution)

        return executions

    def _parse_csv_row(self, row: dict[str, str]) -> dict[str, Any] | None:
        """Parse a CSV row into execution dictionary.

        Args:
            row: CSV row as dictionary

        Returns:
            Execution dictionary or None if parsing fails
        """
        try:
            # Parse datetime
            dt_str = row.get("DateTime", "")
            execution_time = None
            if dt_str:
                for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d, %H:%M:%S", "%Y%m%d;%H%M%S"]:
                    try:
                        execution_time = datetime.strptime(dt_str, fmt)
                        break
                    except ValueError:
                        continue

            # Determine asset class
            asset_class = row.get("AssetClass", "")
            security_type = "OPT" if asset_class == "OPT" else "STK"

            # Get underlying symbol
            underlying = row.get("UnderlyingSymbol", "") or row.get("Symbol", "")

            # Parse IDs
            try:
                order_id = int(row.get("IBOrderID", 0) or 0)
            except (ValueError, TypeError):
                order_id = 0

            try:
                trade_id = int(row.get("TradeID", 0) or 0)
            except (ValueError, TypeError):
                trade_id = 0

            # Parse numeric fields
            try:
                quantity = abs(int(float(row.get("Quantity", 0) or 0)))
            except (ValueError, TypeError):
                quantity = 0

            try:
                price = Decimal(str(row.get("TradePrice", 0) or 0))
            except:
                price = Decimal("0")

            try:
                commission = abs(Decimal(str(row.get("IBCommission", 0) or 0)))
            except:
                commission = Decimal("0")

            try:
                net_cash = Decimal(str(row.get("NetCash", 0) or 0))
            except:
                net_cash = Decimal("0")

            # Parse open/close indicator (take first character if compound like "C;O")
            open_close = row.get("Open/CloseIndicator", "") or ""
            if open_close and len(open_close) > 1:
                open_close = open_close[0]  # Take first character (O or C)

            # Base execution data
            execution = {
                "exec_id": row.get("IBExecID", "") or f"CSV_{trade_id}_{order_id}",
                "order_id": order_id,
                "perm_id": trade_id,
                "execution_time": execution_time,
                "underlying": underlying,
                "security_type": security_type,
                "exchange": row.get("Exchange", "SMART") or "SMART",
                "currency": row.get("CurrencyPrimary", "USD") or "USD",
                "side": "BOT" if row.get("Buy/Sell", "").upper() == "BUY" else "SLD",
                "open_close_indicator": open_close if open_close else None,
                "quantity": quantity,
                "price": price,
                "commission": commission,
                "net_amount": net_cash,
                "account_id": row.get("ClientAccountID", "FLEX_IMPORT") or "FLEX_IMPORT",
            }

            # Option-specific fields
            if security_type == "OPT":
                expiry_str = row.get("Expiry", "")
                expiration = None
                if expiry_str:
                    for fmt in ["%Y-%m-%d", "%Y%m%d"]:
                        try:
                            expiration = datetime.strptime(expiry_str, fmt)
                            break
                        except ValueError:
                            continue

                try:
                    strike = Decimal(str(row.get("Strike", 0) or 0))
                except:
                    strike = None

                try:
                    multiplier = int(float(row.get("Multiplier", 100) or 100))
                except:
                    multiplier = 100

                execution.update({
                    "option_type": row.get("Put/Call", ""),
                    "strike": strike,
                    "expiration": expiration,
                    "multiplier": multiplier,
                })
            else:
                execution.update({
                    "option_type": None,
                    "strike": None,
                    "expiration": None,
                    "multiplier": None,
                })

            return execution

        except Exception as e:
            print(f"Error parsing CSV row: {e}")
            return None

    def _parse_trade_element(self, trade: ET.Element) -> dict[str, Any] | None:
        """Parse a Trade XML element.

        Args:
            trade: XML Trade element

        Returns:
            Execution dictionary or None if parsing fails
        """
        try:
            # Parse datetime
            dt_str = trade.get("dateTime", "")
            if ";" in dt_str:
                dt_str = dt_str.split(";")[0]  # Remove timezone part

            execution_time = None
            if dt_str:
                # Try multiple formats
                for fmt in ["%Y%m%d;%H%M%S", "%Y%m%d%H%M%S", "%Y-%m-%d %H:%M:%S"]:
                    try:
                        execution_time = datetime.strptime(dt_str, fmt)
                        break
                    except ValueError:
                        continue

            # Parse IDs
            try:
                order_id = int(trade.get("ibOrderID", 0))
            except (ValueError, TypeError):
                order_id = 0

            try:
                perm_id = int(trade.get("tradeID", 0))
            except (ValueError, TypeError):
                perm_id = 0

            # Base execution data
            execution = {
                "exec_id": trade.get("ibExecID", ""),
                "order_id": order_id,
                "perm_id": perm_id,
                "execution_time": execution_time,
                "underlying": trade.get("symbol", ""),
                "security_type": "OPT" if trade.get("assetCategory") == "OPT" else "STK",
                "exchange": trade.get("exchange", "SMART"),
                "currency": trade.get("currency", "USD"),
                "side": "BOT" if trade.get("buySell") == "BUY" else "SLD",
                "open_close_indicator": trade.get("openCloseIndicator", None),
                "quantity": abs(int(float(trade.get("quantity", 0)))),
                "price": Decimal(str(trade.get("tradePrice", 0))),
                "commission": abs(Decimal(str(trade.get("ibCommission", 0)))),
                "net_amount": Decimal(str(trade.get("netCash", 0))),
                "account_id": trade.get("accountId", "FLEX_IMPORT"),
            }

            # Option-specific fields
            if execution["security_type"] == "OPT":
                expiry_str = trade.get("expiry", "")
                expiration = None
                if expiry_str:
                    for fmt in ["%Y%m%d", "%Y-%m-%d"]:
                        try:
                            expiration = datetime.strptime(expiry_str, fmt)
                            break
                        except ValueError:
                            continue

                execution.update(
                    {
                        "option_type": trade.get("putCall", ""),
                        "strike": Decimal(str(trade.get("strike", 0))),
                        "expiration": expiration,
                        "multiplier": int(float(trade.get("multiplier", 100))),
                    }
                )
            else:
                execution.update(
                    {
                        "option_type": None,
                        "strike": None,
                        "expiration": None,
                        "multiplier": None,
                    }
                )

            return execution

        except Exception as e:
            print(f"Error parsing trade: {e}")
            return None
