#!/usr/bin/env python3
"""POC script to test IBKR portfolio and transaction data.

Run with: PYTHONPATH=src python scripts/test_ibkr_portfolio.py
"""

import asyncio
from decimal import Decimal
from datetime import datetime

from ib_insync import IB, util

# Enable nest_asyncio to allow nested event loops
util.patchAsyncio()


async def test_ibkr_portfolio():
    """Test fetching portfolio and transaction data from IBKR."""
    ib = IB()

    print("=" * 70)
    print("IBKR Portfolio & Transaction Data POC")
    print("=" * 70)

    try:
        print("\n[1] Connecting to IBKR (TWS Live port 7496)...")
        await ib.connectAsync("127.0.0.1", 7496, clientId=98)
        print(f"    ✓ Connected: {ib.isConnected()}")
    except Exception as e:
        print(f"    ✗ Connection failed: {e}")
        return

    try:
        # Test 1: Account Summary
        print("\n" + "=" * 70)
        print("[2] ACCOUNT SUMMARY")
        print("=" * 70)

        account_values = ib.accountSummary()

        # Key account metrics
        key_tags = [
            'NetLiquidation', 'TotalCashValue', 'GrossPositionValue',
            'AvailableFunds', 'BuyingPower', 'MaintMarginReq',
            'InitMarginReq', 'UnrealizedPnL', 'RealizedPnL',
            'ExcessLiquidity', 'FullMaintMarginReq'
        ]

        for av in account_values:
            if av.tag in key_tags:
                print(f"    {av.tag}: {av.value} {av.currency}")

        # Test 2: Portfolio - positions with market value and unrealized P&L
        print("\n" + "=" * 70)
        print("[3] PORTFOLIO (positions with market data)")
        print("=" * 70)

        portfolio = ib.portfolio()
        print(f"    Found {len(portfolio)} portfolio items\n")

        total_unrealized = 0
        total_market_value = 0

        for item in portfolio[:10]:  # Show first 10
            contract = item.contract
            symbol = contract.localSymbol or contract.symbol

            print(f"    {symbol}")
            print(f"      Position: {item.position}")
            print(f"      Market Price: ${item.marketPrice:.2f}")
            print(f"      Market Value: ${item.marketValue:,.2f}")
            print(f"      Avg Cost: ${item.averageCost:.2f}")
            print(f"      Unrealized PnL: ${item.unrealizedPNL:,.2f}")
            print(f"      Realized PnL: ${item.realizedPNL:,.2f}")
            print()

            total_unrealized += item.unrealizedPNL
            total_market_value += item.marketValue

        if len(portfolio) > 10:
            print(f"    ... and {len(portfolio) - 10} more positions")

        print(f"\n    TOTALS (all {len(portfolio)} positions):")
        print(f"    Total Market Value: ${total_market_value:,.2f}")
        print(f"    Total Unrealized PnL: ${total_unrealized:,.2f}")

        # Test 3: PnL Subscription (real-time P&L updates)
        print("\n" + "=" * 70)
        print("[4] REAL-TIME P&L (account level)")
        print("=" * 70)

        # Subscribe to account P&L
        account = ib.managedAccounts()[0] if ib.managedAccounts() else None
        if account:
            ib.reqPnL(account)
            await asyncio.sleep(1)

            pnl = ib.pnl()
            for p in pnl:
                print(f"    Account: {p.account}")
                print(f"    Daily PnL: ${p.dailyPnL:,.2f}" if p.dailyPnL else "    Daily PnL: N/A")
                print(f"    Unrealized PnL: ${p.unrealizedPnL:,.2f}" if p.unrealizedPnL else "    Unrealized PnL: N/A")
                print(f"    Realized PnL: ${p.realizedPnL:,.2f}" if p.realizedPnL else "    Realized PnL: N/A")

        # Test 4: Today's Executions
        print("\n" + "=" * 70)
        print("[5] TODAY'S EXECUTIONS")
        print("=" * 70)

        fills = ib.fills()
        print(f"    Found {len(fills)} fills today\n")

        for fill in fills[:5]:  # Show first 5
            exec_info = fill.execution
            contract = fill.contract
            symbol = contract.localSymbol or contract.symbol

            print(f"    {exec_info.time} | {symbol}")
            print(f"      Side: {exec_info.side} | Qty: {exec_info.shares} | Price: ${exec_info.price:.2f}")
            print(f"      Exec ID: {exec_info.execId}")
            if fill.commissionReport:
                print(f"      Commission: ${fill.commissionReport.commission:.2f}")
            print()

        if len(fills) > 5:
            print(f"    ... and {len(fills) - 5} more fills")

        # Test 5: Open Orders
        print("\n" + "=" * 70)
        print("[6] OPEN ORDERS")
        print("=" * 70)

        orders = ib.openOrders()
        print(f"    Found {len(orders)} open orders\n")

        for order in orders[:5]:
            print(f"    Order ID: {order.orderId}")
            print(f"      Action: {order.action} | Qty: {order.totalQuantity}")
            print(f"      Type: {order.orderType} | Limit: {order.lmtPrice if order.lmtPrice else 'N/A'}")
            print()

        # Test 6: Trades (order + execution combined)
        print("\n" + "=" * 70)
        print("[7] TRADES (order + execution)")
        print("=" * 70)

        trades = ib.trades()
        print(f"    Found {len(trades)} trades\n")

        for trade in trades[:3]:
            contract = trade.contract
            symbol = contract.localSymbol or contract.symbol
            print(f"    {symbol}")
            print(f"      Order: {trade.order.action} {trade.order.totalQuantity} @ {trade.order.orderType}")
            print(f"      Status: {trade.orderStatus.status}")
            print(f"      Filled: {trade.orderStatus.filled}/{trade.order.totalQuantity}")
            print()

        # Test 7: Single Position PnL
        print("\n" + "=" * 70)
        print("[8] SINGLE POSITION P&L (first option)")
        print("=" * 70)

        # Find first option position
        for item in portfolio:
            if item.contract.secType == "OPT":
                contract = item.contract
                ib.reqPnLSingle(account, "", contract.conId)
                await asyncio.sleep(1)

                pnl_single = ib.pnlSingle()
                for p in pnl_single:
                    if p.conId == contract.conId:
                        print(f"    Contract: {contract.localSymbol}")
                        print(f"    Position: {p.position}")
                        print(f"    Daily PnL: ${p.dailyPnL:,.2f}" if p.dailyPnL else "    Daily PnL: N/A")
                        print(f"    Unrealized PnL: ${p.unrealizedPnL:,.2f}" if p.unrealizedPnL else "    Unrealized PnL: N/A")
                        print(f"    Realized PnL: ${p.realizedPnL:,.2f}" if p.realizedPnL else "    Realized PnL: N/A")
                        print(f"    Market Value: ${p.value:,.2f}" if p.value else "    Market Value: N/A")
                        break
                break

        print("\n" + "=" * 70)
        print("POC Test Complete!")
        print("=" * 70)

    finally:
        ib.disconnect()
        print("\nDisconnected from IBKR")


if __name__ == "__main__":
    asyncio.run(test_ibkr_portfolio())
