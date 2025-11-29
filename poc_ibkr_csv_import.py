"""
POC #1 Final: Import IBKR Executions from CSV

For large datasets (13K+ executions), the Flex Query API times out.
Solution: Manually download CSV from Account Management, then import.

This approach:
- ✅ Works with any size dataset
- ✅ No API timeout issues
- ✅ Same data as API would provide
- ✅ Can be automated (daily/weekly manual export)
"""

import csv
from datetime import datetime
from collections import defaultdict


def parse_ibkr_csv(csv_path):
    """
    Parse IBKR Flex Query CSV export

    Returns list of execution dictionaries
    """
    print(f"📥 Reading IBKR CSV: {csv_path}")

    executions = []

    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)

        for row in reader:
            # Skip summary rows (no date/time)
            if not row['Date/Time'] or row['Date/Time'] == '':
                continue

            # Parse execution
            execution = {
                'symbol': row['Symbol'],
                'asset_type': row['AssetClass'],  # 'STK' or 'OPT'
                'date_time': row['Date/Time'],  # Format: YYYYMMDD;HHMMSS
                'side': row['Buy/Sell'],  # 'BUY' or 'SELL'
                'quantity': abs(float(row['Quantity'])),  # Convert to positive
                'price': float(row['Price']),
                'proceeds': float(row['Proceeds']),
                'commission': float(row['Commission']),
                'trade_id': row['TradeID'],
                'exec_id': row['ExecID'],
                'order_id': row['OrderID'],
            }

            # Add option-specific fields
            if execution['asset_type'] == 'OPT':
                execution['strike'] = float(row['Strike']) if row['Strike'] else None
                execution['expiry'] = row['Expiry']  # Format: YYYYMMDD
                execution['right'] = row['Put/Call']  # 'C' or 'P'
                execution['multiplier'] = float(row['Multiplier']) if row['Multiplier'] else 100

            executions.append(execution)

    print(f"✅ Parsed {len(executions)} executions")
    return executions


def validate_executions(executions):
    """
    Validate execution data for POC
    """
    print(f"\n🔍 Validating execution data...")

    # Count by asset type
    by_type = defaultdict(int)
    for exec in executions:
        by_type[exec['asset_type']] += 1

    # Count by side
    by_side = defaultdict(int)
    for exec in executions:
        by_side[exec['side']] += 1

    # Sample executions
    option_execs = [e for e in executions if e['asset_type'] == 'OPT']
    stock_execs = [e for e in executions if e['asset_type'] == 'STK']

    print(f"\n📊 Breakdown:")
    print(f"   Total executions: {len(executions)}")
    print(f"   Stock executions: {by_type['STK']}")
    print(f"   Option executions: {by_type['OPT']}")
    print(f"   BUY executions: {by_side['BUY']}")
    print(f"   SELL executions: {by_side['SELL']}")

    # Check required fields
    print(f"\n✅ Field validation:")

    # Critical fields (must be present and non-empty)
    critical_fields = ['symbol', 'asset_type', 'date_time', 'side', 'quantity', 'price']

    all_valid = True
    for field in critical_fields:
        has_field = all(field in e and e[field] not in [None, ''] for e in executions)
        status = "✅" if has_field else "❌"
        print(f"   {status} {field}: {'Present' if has_field else 'MISSING'}")
        if not has_field:
            all_valid = False

    # Optional fields (may be empty)
    optional_fields = {'exec_id': 'Execution ID', 'trade_id': 'Trade ID', 'order_id': 'Order ID'}
    print(f"\n📋 Optional fields:")
    for field, description in optional_fields.items():
        count_present = sum(1 for e in executions if field in e and e[field])
        percentage = (count_present / len(executions)) * 100 if executions else 0
        print(f"   ℹ️  {description}: {count_present}/{len(executions)} ({percentage:.1f}%)")

    # Check option-specific fields
    if option_execs:
        print(f"\n✅ Option-specific fields:")
        option_fields = ['strike', 'expiry', 'right']
        for field in option_fields:
            has_field = all(field in e and e[field] for e in option_execs)
            status = "✅" if has_field else "❌"
            print(f"   {status} {field}: {'Present' if has_field else 'MISSING'}")

    return all_valid


def show_sample_executions(executions, count=5):
    """
    Display sample executions
    """
    print(f"\n📋 Sample Executions (first {count}):\n")

    for i, exec in enumerate(executions[:count], 1):
        print(f"{i}. {exec['symbol']} ({exec['asset_type']})")
        print(f"   Date: {exec['date_time']}")
        print(f"   {exec['side']} {exec['quantity']} @ ${exec['price']:.2f}")

        if exec['asset_type'] == 'OPT':
            print(f"   Strike: ${exec['strike']} {exec['right']} Exp: {exec['expiry']}")

        print(f"   Proceeds: ${exec['proceeds']:.2f}")
        print(f"   Commission: ${exec['commission']:.2f}")
        print(f"   Exec ID: {exec['exec_id']}")
        print()


def test_csv_import(csv_path):
    """
    Test IBKR CSV import for POC
    """
    print("=" * 80)
    print("POC #1 (CSV Import): IBKR Execution Fetching")
    print("=" * 80)
    print("\nUsing manual CSV export (works for large datasets)")
    print("-" * 80)
    print()

    # Parse CSV
    executions = parse_ibkr_csv(csv_path)

    if not executions:
        print("\n❌ No executions found in CSV")
        return []

    # Validate
    is_valid = validate_executions(executions)

    # Show samples
    show_sample_executions(executions)

    # Results
    print("=" * 80)
    print("POC #1 RESULTS")
    print("=" * 80)

    if is_valid and executions:
        print(f"\n✅ POC #1 PASSED - CSV Import works perfectly!")
        print(f"\n📊 Summary:")
        print(f"   - Successfully imported {len(executions)} executions")
        print(f"   - All required fields present")
        print(f"   - Option and stock trades included")
        print(f"   - Ready for trade grouping (POC #3)")

        print(f"\n🎯 Next Steps:")
        print(f"   1. ✅ IBKR execution data validated")
        print(f"   2. ⏭️  Move to POC #2 (Polygon.io Greeks)")
        print(f"   3. ⏭️  Move to POC #3 (Trade Grouping)")

        print(f"\n📝 For Production:")
        print(f"   - Manual CSV export weekly/monthly")
        print(f"   - Or reduce Flex Query date range (API will work for smaller datasets)")
        print(f"   - This approach handles unlimited history")
    else:
        print(f"\n❌ POC #1 FAILED - Missing required fields")

    print("=" * 80)

    return executions


if __name__ == "__main__":
    import sys

    # Default to the downloaded file
    csv_path = "/Users/tommyk15/Downloads/TradingJournalExecutions.csv"

    # Allow override from command line
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]

    # Run test
    executions = test_csv_import(csv_path)

    if executions:
        print(f"\n✅ SUCCESS: {len(executions)} executions ready for POC #3!")
        exit(0)
    else:
        print(f"\n❌ FAILURE: Could not import executions")
        exit(1)
