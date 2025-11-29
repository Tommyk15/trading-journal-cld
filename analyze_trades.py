"""
Detailed Trade Analysis - Show all executions by underlying
"""

import pandas as pd
from datetime import datetime
from collections import defaultdict

def load_csv(csv_path):
    """Load and parse CSV"""
    df = pd.read_csv(csv_path)

    # Parse timestamp
    def parse_timestamp(dt_str):
        try:
            return datetime.strptime(dt_str, "%Y%m%d;%H%M%S")
        except:
            return None

    df['parsed_timestamp'] = df['DateTime'].apply(parse_timestamp)
    df = df[df['parsed_timestamp'].notna()]

    # Extract underlying symbol
    df['underlying'] = df['Symbol'].str.split().str[0]

    return df

def analyze_by_underlying(csv_path):
    """Show detailed execution breakdown by underlying"""
    df = load_csv(csv_path)

    print("=" * 120)
    print("DETAILED TRADE ANALYSIS BY UNDERLYING")
    print("=" * 120)

    # Group by underlying
    underlyings = sorted(df['underlying'].unique())

    for underlying in underlyings:
        underlying_df = df[df['underlying'] == underlying].sort_values('parsed_timestamp')

        print(f"\n{'=' * 120}")
        print(f"UNDERLYING: {underlying}")
        print(f"{'=' * 120}")
        print(f"Total Executions: {len(underlying_df)}")

        # Group by date
        underlying_df['date'] = underlying_df['parsed_timestamp'].dt.date
        dates = sorted(underlying_df['date'].unique())

        for date in dates:
            date_df = underlying_df[underlying_df['date'] == date]

            print(f"\n  Date: {date}")
            print(f"  {'-' * 116}")

            # Show each execution
            for idx, row in date_df.iterrows():
                timestamp = row['parsed_timestamp'].strftime("%H:%M:%S")
                side = row['Buy/Sell']
                qty = abs(int(row['Quantity']))
                oc = row['Open/CloseIndicator'] if pd.notna(row['Open/CloseIndicator']) else '?'

                # Build option description
                if row['AssetClass'] == 'OPT':
                    strike = int(row['Strike']) if pd.notna(row['Strike']) else '?'
                    exp = str(int(row['Expiry'])) if pd.notna(row['Expiry']) else '?'
                    right = row['Put/Call'] if pd.notna(row['Put/Call']) else '?'
                    price = abs(float(row['TradePrice'])) if pd.notna(row['TradePrice']) and float(row['TradePrice']) != 0 else 0

                    # Format expiry as readable date
                    if exp != '?':
                        exp_date = datetime.strptime(str(exp), '%Y%m%d').strftime('%m/%d/%y')
                    else:
                        exp_date = '?'

                    proceeds = float(row['Proceeds']) if pd.notna(row['Proceeds']) else 0
                    pnl = float(row['FifoPnlRealized']) if pd.notna(row['FifoPnlRealized']) else 0

                    desc = f"{exp_date} {strike:>3}{right}"
                    print(f"    {timestamp} | {oc:^5} | {side:4} {qty:>3}x {desc:15} @ ${price:>6.2f} | Proceeds: ${proceeds:>8.2f} | PnL: ${pnl:>8.2f}")
                else:
                    price = abs(float(row['TradePrice'])) if pd.notna(row['TradePrice']) else 0
                    proceeds = float(row['Proceeds']) if pd.notna(row['Proceeds']) else 0
                    pnl = float(row['FifoPnlRealized']) if pd.notna(row['FifoPnlRealized']) else 0

                    print(f"    {timestamp} | {oc:^5} | {side:4} {qty:>3}x STK @ ${price:>6.2f} | Proceeds: ${proceeds:>8.2f} | PnL: ${pnl:>8.2f}")

        # Show net position
        print(f"\n  Net Position Summary:")
        print(f"  {'-' * 116}")

        # Calculate net position per contract
        positions = defaultdict(lambda: {'qty': 0, 'cost': 0})

        for idx, row in underlying_df.iterrows():
            if row['AssetClass'] == 'OPT':
                strike = int(row['Strike']) if pd.notna(row['Strike']) else 0
                exp = str(int(row['Expiry'])) if pd.notna(row['Expiry']) else ''
                right = row['Put/Call'] if pd.notna(row['Put/Call']) else ''

                key = f"{exp}_{strike}_{right}"

                qty = int(row['Quantity'])
                price = abs(float(row['TradePrice'])) if pd.notna(row['TradePrice']) else 0

                positions[key]['qty'] += qty

                # Cost: BUY is negative (costs money), SELL is positive (brings in money)
                cost = float(row['Proceeds']) if pd.notna(row['Proceeds']) else 0
                positions[key]['cost'] += cost

        # Show positions
        for contract, pos in sorted(positions.items()):
            if pos['qty'] != 0:  # Only show open positions
                exp_str, strike, right = contract.split('_')
                exp_date = datetime.strptime(exp_str, '%Y%m%d').strftime('%m/%d/%y') if exp_str else '?'
                print(f"    {exp_date} {strike:>3}{right}: Qty={pos['qty']:>4}, Net Cost=${pos['cost']:>9.2f}")

        # Show realized P&L for this underlying
        total_pnl = underlying_df['FifoPnlRealized'].sum() if 'FifoPnlRealized' in underlying_df else 0
        print(f"\n  Total Realized P&L: ${total_pnl:,.2f}")

def main():
    csv_path = '/Users/tommyk15/Downloads/TradingJournalExecutions1.csv'
    analyze_by_underlying(csv_path)

    print("\n" + "=" * 120)
    print("Analysis complete - Review the execution sequences to verify trade classification")
    print("=" * 120)

if __name__ == "__main__":
    main()
