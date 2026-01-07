#!/usr/bin/env python3
"""POC: Pull all data for BMNR Bull Put 25/30 position from multiple sources.

Position Structure:
- Long 40x BMNR Jan 2026 $25 Put
- Short 40x BMNR Jan 2026 $30 Put

Run with: PYTHONPATH=src python scripts/test_bmnr_position_data.py
"""

import asyncio
from datetime import datetime
from decimal import Decimal

from ib_insync import IB, Option, Stock, util

# Patch for nested async
util.patchAsyncio()

# Position details
UNDERLYING = "BMNR"
EXPIRATION = "20260116"  # Jan 16, 2026
LONG_STRIKE = 25.0
SHORT_STRIKE = 30.0
QUANTITY = 40
MULTIPLIER = 100


def format_currency(value):
    """Format value as currency."""
    if value is None or (isinstance(value, float) and value != value):  # NaN check
        return "N/A"
    return f"${value:,.2f}"


def format_percent(value):
    """Format value as percentage."""
    if value is None or (isinstance(value, float) and value != value):
        return "N/A"
    return f"{value:.2%}"


def format_greek(value):
    """Format Greek value."""
    if value is None or (isinstance(value, float) and value != value):
        return "N/A"
    return f"{value:.4f}"


async def fetch_ibkr_data(ib: IB):
    """Fetch position data from IBKR."""
    print("\n" + "=" * 70)
    print("SOURCE 1: IBKR (Real-time)")
    print("=" * 70)

    results = {
        "connected": ib.isConnected(),
        "long_leg": None,
        "short_leg": None,
        "spread": None,
    }

    if not ib.isConnected():
        print("    ✗ Not connected to IBKR")
        return results

    # Get portfolio positions
    portfolio = ib.portfolio()
    bmnr_positions = [p for p in portfolio if p.contract.symbol == UNDERLYING]

    print(f"\n[IBKR] Found {len(bmnr_positions)} BMNR positions")

    long_leg = None
    short_leg = None

    for item in bmnr_positions:
        contract = item.contract
        if contract.secType != "OPT" or contract.right != "P":
            continue

        strike = contract.strike
        is_long = item.position > 0

        leg_data = {
            "symbol": contract.localSymbol,
            "strike": strike,
            "position": int(item.position),
            "market_price": item.marketPrice,
            "market_value": item.marketValue,
            "avg_cost": item.averageCost,
            "unrealized_pnl": item.unrealizedPNL,
            "realized_pnl": item.realizedPNL,
        }

        if strike == LONG_STRIKE and is_long:
            long_leg = leg_data
            results["long_leg"] = leg_data
            print(f"\n    LONG LEG: {contract.localSymbol}")
        elif strike == SHORT_STRIKE and not is_long:
            short_leg = leg_data
            results["short_leg"] = leg_data
            print(f"\n    SHORT LEG: {contract.localSymbol}")
        else:
            continue

        print(f"      Position: {leg_data['position']} contracts")
        print(f"      Market Price: {format_currency(leg_data['market_price'])}")
        print(f"      Market Value: {format_currency(leg_data['market_value'])}")
        print(f"      Avg Cost: {format_currency(leg_data['avg_cost'])}")
        print(f"      Unrealized P&L: {format_currency(leg_data['unrealized_pnl'])}")

    # Calculate spread totals
    if long_leg and short_leg:
        spread_data = {
            "net_market_value": long_leg["market_value"] + short_leg["market_value"],
            "net_unrealized_pnl": long_leg["unrealized_pnl"] + short_leg["unrealized_pnl"],
            "total_cost": (long_leg["avg_cost"] * abs(long_leg["position"])) -
                         (short_leg["avg_cost"] * abs(short_leg["position"])),
        }
        results["spread"] = spread_data

        print(f"\n    SPREAD TOTALS:")
        print(f"      Net Market Value: {format_currency(spread_data['net_market_value'])}")
        print(f"      Net Unrealized P&L: {format_currency(spread_data['net_unrealized_pnl'])}")

    # Fetch Greeks for each leg
    print(f"\n[IBKR] Fetching Greeks (market {'open' if datetime.now().hour < 16 else 'closed'})...")

    for strike, right in [(LONG_STRIKE, "P"), (SHORT_STRIKE, "P")]:
        option = Option(UNDERLYING, EXPIRATION, strike, right, "SMART")
        try:
            await ib.qualifyContractsAsync(option)
            ticker = ib.reqMktData(option, "106", False, False)
            await asyncio.sleep(2)

            leg_name = "LONG" if strike == LONG_STRIKE else "SHORT"
            print(f"\n    {leg_name} LEG Greeks ({option.localSymbol}):")
            print(f"      Bid: {format_currency(ticker.bid)}")
            print(f"      Ask: {format_currency(ticker.ask)}")
            print(f"      Last: {format_currency(ticker.last)}")

            if ticker.modelGreeks:
                g = ticker.modelGreeks
                print(f"      Delta: {format_greek(g.delta)}")
                print(f"      Gamma: {format_greek(g.gamma)}")
                print(f"      Theta: {format_greek(g.theta)}")
                print(f"      Vega: {format_greek(g.vega)}")
                print(f"      IV: {format_percent(g.impliedVol) if g.impliedVol else 'N/A'}")
                print(f"      Underlying: {format_currency(g.undPrice)}")

                # Store in results
                key = "long_leg" if strike == LONG_STRIKE else "short_leg"
                if results[key]:
                    results[key]["greeks"] = {
                        "delta": g.delta,
                        "gamma": g.gamma,
                        "theta": g.theta,
                        "vega": g.vega,
                        "iv": g.impliedVol,
                    }
            else:
                print("      Greeks: Not available (market closed)")

            ib.cancelMktData(option)
        except Exception as e:
            print(f"      Error: {e}")

    # Get underlying price
    print(f"\n[IBKR] Fetching underlying price...")
    stock = Stock(UNDERLYING, "SMART", "USD")
    try:
        await ib.qualifyContractsAsync(stock)
        ticker = ib.reqMktData(stock, "", False, False)
        await asyncio.sleep(1)

        print(f"    {UNDERLYING} Stock:")
        print(f"      Last: {format_currency(ticker.last)}")
        print(f"      Bid: {format_currency(ticker.bid)}")
        print(f"      Ask: {format_currency(ticker.ask)}")
        print(f"      Close: {format_currency(ticker.close)}")

        results["underlying_price"] = ticker.close if ticker.close else ticker.last
        ib.cancelMktData(stock)
    except Exception as e:
        print(f"    Error: {e}")

    # Get account P&L for this position
    print(f"\n[IBKR] Account-level P&L...")
    account = ib.managedAccounts()[0] if ib.managedAccounts() else None
    if account:
        ib.reqPnL(account)
        await asyncio.sleep(1)
        pnl = ib.pnl()
        for p in pnl:
            print(f"    Account: {p.account}")
            print(f"    Daily P&L: {format_currency(p.dailyPnL)}")
            print(f"    Total Unrealized: {format_currency(p.unrealizedPnL)}")
            print(f"    Total Realized: {format_currency(p.realizedPnL)}")

    return results


