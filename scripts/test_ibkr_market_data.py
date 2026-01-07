#!/usr/bin/env python3
"""POC script to test IBKR market data fetching.

Run with: PYTHONPATH=src python scripts/test_ibkr_market_data.py
"""

import asyncio
from decimal import Decimal
from datetime import datetime

from ib_insync import IB, Stock, Option, util

# Enable nest_asyncio to allow nested event loops
util.patchAsyncio()


async def test_ibkr_market_data():
    """Test fetching market data from IBKR."""
    ib = IB()

    print("=" * 60)
    print("IBKR Market Data POC Test")
    print("=" * 60)

    # Connect to IBKR
    # Port 7496 = TWS Live, 7497 = TWS Paper, 4001 = Gateway Live, 4002 = Gateway Paper
    try:
        print("\n[1] Connecting to IBKR (TWS Live port 7496)...")
        await ib.connectAsync("127.0.0.1", 7496, clientId=99)
        print(f"    ✓ Connected: {ib.isConnected()}")
    except Exception as e:
        print(f"    ✗ Connection failed: {e}")
        print("\n    Make sure TWS or IB Gateway is running and API is enabled.")
        return

    try:
        # Test 1: Fetch stock price
        print("\n[2] Fetching stock price for SPY...")
        stock = Stock("SPY", "SMART", "USD")
        await ib.qualifyContractsAsync(stock)

        # Request market data
        ticker = ib.reqMktData(stock, "", False, False)
        await asyncio.sleep(2)  # Wait for data

        # Check if market is open (nan means closed/no data)
        market_price = ticker.marketPrice()
        is_market_open = market_price == market_price  # NaN check

        print(f"    Last price: {ticker.last}")
        print(f"    Bid: {ticker.bid}")
        print(f"    Ask: {ticker.ask}")
        print(f"    Close (prev day): {ticker.close}")
        print(f"    Market price: {market_price}")
        print(f"    Market open: {'Yes' if is_market_open else 'No (using close)'}")

        ib.cancelMktData(stock)

        # Test 2: Fetch option price
        print("\n[3] Fetching option price...")

        # Get the option chain to find valid strikes/expirations
        chains = await ib.reqSecDefOptParamsAsync(stock.symbol, "", stock.secType, stock.conId)

        if chains:
            chain = chains[0]
            print(f"    Exchange: {chain.exchange}")
            print(f"    Expirations available: {len(chain.expirations)}")
            print(f"    Strikes available: {len(chain.strikes)}")

            # Pick the nearest expiration and an ATM strike
            expirations = sorted(chain.expirations)
            nearest_exp = expirations[0] if expirations else None

            # Use close price if market price not available
            ref_price = ticker.marketPrice() if ticker.marketPrice() == ticker.marketPrice() else ticker.close
            if nearest_exp and ref_price:
                # Find strike closest to current price
                current_price = float(ref_price)
                strikes = sorted(chain.strikes)
                closest_strike = min(strikes, key=lambda x: abs(x - current_price))

                print(f"\n    Testing option: SPY {nearest_exp} C{closest_strike}")

                option = Option("SPY", nearest_exp, closest_strike, "C", "SMART")
                await ib.qualifyContractsAsync(option)

                # Request option market data with Greeks (generic tick 106)
                opt_ticker = ib.reqMktData(option, "106", False, False)
                await asyncio.sleep(3)  # Options data may take longer

                print(f"\n    Option Market Data:")
                print(f"    Last price: {opt_ticker.last}")
                print(f"    Bid: {opt_ticker.bid}")
                print(f"    Ask: {opt_ticker.ask}")
                print(f"    Market price: {opt_ticker.marketPrice()}")

                if opt_ticker.modelGreeks:
                    greeks = opt_ticker.modelGreeks
                    print(f"\n    Greeks (from model):")
                    print(f"    Delta: {greeks.delta}")
                    print(f"    Gamma: {greeks.gamma}")
                    print(f"    Theta: {greeks.theta}")
                    print(f"    Vega: {greeks.vega}")
                    print(f"    IV: {greeks.impliedVol}")
                    print(f"    Underlying price: {greeks.undPrice}")
                else:
                    print("\n    No Greeks available (market may be closed)")

                ib.cancelMktData(option)

        # Test 3: Check open positions
        print("\n[4] Checking current positions...")
        positions = ib.positions()
        print(f"    Found {len(positions)} positions")

        for pos in positions[:5]:  # Show first 5
            contract = pos.contract
            print(f"\n    {contract.symbol} {contract.secType}", end="")
            if contract.secType == "OPT":
                print(f" {contract.lastTradeDateOrContractMonth} {contract.right}{contract.strike}", end="")
            print(f" qty={pos.position} avgCost={pos.avgCost}")

        # Test 4: Fetch market price for a position
        if positions:
            print("\n[5] Fetching market price for first position...")
            pos = positions[0]
            contract = pos.contract

            await ib.qualifyContractsAsync(contract)
            pos_ticker = ib.reqMktData(contract, "106" if contract.secType == "OPT" else "", False, False)
            await asyncio.sleep(2)

            print(f"    Contract: {contract.localSymbol or contract.symbol}")
            print(f"    Market price: {pos_ticker.marketPrice()}")
            print(f"    Bid: {pos_ticker.bid}")
            print(f"    Ask: {pos_ticker.ask}")

            if pos_ticker.modelGreeks and contract.secType == "OPT":
                print(f"    Delta: {pos_ticker.modelGreeks.delta}")
                print(f"    IV: {pos_ticker.modelGreeks.impliedVol}")

            ib.cancelMktData(contract)

        print("\n" + "=" * 60)
        print("POC Test Complete!")
        print("=" * 60)

    finally:
        ib.disconnect()
        print("\nDisconnected from IBKR")


if __name__ == "__main__":
    asyncio.run(test_ibkr_market_data())
