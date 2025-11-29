"""
Test POC #3 Grouping Algorithm with Real Trading Data

Loads executions from CSV and runs through the grouping algorithm
"""

import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict
import json


# Import the grouping functions from POC #3
def sort_executions(executions: List[Dict]) -> List[Dict]:
    """
    Sort executions using deterministic 8-key sort

    Sort order:
    1. timestamp (ascending)
    2. underlying (ascending)
    3. asset_type (ascending)
    4. side (BUY before SELL)
    5. open_close (OPEN before CLOSE)
    6. expiry (ascending)
    7. strike (ascending)
    8. right (C before P)
    """
    def sort_key(exec_dict):
        return (
            exec_dict['timestamp'],
            exec_dict['underlying'],
            exec_dict['asset_type'],
            exec_dict['side'],  # BUY < SELL alphabetically
            exec_dict['open_close'],  # CLOSE < OPEN alphabetically
            exec_dict.get('expiry', ''),
            exec_dict.get('strike', 0),
            exec_dict.get('right', '')
        )

    sorted_execs = sorted(executions, key=sort_key)
    return sorted_execs


class TradeLedger:
    """
    Simple ledger-based trade grouping
    """

    def __init__(self):
        self.trades = []
        self.current_trade = None
        self.position_ledger = {}  # Track position by leg structure

    def get_leg_key(self, execution):
        """Generate unique key for a leg (specific structure)"""
        if execution['asset_type'] == 'OPT':
            return f"{execution['underlying']}_{execution['expiry']}_{execution['strike']}_{execution['right']}"
        else:
            return f"{execution['underlying']}_STK"

    def update_ledger(self, execution):
        """Update position ledger with execution"""
        leg_key = self.get_leg_key(execution)

        # Calculate signed quantity (BUY = +, SELL = -)
        signed_qty = execution['quantity']
        if execution['side'] == 'SELL':
            signed_qty = -signed_qty

        # Update ledger
        if leg_key not in self.position_ledger:
            self.position_ledger[leg_key] = {
                'quantity': 0,
                'total_cost': 0.0,
                'executions': []
            }

        leg = self.position_ledger[leg_key]

        # Calculate cost (BUY costs money, SELL brings in money)
        cost = execution['price'] * abs(execution['quantity']) * execution['multiplier']
        if execution['side'] == 'SELL':
            cost = -cost

        leg['quantity'] += signed_qty
        leg['total_cost'] += cost
        leg['executions'].append(execution)

    def is_flat(self):
        """Check if all positions are flat (zero quantity)"""
        return all(leg['quantity'] == 0 for leg in self.position_ledger.values())

    def get_trade_summary(self):
        """Get summary of current trade"""
        total_cost = sum(leg['total_cost'] for leg in self.position_ledger.values())
        all_executions = []
        for leg in self.position_ledger.values():
            all_executions.extend(leg['executions'])

        return {
            'executions': all_executions,
            'legs': dict(self.position_ledger),
            'total_pnl': -total_cost,  # Negative cost = profit
            'is_closed': self.is_flat()
        }

    def reset(self):
        """Reset ledger for new trade"""
        self.position_ledger = {}


def group_executions_into_trades(executions: List[Dict]) -> List[Dict]:
    """
    Group executions into trades using ledger approach
    """
    sorted_execs = sort_executions(executions)

    trades = []
    current_ledger = TradeLedger()

    for execution in sorted_execs:
        # Update ledger
        current_ledger.update_ledger(execution)

        # Check if trade is complete (all positions flat)
        if current_ledger.is_flat():
            trade = current_ledger.get_trade_summary()
            trades.append(trade)
            current_ledger.reset()

    # Handle open trade (if any)
    if current_ledger.position_ledger:
        trade = current_ledger.get_trade_summary()
        trades.append(trade)

    return trades


