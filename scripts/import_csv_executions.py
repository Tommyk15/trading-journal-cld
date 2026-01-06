"""Import executions from CSV file into the database."""

import asyncio
import csv
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from trading_journal.config import get_settings
from trading_journal.models.execution import Execution

settings = get_settings()


def parse_csv_row(row: dict[str, str]) -> dict | None:
    """Parse a CSV row into execution dictionary."""
    try:
        # Parse datetime
        dt_str = row.get("DateTime", "")
        execution_time = None
        if dt_str:
            for fmt in [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d, %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%Y%m%d;%H%M%S",
            ]:
                try:
                    execution_time = datetime.strptime(dt_str, fmt).replace(tzinfo=UTC)
                    break
                except ValueError:
                    continue

        # Determine asset class
        asset_class = row.get("AssetClass", "")
        security_type = "OPT" if asset_class == "OPT" else "STK"

        # Get underlying symbol
        underlying = row.get("UnderlyingSymbol", "") or row.get("Symbol", "")
        # For stocks, Symbol is the underlying
        if security_type == "STK":
            underlying = row.get("Symbol", "")

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
            quantity = abs(Decimal(str(row.get("Quantity", 0) or 0)))
        except (ValueError, TypeError):
            quantity = Decimal("0")

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

        # Parse open/close indicator
        open_close = row.get("Open/CloseIndicator", "") or ""
        if open_close and len(open_close) > 1:
            open_close = open_close[0]

        # Determine side
        side = "BOT" if row.get("Buy/Sell", "").upper() == "BUY" else "SLD"

        # Calculate raw net_amount WITHOUT commission
        if side == "BOT":
            raw_net_amount = net_cash + commission
        else:
            raw_net_amount = net_cash + commission

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
            "side": side,
            "open_close_indicator": open_close if open_close else None,
            "quantity": quantity,
            "price": price,
            "commission": commission,
            "net_amount": raw_net_amount,
            "account_id": row.get("ClientAccountID", "FLEX_IMPORT") or "FLEX_IMPORT",
        }

        # Option-specific fields
        if security_type == "OPT":
            expiry_str = row.get("Expiry", "")
            expiration = None
            if expiry_str:
                for fmt in ["%Y-%m-%d", "%Y%m%d"]:
                    try:
                        expiration = datetime.strptime(expiry_str, fmt).replace(tzinfo=UTC)
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


async def import_csv(csv_path: str, dry_run: bool = False):
    """Import executions from CSV file."""
    # Create database connection
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    stats = {
        "total": 0,
        "existing": 0,
        "imported": 0,
        "errors": 0,
    }

    async with async_session() as session:
        # Read CSV file
        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        print(f"Found {len(rows)} rows in CSV")

        for row in rows:
            stats["total"] += 1
            exec_data = parse_csv_row(row)

            if not exec_data:
                stats["errors"] += 1
                continue

            exec_id = exec_data["exec_id"]

            # Check if execution already exists
            stmt = select(Execution).where(Execution.exec_id == exec_id)
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                stats["existing"] += 1
                continue

            # Import new execution
            if not dry_run:
                execution = Execution(**exec_data)
                session.add(execution)
                print(f"  Imported: {exec_data['execution_time']} {exec_data['side']} {exec_data['quantity']} {exec_data['underlying']} @ {exec_data['price']}")
            else:
                print(f"  Would import: {exec_data['execution_time']} {exec_data['side']} {exec_data['quantity']} {exec_data['underlying']} @ {exec_data['price']}")

            stats["imported"] += 1

        if not dry_run:
            await session.commit()

    await engine.dispose()

    print(f"\nImport complete:")
    print(f"  Total rows: {stats['total']}")
    print(f"  Already existing: {stats['existing']}")
    print(f"  Imported: {stats['imported']}")
    print(f"  Errors: {stats['errors']}")

    return stats


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python import_csv_executions.py <csv_path> [--dry-run]")
        sys.exit(1)

    csv_path = sys.argv[1]
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        print("DRY RUN - no changes will be made\n")

    asyncio.run(import_csv(csv_path, dry_run))
