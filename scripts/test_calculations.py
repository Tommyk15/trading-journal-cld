#!/usr/bin/env python3
"""Test script for calculation services."""

import sys
from datetime import datetime, timedelta
from decimal import Decimal

sys.path.insert(0, "src")

from trading_journal.services.trade_analytics_service import (
    LegData,
    StrategyType,
    TradeAnalyticsService,
)


def test_trade_analytics():
    """Test TradeAnalyticsService calculations."""
    print("=" * 60)
    print("Testing Trade Analytics Service")
    print("=" * 60)

    service = TradeAnalyticsService(risk_free_rate=Decimal("0.0358"))

    # Test 1: Vertical Put Credit Spread
    print("\n1. Testing Put Credit Spread (SPY 580/575)...")
    expiration = datetime.now() + timedelta(days=30)
    legs = [
        LegData(
            option_type="P",
            strike=Decimal("580"),
            expiration=expiration,
            quantity=-1,  # Short
            delta=Decimal("-0.30"),
            gamma=Decimal("0.02"),
            theta=Decimal("-0.15"),
            vega=Decimal("0.20"),
            iv=Decimal("0.15"),
            premium=Decimal("3.50"),
        ),
        LegData(
            option_type="P",
            strike=Decimal("575"),
            expiration=expiration,
            quantity=1,  # Long
            delta=Decimal("-0.25"),
            gamma=Decimal("0.02"),
            theta=Decimal("-0.12"),
            vega=Decimal("0.18"),
            iv=Decimal("0.16"),
            premium=Decimal("2.00"),
        ),
    ]

    net_premium = Decimal("1.50")  # Credit received
    underlying_price = Decimal("600")

    analytics = service.calculate_analytics(
        legs=legs,
        strategy_type=StrategyType.VERTICAL_PUT.value,
        underlying_price=underlying_price,
        net_premium=net_premium,
    )

    print(f"   Net Delta: {analytics.net_delta}")
    print(f"   Net Theta: {analytics.net_theta}")
    print(f"   Trade IV: {float(analytics.trade_iv) * 100:.1f}%")
    print(f"   Breakeven: ${analytics.breakeven[0] if analytics.breakeven else 'N/A'}")
    print(f"   Max Profit: ${analytics.max_profit}")
    print(f"   Max Risk: ${analytics.max_risk}")
    print(f"   PoP: {analytics.pop}%")
    print(f"   DTE: {analytics.dte} days")

    # Test 2: Iron Condor
    print("\n2. Testing Iron Condor (SPY 570/575 - 625/630)...")
    legs = [
        # Put spread
        LegData(
            option_type="P",
            strike=Decimal("575"),
            expiration=expiration,
            quantity=-1,
            delta=Decimal("-0.20"),
            iv=Decimal("0.18"),
        ),
        LegData(
            option_type="P",
            strike=Decimal("570"),
            expiration=expiration,
            quantity=1,
            delta=Decimal("-0.15"),
            iv=Decimal("0.19"),
        ),
        # Call spread
        LegData(
            option_type="C",
            strike=Decimal("625"),
            expiration=expiration,
            quantity=-1,
            delta=Decimal("0.20"),
            iv=Decimal("0.14"),
        ),
        LegData(
            option_type="C",
            strike=Decimal("630"),
            expiration=expiration,
            quantity=1,
            delta=Decimal("0.15"),
            iv=Decimal("0.13"),
        ),
    ]

    net_premium = Decimal("2.00")
    analytics = service.calculate_analytics(
        legs=legs,
        strategy_type=StrategyType.IRON_CONDOR.value,
        underlying_price=underlying_price,
        net_premium=net_premium,
    )

    print(f"   Net Delta: {analytics.net_delta}")
    print(f"   Trade IV: {float(analytics.trade_iv) * 100:.1f}%")
    print(f"   Breakevens: {[f'${b}' for b in analytics.breakeven]}")
    print(f"   Max Profit: ${analytics.max_profit}")
    print(f"   Max Risk: ${analytics.max_risk}")
    print(f"   Risk/Reward: {float(analytics.risk_reward_ratio):.2f}" if analytics.risk_reward_ratio else "   Risk/Reward: N/A")

    # Test 3: Single Long Call
    print("\n3. Testing Long Call (SPY 600C)...")
    legs = [
        LegData(
            option_type="C",
            strike=Decimal("600"),
            expiration=expiration,
            quantity=1,
            delta=Decimal("0.50"),
            gamma=Decimal("0.03"),
            theta=Decimal("-0.20"),
            vega=Decimal("0.30"),
            iv=Decimal("0.15"),
            premium=Decimal("8.00"),
        ),
    ]

    net_premium = Decimal("-8.00")  # Debit paid
    analytics = service.calculate_analytics(
        legs=legs,
        strategy_type=StrategyType.SINGLE.value,
        underlying_price=underlying_price,
        net_premium=net_premium,
    )

    print(f"   Net Delta: {analytics.net_delta}")
    print(f"   Net Theta: {analytics.net_theta}")
    print(f"   Breakeven: ${analytics.breakeven[0] if analytics.breakeven else 'N/A'}")
    print(f"   Max Risk: ${analytics.max_risk}")

    # Test 4: PoP Calculation
    print("\n4. Testing PoP Calculations...")

    # Credit spread: high PoP when breakeven far from current price
    pop1 = service.calculate_pop_black_scholes(
        underlying_price=Decimal("600"),
        breakeven=Decimal("575"),
        iv=Decimal("0.15"),
        dte=30,
        is_credit=True,
    )
    print(f"   Credit spread (BE at $575, SPY at $600): PoP = {pop1}%")

    # Debit spread: low PoP when breakeven far from current price
    pop2 = service.calculate_pop_black_scholes(
        underlying_price=Decimal("600"),
        breakeven=Decimal("620"),
        iv=Decimal("0.15"),
        dte=30,
        is_credit=False,
    )
    print(f"   Debit spread (BE at $620, SPY at $600): PoP = {pop2}%")

    # Test 5: Breakeven calculations
    print("\n5. Testing Breakeven Calculations...")

    # Straddle
    legs = [
        LegData(option_type="C", strike=Decimal("600"), expiration=expiration, quantity=1),
        LegData(option_type="P", strike=Decimal("600"), expiration=expiration, quantity=1),
    ]
    breakevens = service.calculate_breakevens(
        legs=legs,
        strategy_type=StrategyType.STRADDLE.value,
        net_premium=Decimal("-15.00"),
    )
    print(f"   Straddle at $600 (premium $15): BEs = {[f'${b}' for b in breakevens]}")

    print("\n" + "=" * 60)
    print("Trade Analytics tests complete!")
    print("=" * 60)


if __name__ == "__main__":
    test_trade_analytics()
