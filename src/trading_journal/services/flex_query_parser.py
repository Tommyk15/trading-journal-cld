"""Flex Query parser for CSV and XML formats."""

import csv
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from decimal import Decimal
from io import StringIO
from typing import Any


class FlexQueryParser:
    """Parse IBKR Flex Query reports in CSV or XML format."""

    @staticmethod
    def parse_file(content: str) -> list[dict[str, Any]]:
        """Parse Flex Query file content.

        Args:
            content: File content as string

        Returns:
            List of execution dictionaries

        Raises:
            ValueError: If format is not supported
        """
        # Detect format
        content = content.strip()

        if content.startswith('<?xml'):
            return FlexQueryParser._parse_xml(content)
        elif content.startswith('"') or content.startswith('Symbol,'):
            return FlexQueryParser._parse_csv(content)
        else:
            raise ValueError("Unsupported file format. Expected XML or CSV.")

    @staticmethod
    def _parse_xml(content: str) -> list[dict[str, Any]]:
        """Parse XML Flex Query report.

        Args:
            content: XML content

        Returns:
            List of execution dictionaries
        """
        executions = []

        try:
            root = ET.fromstring(content)

            # Find all Trade elements
            trades = root.findall('.//Trade')

            for trade in trades:
                execution = FlexQueryParser._parse_trade_element(trade)
                if execution:
                    executions.append(execution)

        except ET.ParseError as e:
            raise ValueError(f"Invalid XML format: {e}")

        return executions

    @staticmethod
    def _parse_csv(content: str) -> list[dict[str, Any]]:
        """Parse CSV Flex Query report.

        Args:
            content: CSV content

        Returns:
            List of execution dictionaries
        """
        executions = []

        try:
            reader = csv.DictReader(StringIO(content))

            for row in reader:
                execution = FlexQueryParser._parse_csv_row(row)
                if execution:
                    executions.append(execution)

        except Exception as e:
            raise ValueError(f"Invalid CSV format: {e}")

        return executions

    @staticmethod
    def _parse_trade_element(trade: ET.Element) -> dict[str, Any]:
        """Parse a Trade XML element.

        Args:
            trade: XML Trade element

        Returns:
            Execution dictionary
        """
        try:
            # Parse datetime - format is YYYYMMDD;HHMMSS or YYYYMMDD;HHMMSS;TZ
            dt_str = trade.get('dateTime', '')
            execution_time = None
            if dt_str:
                parts = dt_str.split(';')
                if len(parts) >= 2:
                    # Has date and time (possibly with timezone suffix to ignore)
                    dt_clean = f"{parts[0]};{parts[1]}"
                    execution_time = datetime.strptime(dt_clean, '%Y%m%d;%H%M%S').replace(tzinfo=UTC)
                elif len(parts) == 1:
                    # Just date
                    execution_time = datetime.strptime(parts[0], '%Y%m%d').replace(tzinfo=UTC)

            # Parse IDs
            try:
                order_id = int(trade.get('ibOrderID', 0))
            except (ValueError, TypeError):
                order_id = 0

            try:
                perm_id = int(trade.get('tradeID', 0))
            except (ValueError, TypeError):
                perm_id = 0

            # Base execution data
            execution = {
                'exec_id': trade.get('ibExecID', ''),
                'order_id': order_id,
                'perm_id': perm_id,
                'execution_time': execution_time,
                'underlying': trade.get('symbol', ''),
                'security_type': 'OPT' if trade.get('assetCategory') == 'OPT' else 'STK',
                'exchange': trade.get('exchange', 'SMART'),
                'currency': trade.get('currency', 'USD'),
                'side': 'BOT' if trade.get('buySell') == 'BUY' else 'SLD',
                'open_close_indicator': trade.get('openCloseIndicator', None),
                'quantity': abs(Decimal(str(trade.get('quantity', 0)))),
                'price': Decimal(str(trade.get('tradePrice', 0))),
                'commission': abs(Decimal(str(trade.get('ibCommission', 0)))),
                'net_amount': Decimal(str(trade.get('netCash', 0))),
                'account_id': 'FLEX_IMPORT',
            }

            # Option-specific fields
            if execution['security_type'] == 'OPT':
                expiry_str = trade.get('expiry', '')
                execution.update({
                    'option_type': trade.get('putCall', ''),
                    'strike': Decimal(str(trade.get('strike', 0))),
                    'expiration': datetime.strptime(expiry_str, '%Y%m%d').replace(tzinfo=UTC) if expiry_str else None,
                    'multiplier': int(float(trade.get('multiplier', 100))),
                })
            else:
                execution.update({
                    'option_type': None,
                    'strike': None,
                    'expiration': None,
                    'multiplier': None,
                })

            return execution

        except Exception as e:
            print(f"Error parsing trade: {e}")
            return None

    @staticmethod
    def _parse_csv_row(row: dict[str, str]) -> dict[str, Any]:
        """Parse a CSV row.

        Args:
            row: CSV row dictionary

        Returns:
            Execution dictionary
        """
        try:
            # Parse datetime (various formats)
            dt_str = row.get('DateTime', row.get('Date/Time', ''))

            # Try different datetime formats
            execution_time = None
            for fmt in ['%Y%m%d;%H%M%S', '%Y-%m-%d, %H:%M:%S', '%Y-%m-%d %H:%M:%S']:
                try:
                    execution_time = datetime.strptime(dt_str, fmt).replace(tzinfo=UTC)
                    break
                except ValueError:
                    continue

            # Determine security type
            asset_category = row.get('AssetClass', row.get('Asset Category', ''))
            security_type = 'OPT' if asset_category == 'OPT' else 'STK'

            # Determine side
            buy_sell = row.get('Buy/Sell', row.get('BuySell', ''))
            side = 'BOT' if buy_sell == 'BUY' else 'SLD'

            # Extract underlying symbol (for options, remove the option suffix)
            symbol = row.get('Symbol', '')
            underlying = symbol

            # For options, the symbol includes the option details (e.g., "ACHR  260116C00013000")
            # Extract just the underlying ticker
            if security_type == 'OPT' and symbol:
                # Symbol format: "TICKER  YYMMDDCNNNNN" where C is P/C and NNNNN is strike
                underlying = symbol.split()[0] if ' ' in symbol else symbol

            # Parse order_id and perm_id (use TradeID as perm_id since it's a permanent identifier)
            order_id_str = row.get('IBOrderID', row.get('Order ID', row.get('ibOrderID', '0')))
            trade_id_str = row.get('TradeID', row.get('Trade ID', row.get('tradeID', '0')))

            # Convert to integers, handling potential errors
            try:
                order_id = int(order_id_str) if order_id_str else 0
            except ValueError:
                order_id = 0

            try:
                perm_id = int(trade_id_str) if trade_id_str else 0
            except ValueError:
                perm_id = 0

            # Base execution data
            execution = {
                'exec_id': row.get('IBExecID', row.get('Execution ID', row.get('ibExecID', ''))),
                'order_id': order_id,
                'perm_id': perm_id,
                'execution_time': execution_time,
                'underlying': underlying,
                'security_type': security_type,
                'exchange': row.get('Exchange', 'SMART'),  # Default to SMART if not provided
                'currency': row.get('Currency', 'USD'),  # Default to USD if not provided
                'side': side,
                'open_close_indicator': row.get('Open/CloseIndicator', row.get('OpenCloseIndicator', None)),
                'quantity': abs(Decimal(str(row.get('Quantity', 0)))),
                'price': Decimal(str(row.get('TradePrice', row.get('T. Price', row.get('Trade Price', 0))))),
                'commission': abs(Decimal(str(row.get('IBCommission', row.get('Comm/Fee', row.get('ibCommission', 0)))))),
                'net_amount': Decimal(str(row.get('Proceeds', row.get('netCash', 0)))),
                'account_id': 'FLEX_IMPORT',  # Default account ID for flex query imports
            }

            # Option-specific fields
            if security_type == 'OPT':
                expiry_str = row.get('Expiry', row.get('expiry', ''))

                # Parse expiry
                expiration = None
                if expiry_str:
                    for fmt in ['%Y%m%d', '%Y-%m-%d']:
                        try:
                            expiration = datetime.strptime(expiry_str, fmt).replace(tzinfo=UTC)
                            break
                        except ValueError:
                            continue

                execution.update({
                    'option_type': row.get('Put/Call', row.get('putCall', '')),
                    'strike': Decimal(str(row.get('Strike', 0))) if row.get('Strike') else None,
                    'expiration': expiration,
                    'multiplier': int(float(row.get('Multiplier', 100))),
                })
            else:
                execution.update({
                    'option_type': None,
                    'strike': None,
                    'expiration': None,
                    'multiplier': None,
                })

            return execution

        except Exception as e:
            print(f"Error parsing CSV row: {e}")
            import traceback
            traceback.print_exc()
            return None