async def fetch_polygon_data():
    """Fetch data from Polygon.io."""
    print("\n" + "=" * 70)
    print("SOURCE 2: Polygon.io (15-min delayed)")
    print("=" * 70)

    try:
        from trading_journal.services.polygon_service import PolygonService
    except Exception as e:
        print(f"    ✗ Polygon service not available: {e}")
        return None

    results = {"long_leg": None, "short_leg": None, "underlying": None}

    try:
        service = PolygonService()
    except Exception as e:
        print(f"    ✗ Polygon API key not configured: {e}")
        return results

    async with service:
        # Check API access
        status = await service.check_api_status()
        print(f"\n[Polygon] API Status:")
        print(f"    Basic access: {'✓' if status['basic'] else '✗'}")
        print(f"    Options access: {'✓' if status['options'] else '✗'}")

        # Get underlying price
        print(f"\n[Polygon] Fetching {UNDERLYING} stock price...")
        quote = await service.get_underlying_price(UNDERLYING)
        if quote:
            print(f"    Price (prev close): {format_currency(float(quote.price))}")
            print(f"    Open: {format_currency(float(quote.open)) if quote.open else 'N/A'}")
            print(f"    High: {format_currency(float(quote.high)) if quote.high else 'N/A'}")
            print(f"    Low: {format_currency(float(quote.low)) if quote.low else 'N/A'}")
            print(f"    Volume: {quote.volume:,}" if quote.volume else "    Volume: N/A")
            results["underlying"] = {"price": float(quote.price)}
        else:
            print("    ✗ No quote data")

        # Get Greeks for each leg
        if status['options']:
            exp_date = datetime.strptime(EXPIRATION, "%Y%m%d")

            for strike, leg_name in [(LONG_STRIKE, "LONG"), (SHORT_STRIKE, "SHORT")]:
                print(f"\n[Polygon] Fetching {leg_name} leg Greeks (${strike} Put)...")

                greeks = await service.get_option_greeks(
                    underlying=UNDERLYING,
                    expiration=exp_date,
                    option_type="P",
                    strike=Decimal(str(strike)),
                    fetch_underlying_price=False,
                )

                if greeks:
                    key = "long_leg" if leg_name == "LONG" else "short_leg"
                    results[key] = {
                        "delta": float(greeks.delta) if greeks.delta else None,
                        "gamma": float(greeks.gamma) if greeks.gamma else None,
                        "theta": float(greeks.theta) if greeks.theta else None,
                        "vega": float(greeks.vega) if greeks.vega else None,
                        "iv": float(greeks.iv) if greeks.iv else None,
                        "option_price": float(greeks.option_price) if greeks.option_price else None,
                        "bid": float(greeks.bid) if greeks.bid else None,
                        "ask": float(greeks.ask) if greeks.ask else None,
                        "open_interest": greeks.open_interest,
                        "volume": greeks.volume,
                    }

                    print(f"    Option Price: {format_currency(results[key]['option_price'])}")
                    print(f"    Bid/Ask: {format_currency(results[key]['bid'])} / {format_currency(results[key]['ask'])}")
                    print(f"    Delta: {format_greek(results[key]['delta'])}")
                    print(f"    Gamma: {format_greek(results[key]['gamma'])}")
                    print(f"    Theta: {format_greek(results[key]['theta'])}")
                    print(f"    Vega: {format_greek(results[key]['vega'])}")
                    print(f"    IV: {format_percent(results[key]['iv']) if results[key]['iv'] else 'N/A'}")
                    print(f"    Open Interest: {results[key]['open_interest'] or 'N/A'}")
                    print(f"    Volume: {results[key]['volume'] or 'N/A'}")
                else:
                    print(f"    ✗ No data for ${strike} Put")

    return results