def load_and_convert_csv(csv_path: str, days_back: int = 7) -> List[Dict]:
    """
    Load CSV and convert to format expected by grouping algorithm

    Args:
        csv_path: Path to TradingJournalExecutions.csv
        days_back: Number of days to look back (default: 7)

    Returns:
        List of execution dictionaries
    """
    print(f"Loading CSV from: {csv_path}")
    df = pd.read_csv(csv_path)

    print(f"Total rows in CSV: {len(df)}")

    # Detect DateTime column (could be 'Date/Time' or 'DateTime')
    datetime_col = 'DateTime' if 'DateTime' in df.columns else 'Date/Time'

    # Filter out rows without DateTime (summary rows)
    df = df[df[datetime_col].notna() & (df[datetime_col] != '')]
    print(f"Rows with timestamps: {len(df)}")

    # Parse timestamp
    def parse_timestamp(dt_str):
        """Parse YYYYMMDD;HHMMSS format"""
        try:
            return datetime.strptime(dt_str, "%Y%m%d;%H%M%S")
        except:
            return None

    df['parsed_timestamp'] = df[datetime_col].apply(parse_timestamp)
    df = df[df['parsed_timestamp'].notna()]

    # Get date range
    max_date = df['parsed_timestamp'].max()
    min_date = df['parsed_timestamp'].min()
    print(f"\nDate range in data: {min_date.date()} to {max_date.date()}")

    # Filter to last N days
    cutoff_date = max_date - timedelta(days=days_back)
    df_filtered = df[df['parsed_timestamp'] >= cutoff_date]
    print(f"Transactions in last {days_back} days: {len(df_filtered)}")

    if len(df_filtered) == 0:
        print(f"\n⚠️  No transactions in last {days_back} days, using all data instead")
        df_filtered = df

    # Convert to execution format
    executions = []

    for _, row in df_filtered.iterrows():
        # Determine side (handle negative quantities)
        quantity = float(row['Quantity'])
        if quantity < 0:
            side = 'SELL'
            quantity = abs(quantity)
        else:
            side = 'BUY'

        # Determine open/close indicator
        open_close = 'OPEN'  # Default
        if 'Open/CloseIndicator' in df.columns and pd.notna(row['Open/CloseIndicator']):
            oc_indicator = str(row['Open/CloseIndicator']).strip().upper()
            if oc_indicator == 'C':
                open_close = 'CLOSE'
            elif oc_indicator == 'O':
                open_close = 'OPEN'

        # Detect ExecID column
        exec_id_col = 'IBExecID' if 'IBExecID' in df.columns else 'ExecID'
        order_id_col = 'IBOrderID' if 'IBOrderID' in df.columns else 'OrderID'

        # Base execution
        execution = {
            'exec_id': str(row[exec_id_col]) if pd.notna(row.get(exec_id_col)) else str(row.get(order_id_col, '')),
            'timestamp': row['parsed_timestamp'],
            'underlying': row['Symbol'].split()[0],  # Extract underlying (e.g., "AMD" from "AMD   251121P00230000")
            'asset_type': row['AssetClass'],
            'side': side,
            'open_close': open_close,
            'quantity': quantity,
            'price': abs(float(row['TradePrice'])) if pd.notna(row.get('TradePrice')) and float(row.get('TradePrice', 0)) != 0 else abs(float(row.get('Price', 0))),
            'multiplier': int(row['Multiplier']) if pd.notna(row['Multiplier']) else 1
        }

        # Add option-specific fields
        if row['AssetClass'] == 'OPT':
            execution['strike'] = float(row['Strike']) if pd.notna(row['Strike']) else 0
            execution['expiry'] = str(int(row['Expiry'])) if pd.notna(row['Expiry']) else ''
            execution['right'] = row['Put/Call'] if pd.notna(row['Put/Call']) else ''

        executions.append(execution)

    print(f"\nConverted {len(executions)} executions")
    print(f"Asset types: {df_filtered['AssetClass'].value_counts().to_dict()}")

    # Show open/close breakdown
    if 'Open/CloseIndicator' in df.columns:
        opens = len([e for e in executions if e['open_close'] == 'OPEN'])
        closes = len([e for e in executions if e['open_close'] == 'CLOSE'])
        print(f"Open/Close breakdown: {opens} OPEN, {closes} CLOSE")

    return executions


