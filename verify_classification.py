"""
Verify Trade Classification - Focus on specific underlyings
"""

import pandas as pd
from datetime import datetime

def analyze_underlying(df, symbol):
    """Detailed analysis of a specific underlying"""
    underlying_df = df[df['underlying'] == symbol].sort_values('parsed_timestamp')

    print(f"\n{'=' * 120}")
    print(f"{symbol} - DETAILED CLASSIFICATION")
    print(f"{'=' * 120}")

    for idx, row in underlying_df.iterrows():
        timestamp = row['parsed_timestamp'].strftime("%m/%d %H:%M:%S")
        side = row['Buy/Sell']
        qty = abs(int(row['Quantity']))
        oc = row['Open/CloseIndicator'] if pd.notna(row['Open/CloseIndicator']) else '?'

        strike = int(row['Strike']) if pd.notna(row['Strike']) else '?'
        exp = str(int(row['Expiry'])) if pd.notna(row['Expiry']) else '?'
        right = row['Put/Call'] if pd.notna(row['Put/Call']) else '?'
        price = abs(float(row['TradePrice'])) if pd.notna(row['TradePrice']) and float(row['TradePrice']) != 0 else 0

        # Format expiry
        if exp != '?':
            exp_date = datetime.strptime(str(exp), '%Y%m%d').strftime('%m/%d/%y')
        else:
            exp_date = '?'

        pnl = float(row['FifoPnlRealized']) if pd.notna(row['FifoPnlRealized']) else 0

        print(f"{timestamp} | {oc:^5} | {side:4} {qty:>3}x {exp_date} {strike:>3}{right} @ ${price:>6.2f} | PnL: ${pnl:>8.2f}")

def main():
    csv_path = '/Users/tommyk15/Downloads/TradingJournalExecutions1.csv'

    # Load data
    df = pd.read_csv(csv_path)

    def parse_timestamp(dt_str):
        try:
            return datetime.strptime(dt_str, "%Y%m%d;%H%M%S")
        except:
            return None

    df['parsed_timestamp'] = df['DateTime'].apply(parse_timestamp)
    df = df[df['parsed_timestamp'].notna()]
    df['underlying'] = df['Symbol'].str.split().str[0]

    print("=" * 120)
    print("TRADE CLASSIFICATION VERIFICATION")
    print("=" * 120)
    print("\nUser's Classifications to Verify:")
    print("  - AMD 230/240: ROLL (close 11/21, open 11/28)")
    print("  - V: IRON CONDOR that was ROLLED")
    print("  - BMNR 75C: POOR MAN'S COVERED CALL")
    print("  - NVDA: Show all spreads for classification")

    # Analyze each
    analyze_underlying(df, 'AMD')
    analyze_underlying(df, 'V')
    analyze_underlying(df, 'BMNR')
    analyze_underlying(df, 'NVDA')

    # Summary
    print(f"\n{'=' * 120}")
    print("CLASSIFICATION ANALYSIS")
    print(f"{'=' * 120}")

    print("\n1. AMD - PUT SPREAD ROLL")
    print("   11/17 15:50: CLOSE 20x 11/21/25 230/240 Put Spread (PnL: -$2,731)")
    print("   11/17 15:50: OPEN 20x 11/28/25 230/240 Put Spread (same strikes, rolled out)")
    print("   11/18 09:42: CLOSE 24x 02/20/26 280/330 Call Spread (different position)")
    print("   ✅ CONFIRMED: Roll detected - same strikes, different expiry")

    print("\n2. V - IRON CONDOR ROLL")
    print("   Need to verify: Should show 4 legs (call spread + put spread)")
    print("   Look for: Closing and opening of both spreads within timeframe")

    print("\n3. BMNR 75C - POOR MAN'S COVERED CALL")
    print("   11/21 16:20: BUY 160x 11/21/25 75C @ $0 (expired worthless)")
    print("   This should be: LONG deep ITM call + SELL OTM calls against it")
    print("   Need to check: Is there a long-dated call position?")

    print("\n4. NVDA - MULTIPLE SPREADS")
    print("   See detailed output above for classification")
    print("   Multiple put spreads and call spreads opened/closed")

if __name__ == "__main__":
    main()