async def fetch_yfinance_data():
    """Fetch data from Yahoo Finance (free)."""
    print("\n" + "=" * 70)
    print("SOURCE 3: Yahoo Finance (Free)")
    print("=" * 70)

    results = {"underlying": None, "options": None}

    try:
        import yfinance as yf
    except ImportError:
        print("    ✗ yfinance not installed. Run: pip install yfinance")
        return results

    print(f"\n[yfinance] Fetching {UNDERLYING} data...")

    ticker = yf.Ticker(UNDERLYING)

    # Stock info
    try:
        info = ticker.info
        current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        prev_close = info.get("previousClose")

        print(f"    Current Price: {format_currency(current_price)}")
        print(f"    Previous Close: {format_currency(prev_close)}")
        print(f"    52-Week High: {format_currency(info.get('fiftyTwoWeekHigh'))}")
        print(f"    52-Week Low: {format_currency(info.get('fiftyTwoWeekLow'))}")
        print(f"    Market Cap: {format_currency(info.get('marketCap'))}")

        results["underlying"] = {
            "price": current_price,
            "prev_close": prev_close,
        }
    except Exception as e:
        print(f"    ✗ Stock info error: {e}")

    # Options chain
    print(f"\n[yfinance] Fetching options chain...")
    try:
        expirations = ticker.options
        print(f"    Available expirations: {len(expirations)}")

        # Find Jan 2026 expiration
        target_exp = "2026-01-16"
        if target_exp in expirations:
            print(f"    Found target expiration: {target_exp}")

            chain = ticker.option_chain(target_exp)
            puts = chain.puts

            # Filter for our strikes
            our_puts = puts[puts["strike"].isin([LONG_STRIKE, SHORT_STRIKE])]

            if not our_puts.empty:
                print(f"\n    Options for ${LONG_STRIKE} and ${SHORT_STRIKE} Puts:")
                results["options"] = {}

                for _, row in our_puts.iterrows():
                    strike = row["strike"]
                    leg_name = "long" if strike == LONG_STRIKE else "short"

                    results["options"][leg_name] = {
                        "strike": strike,
                        "last_price": row["lastPrice"],
                        "bid": row["bid"],
                        "ask": row["ask"],
                        "volume": row["volume"],
                        "open_interest": row["openInterest"],
                        "iv": row["impliedVolatility"],
                    }

                    print(f"\n    ${strike} Put:")
                    print(f"      Last: {format_currency(row['lastPrice'])}")
                    print(f"      Bid/Ask: {format_currency(row['bid'])} / {format_currency(row['ask'])}")
                    print(f"      Volume: {row['volume']}")
                    print(f"      Open Interest: {row['openInterest']}")
                    print(f"      IV: {format_percent(row['impliedVolatility'])}")
            else:
                print(f"    ✗ No options found for strikes ${LONG_STRIKE}, ${SHORT_STRIKE}")
        else:
            print(f"    ✗ Expiration {target_exp} not available")
            print(f"    Available: {expirations[:5]}...")
    except Exception as e:
        print(f"    ✗ Options chain error: {e}")

    return results