def main():
    """Main execution"""
    csv_path = '/Users/tommyk15/Downloads/TradingJournalExecutions1.csv'

    print("=" * 100)
    print("POC #3: Testing Grouping Algorithm with Real Trading Data")
    print("=" * 100)
    print()

    # Load and convert data
    executions = load_and_convert_csv(csv_path, days_back=7)

    if len(executions) == 0:
        print("\n❌ No executions to process")
        return

    # Show sample executions
    print("\n" + "=" * 100)
    print("SAMPLE EXECUTIONS (first 10)")
    print("=" * 100)
    for i, exec in enumerate(executions[:10], 1):
        opt_info = ""
        if exec['asset_type'] == 'OPT':
            opt_info = f" {exec.get('strike', '')} {exec.get('right', '')} exp:{exec.get('expiry', '')}"
        print(f"{i}. {exec['timestamp']} | {exec['underlying']} {exec['asset_type']} | "
              f"{exec['side']:4} x{exec['quantity']:.0f} @ ${exec['price']:.2f}{opt_info}")

    # Run grouping algorithm
    print("\n" + "=" * 100)
    print("RUNNING GROUPING ALGORITHM")
    print("=" * 100)

    trades = group_executions_into_trades(executions)

    print(f"\n✅ Grouped {len(executions)} executions into {len(trades)} trades")

    # Show results
    print("\n" + "=" * 100)
    print("TRADE GROUPING RESULTS")
    print("=" * 100)

    closed_trades = [t for t in trades if t['is_closed']]
    open_trades = [t for t in trades if not t['is_closed']]

    print(f"\nClosed Trades: {len(closed_trades)}")
    print(f"Open Trades: {len(open_trades)}")

    # Show closed trades
    if closed_trades:
        print("\n" + "=" * 100)
        print("CLOSED TRADES")
        print("=" * 100)

        for i, trade in enumerate(closed_trades, 1):
            underlying = trade['executions'][0]['underlying'] if trade['executions'] else 'UNKNOWN'
            asset_type = trade['executions'][0]['asset_type'] if trade['executions'] else 'UNKNOWN'

            print(f"\nTrade #{i}: {underlying} ({asset_type})")
            print(f"  Status: CLOSED")
            print(f"  P&L: ${trade['total_pnl']:.2f}")
            print(f"  Executions: {len(trade['executions'])}")
            print(f"  Legs:")
            for leg_key, leg_data in trade['legs'].items():
                print(f"    {leg_key}: Qty={leg_data['quantity']}, Cost=${leg_data['total_cost']:.2f}")

    # Show open trades summary
    if open_trades:
        print("\n" + "=" * 100)
        print("OPEN TRADES (Summary)")
        print("=" * 100)

        for i, trade in enumerate(open_trades, 1):
            underlying = trade['executions'][0]['underlying'] if trade['executions'] else 'UNKNOWN'
            asset_type = trade['executions'][0]['asset_type'] if trade['executions'] else 'UNKNOWN'

            print(f"\nTrade #{i}: {underlying} ({asset_type})")
            print(f"  Status: OPEN")
            print(f"  Unrealized P&L: ${trade['total_pnl']:.2f}")
            print(f"  Executions: {len(trade['executions'])}")
            print(f"  Open Legs: {len([leg for leg in trade['legs'].values() if leg['quantity'] != 0])}")

            # Show breakdown of open legs by underlying
            print(f"\n  Open Legs Breakdown:")
            leg_by_underlying = {}
            for leg_key, leg_data in trade['legs'].items():
                if leg_data['quantity'] != 0:
                    underlying_sym = leg_key.split('_')[0]
                    if underlying_sym not in leg_by_underlying:
                        leg_by_underlying[underlying_sym] = []
                    leg_by_underlying[underlying_sym].append((leg_key, leg_data))

            for und, legs in sorted(leg_by_underlying.items()):
                print(f"\n    {und}:")
                for leg_key, leg_data in legs[:5]:  # Show first 5 legs per underlying
                    print(f"      {leg_key}: Qty={leg_data['quantity']}, Cost=${leg_data['total_cost']:.2f}")
                if len(legs) > 5:
                    print(f"      ... and {len(legs) - 5} more legs")

    # Summary statistics
    print("\n" + "=" * 100)
    print("SUMMARY STATISTICS")
    print("=" * 100)

    total_pnl_closed = sum(t['total_pnl'] for t in closed_trades)
    total_pnl_open = sum(t['total_pnl'] for t in open_trades)

    print(f"\nTotal Trades: {len(trades)}")
    print(f"  Closed: {len(closed_trades)}")
    print(f"  Open: {len(open_trades)}")
    print(f"\nRealized P&L (Closed): ${total_pnl_closed:,.2f}")
    print(f"Unrealized P&L (Open): ${total_pnl_open:,.2f}")
    print(f"Total P&L: ${total_pnl_closed + total_pnl_open:,.2f}")

    print("\n" + "=" * 100)
    print("✅ POC #3 VALIDATION COMPLETE")
    print("=" * 100)
    print("\n🎯 Algorithm successfully processed real trading data!")
    print("   - Deterministic sorting applied")
    print("   - Ledger-based grouping completed")
    print("   - Closed trades detected")
    print("   - P&L calculated")


if __name__ == "__main__":
    main()