async def calculate_spread_analytics(ibkr_data, polygon_data, yf_data):
    """Calculate spread analytics from all sources."""
    print("\n" + "=" * 70)
    print("SPREAD ANALYTICS: BMNR Bull Put 25/30")
    print("=" * 70)

    # Get underlying price (prefer IBKR, then Polygon, then yfinance)
    underlying_price = None
    if ibkr_data and ibkr_data.get("underlying_price"):
        underlying_price = ibkr_data["underlying_price"]
        price_source = "IBKR"
    elif polygon_data and polygon_data.get("underlying"):
        underlying_price = polygon_data["underlying"]["price"]
        price_source = "Polygon"
    elif yf_data and yf_data.get("underlying"):
        underlying_price = yf_data["underlying"]["price"]
        price_source = "yfinance"

    print(f"\n[Underlying] {UNDERLYING}: {format_currency(underlying_price)} (from {price_source})")

    # Spread characteristics
    spread_width = SHORT_STRIKE - LONG_STRIKE
    max_profit = None
    max_loss = spread_width * QUANTITY * MULTIPLIER

    print(f"\n[Structure]")
    print(f"    Strategy: Bull Put Spread (Credit Spread)")
    print(f"    Long: {QUANTITY}x ${LONG_STRIKE} Put")
    print(f"    Short: {QUANTITY}x ${SHORT_STRIKE} Put")
    print(f"    Expiration: Jan 16, 2026")
    print(f"    Spread Width: ${spread_width}")
    print(f"    Contracts: {QUANTITY}")

    # P&L from IBKR
    if ibkr_data and ibkr_data.get("spread"):
        spread = ibkr_data["spread"]
        print(f"\n[P&L - IBKR Real-time]")
        print(f"    Net Market Value: {format_currency(spread['net_market_value'])}")
        print(f"    Net Unrealized P&L: {format_currency(spread['net_unrealized_pnl'])}")

    # Calculate net Greeks
    print(f"\n[Net Greeks - Combined from all legs]")

    # Try IBKR Greeks first
    if ibkr_data:
        long_greeks = ibkr_data.get("long_leg", {}).get("greeks", {})
        short_greeks = ibkr_data.get("short_leg", {}).get("greeks", {})

        if long_greeks and short_greeks:
            # Net delta = long_delta * qty + short_delta * (-qty)
            net_delta = (long_greeks.get("delta", 0) or 0) * QUANTITY + \
                       (short_greeks.get("delta", 0) or 0) * (-QUANTITY)
            net_gamma = (long_greeks.get("gamma", 0) or 0) * QUANTITY + \
                       (short_greeks.get("gamma", 0) or 0) * (-QUANTITY)
            net_theta = (long_greeks.get("theta", 0) or 0) * QUANTITY + \
                       (short_greeks.get("theta", 0) or 0) * (-QUANTITY)
            net_vega = (long_greeks.get("vega", 0) or 0) * QUANTITY + \
                      (short_greeks.get("vega", 0) or 0) * (-QUANTITY)

            print(f"    Source: IBKR")
            print(f"    Net Delta: {format_greek(net_delta)} (${net_delta * 100 * (underlying_price or 0):.2f} exposure)")
            print(f"    Net Gamma: {format_greek(net_gamma)}")
            print(f"    Net Theta: {format_greek(net_theta)} (${net_theta * 100:.2f}/day)")
            print(f"    Net Vega: {format_greek(net_vega)}")
        else:
            print("    IBKR Greeks not available (market closed)")

    # Try Polygon Greeks as backup
    if polygon_data and polygon_data.get("long_leg") and polygon_data.get("short_leg"):
        long_g = polygon_data["long_leg"]
        short_g = polygon_data["short_leg"]

        if long_g.get("delta") and short_g.get("delta"):
            net_delta = (long_g["delta"] or 0) * QUANTITY + (short_g["delta"] or 0) * (-QUANTITY)
            net_gamma = (long_g.get("gamma", 0) or 0) * QUANTITY + (short_g.get("gamma", 0) or 0) * (-QUANTITY)
            net_theta = (long_g.get("theta", 0) or 0) * QUANTITY + (short_g.get("theta", 0) or 0) * (-QUANTITY)
            net_vega = (long_g.get("vega", 0) or 0) * QUANTITY + (short_g.get("vega", 0) or 0) * (-QUANTITY)

            print(f"\n    Source: Polygon (backup)")
            print(f"    Net Delta: {format_greek(net_delta)}")
            print(f"    Net Gamma: {format_greek(net_gamma)}")
            print(f"    Net Theta: {format_greek(net_theta)} (${net_theta * 100:.2f}/day)")
            print(f"    Net Vega: {format_greek(net_vega)}")

    # Risk metrics
    print(f"\n[Risk Metrics]")
    print(f"    Max Risk: {format_currency(max_loss)} (spread width × contracts × 100)")
    if ibkr_data and ibkr_data.get("short_leg"):
        credit_received = abs(ibkr_data["short_leg"].get("avg_cost", 0) * QUANTITY) - \
                         abs(ibkr_data["long_leg"].get("avg_cost", 0) * QUANTITY)
        print(f"    Credit Received: {format_currency(credit_received)} (estimated)")
        print(f"    Max Profit: {format_currency(credit_received)} (credit received)")
        breakeven = SHORT_STRIKE - (credit_received / (QUANTITY * MULTIPLIER))
        print(f"    Breakeven: ${breakeven:.2f}")

    # Days to expiration
    exp_date = datetime.strptime(EXPIRATION, "%Y%m%d")
    dte = (exp_date - datetime.now()).days
    print(f"    Days to Expiration: {dte}")


async def main():
    """Main function to run all data fetches."""
    print("=" * 70)
    print("BMNR Bull Put 25/30 - Multi-Source Data POC")
    print("=" * 70)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    ib = IB()

    # Connect to IBKR
    try:
        await ib.connectAsync("127.0.0.1", 7496, clientId=97)
        ibkr_connected = True
    except Exception as e:
        print(f"\n⚠ IBKR connection failed: {e}")
        ibkr_connected = False

    try:
        # Fetch from all sources
        ibkr_data = await fetch_ibkr_data(ib) if ibkr_connected else None
        polygon_data = await fetch_polygon_data()
        yf_data = await fetch_yfinance_data()

        # Calculate combined analytics
        await calculate_spread_analytics(ibkr_data, polygon_data, yf_data)

        print("\n" + "=" * 70)
        print("POC Complete!")
        print("=" * 70)

    finally:
        if ibkr_connected:
            ib.disconnect()
            print("\nDisconnected from IBKR")


if __name__ == "__main__":
    asyncio.run(main())
