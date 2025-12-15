"""Trade Analytics Service - Greeks, IV metrics, and risk analytics calculations."""

import logging
import math
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from scipy.stats import norm

logger = logging.getLogger(__name__)


class StrategyType(str, Enum):
    """Options strategy types."""

    SINGLE = "Single"
    VERTICAL_CALL = "Vertical Call Spread"
    VERTICAL_PUT = "Vertical Put Spread"
    IRON_CONDOR = "Iron Condor"
    IRON_BUTTERFLY = "Iron Butterfly"
    BUTTERFLY = "Butterfly"
    CALENDAR = "Calendar"
    STRADDLE = "Straddle"
    STRANGLE = "Strangle"
    COVERED_CALL = "Covered Call"
    CASH_SECURED_PUT = "Cash Secured Put"
    COMPLEX = "Complex"


@dataclass
class LegData:
    """Data for a single option leg."""

    option_type: str  # "C" or "P"
    strike: Decimal
    expiration: datetime
    quantity: int  # Signed: positive for long, negative for short
    delta: Decimal | None = None
    gamma: Decimal | None = None
    theta: Decimal | None = None
    vega: Decimal | None = None
    iv: Decimal | None = None
    premium: Decimal | None = None


@dataclass
class TradeAnalytics:
    """Calculated analytics for a trade."""

    # Net Greeks (weighted sum across legs)
    net_delta: Decimal | None
    net_gamma: Decimal | None
    net_theta: Decimal | None
    net_vega: Decimal | None

    # IV metrics
    trade_iv: Decimal | None  # Short strike IV for credit strategies
    iv_percentile: Decimal | None
    iv_rank: Decimal | None

    # Risk analytics
    pop: Decimal | None  # Probability of profit (0-100)
    breakeven: list[Decimal]  # Can have multiple breakevens
    max_profit: Decimal | None
    max_risk: Decimal | None
    risk_reward_ratio: Decimal | None

    # Collateral
    collateral_required: Decimal | None

    # Days to expiration (for front month if multi-expiry)
    dte: int | None


class TradeAnalyticsService:
    """Service for calculating trade analytics.

    Computes Greeks, IV metrics, probability of profit, max profit/risk,
    and collateral requirements for options trades.
    """

    def __init__(self, risk_free_rate: Decimal = Decimal("0.05")):
        """Initialize analytics service.

        Args:
            risk_free_rate: Annual risk-free rate (default 5%)
        """
        self.risk_free_rate = risk_free_rate

    def calculate_net_greeks(self, legs: list[LegData], multiplier: int = 100) -> dict:
        """Calculate net Greeks for a multi-leg trade.

        Greeks are summed across legs, weighted by signed quantity.

        Args:
            legs: List of leg data with Greeks
            multiplier: Contract multiplier (default 100)

        Returns:
            Dictionary with net delta, gamma, theta, vega
        """
        net_delta = Decimal("0")
        net_gamma = Decimal("0")
        net_theta = Decimal("0")
        net_vega = Decimal("0")

        for leg in legs:
            qty = leg.quantity
            if leg.delta is not None:
                net_delta += leg.delta * qty
            if leg.gamma is not None:
                net_gamma += leg.gamma * qty
            if leg.theta is not None:
                net_theta += leg.theta * qty
            if leg.vega is not None:
                net_vega += leg.vega * qty

        return {
            "net_delta": net_delta * multiplier,
            "net_gamma": net_gamma * multiplier,
            "net_theta": net_theta * multiplier,
            "net_vega": net_vega * multiplier,
        }

    def get_trade_iv(self, legs: list[LegData], strategy_type: str) -> Decimal | None:
        """Get trade-level IV based on strategy type.

        For credit strategies, use the short strike IV.
        For debit strategies, use the long strike IV.
        For complex strategies, use weighted average.

        Args:
            legs: List of leg data with IV
            strategy_type: Type of strategy

        Returns:
            Trade-level IV or None if not available
        """
        if not legs:
            return None

        # Find short and long legs
        short_legs = [leg for leg in legs if leg.quantity < 0 and leg.iv is not None]
        long_legs = [leg for leg in legs if leg.quantity > 0 and leg.iv is not None]

        # Credit strategies: use short strike IV
        credit_strategies = [
            StrategyType.VERTICAL_CALL.value,
            StrategyType.VERTICAL_PUT.value,
            StrategyType.IRON_CONDOR.value,
            StrategyType.IRON_BUTTERFLY.value,
            StrategyType.CASH_SECURED_PUT.value,
            StrategyType.COVERED_CALL.value,
        ]

        if strategy_type in credit_strategies and short_legs:
            # Use average IV of short legs
            return sum(leg.iv for leg in short_legs) / len(short_legs)

        # Debit strategies: use long strike IV
        if long_legs:
            return sum(leg.iv for leg in long_legs) / len(long_legs)

        # Fallback: weighted average of all legs
        all_legs_with_iv = [leg for leg in legs if leg.iv is not None]
        if all_legs_with_iv:
            total_qty = sum(abs(leg.quantity) for leg in all_legs_with_iv)
            weighted_iv = sum(leg.iv * abs(leg.quantity) for leg in all_legs_with_iv)
            return weighted_iv / total_qty

        return None

    def calculate_pop_black_scholes(
        self,
        underlying_price: Decimal,
        breakeven: Decimal,
        iv: Decimal,
        dte: int,
        is_credit: bool = True,
    ) -> Decimal:
        """Calculate Probability of Profit using Black-Scholes model.

        Uses the cumulative normal distribution to estimate the probability
        that the underlying will be above/below breakeven at expiration.

        Args:
            underlying_price: Current underlying price
            breakeven: Breakeven price
            iv: Implied volatility (as decimal, e.g., 0.20 for 20%)
            dte: Days to expiration
            is_credit: True for credit strategies (profit if price stays away)

        Returns:
            Probability of profit as percentage (0-100)
        """
        if dte <= 0 or iv <= 0:
            return Decimal("50")  # 50-50 if no time or IV

        # Convert to float for scipy
        S = float(underlying_price)
        K = float(breakeven)
        sigma = float(iv)
        t = dte / 365.0
        r = float(self.risk_free_rate)

        # Calculate d2 (probability that S > K at expiration)
        d2 = (math.log(S / K) + (r - 0.5 * sigma**2) * t) / (sigma * math.sqrt(t))

        if is_credit:
            # Credit spread: profit if underlying stays above/below breakeven
            # For put credit spread: profit if S > breakeven
            # For call credit spread: profit if S < breakeven
            pop = norm.cdf(d2) * 100
        else:
            # Debit spread: profit if underlying moves past breakeven
            pop = (1 - norm.cdf(d2)) * 100

        return Decimal(str(round(pop, 2)))

    def calculate_breakevens(
        self,
        legs: list[LegData],
        strategy_type: str,
        net_premium: Decimal,
    ) -> list[Decimal]:
        """Calculate breakeven prices for a trade.

        Args:
            legs: List of leg data
            strategy_type: Type of strategy
            net_premium: Net premium received (positive) or paid (negative)

        Returns:
            List of breakeven prices
        """
        breakevens = []

        if not legs:
            return breakevens

        if strategy_type == StrategyType.VERTICAL_CALL.value:
            # Call credit spread: breakeven = lower strike + premium received
            # Call debit spread: breakeven = lower strike + premium paid
            lower_strike = min(leg.strike for leg in legs if leg.option_type == "C")
            breakevens.append(lower_strike + abs(net_premium))

        elif strategy_type == StrategyType.VERTICAL_PUT.value:
            # Put credit spread: breakeven = higher strike - premium received
            # Put debit spread: breakeven = higher strike - premium paid
            higher_strike = max(leg.strike for leg in legs if leg.option_type == "P")
            breakevens.append(higher_strike - abs(net_premium))

        elif strategy_type == StrategyType.IRON_CONDOR.value:
            # Two breakevens: put side and call side
            put_legs = [leg for leg in legs if leg.option_type == "P"]
            call_legs = [leg for leg in legs if leg.option_type == "C"]

            if put_legs:
                higher_put = max(leg.strike for leg in put_legs)
                breakevens.append(higher_put - abs(net_premium))

            if call_legs:
                lower_call = min(leg.strike for leg in call_legs)
                breakevens.append(lower_call + abs(net_premium))

        elif strategy_type == StrategyType.STRADDLE.value:
            # Two breakevens: strike ± premium
            strike = legs[0].strike
            breakevens.append(strike - abs(net_premium))
            breakevens.append(strike + abs(net_premium))

        elif strategy_type == StrategyType.STRANGLE.value:
            put_strike = min(leg.strike for leg in legs if leg.option_type == "P")
            call_strike = max(leg.strike for leg in legs if leg.option_type == "C")
            breakevens.append(put_strike - abs(net_premium))
            breakevens.append(call_strike + abs(net_premium))

        elif strategy_type == StrategyType.SINGLE.value:
            # Single option
            leg = legs[0]
            if leg.quantity > 0:  # Long
                if leg.option_type == "C":
                    breakevens.append(leg.strike + abs(net_premium))
                else:
                    breakevens.append(leg.strike - abs(net_premium))
            else:  # Short
                if leg.option_type == "C":
                    breakevens.append(leg.strike + abs(net_premium))
                else:
                    breakevens.append(leg.strike - abs(net_premium))

        elif strategy_type == StrategyType.CASH_SECURED_PUT.value:
            put_strike = legs[0].strike
            breakevens.append(put_strike - abs(net_premium))

        elif strategy_type == StrategyType.COVERED_CALL.value:
            # Breakeven is cost basis - premium received
            # This requires knowing the stock cost basis
            call_strike = legs[0].strike
            breakevens.append(call_strike)  # Simplified

        return sorted(breakevens)

    def calculate_max_profit_risk(
        self,
        legs: list[LegData],
        strategy_type: str,
        net_premium: Decimal,
        multiplier: int = 100,
    ) -> tuple[Decimal | None, Decimal | None]:
        """Calculate maximum profit and maximum risk for a trade.

        Args:
            legs: List of leg data
            strategy_type: Type of strategy
            net_premium: Net premium received (positive) or paid (negative)
            multiplier: Contract multiplier (default 100)

        Returns:
            Tuple of (max_profit, max_risk)
        """
        if not legs:
            return None, None

        # Get strike information
        strikes = sorted({leg.strike for leg in legs})

        if strategy_type == StrategyType.VERTICAL_CALL.value:
            # Credit spread: max profit = premium, max risk = width - premium
            # Debit spread: max profit = width - premium, max risk = premium
            width = max(strikes) - min(strikes)
            if net_premium > 0:  # Credit spread
                max_profit = net_premium * multiplier
                max_risk = (width - net_premium) * multiplier
            else:  # Debit spread
                max_profit = (width + net_premium) * multiplier
                max_risk = abs(net_premium) * multiplier
            return max_profit, max_risk

        elif strategy_type == StrategyType.VERTICAL_PUT.value:
            width = max(strikes) - min(strikes)
            if net_premium > 0:  # Credit spread
                max_profit = net_premium * multiplier
                max_risk = (width - net_premium) * multiplier
            else:  # Debit spread
                max_profit = (width + net_premium) * multiplier
                max_risk = abs(net_premium) * multiplier
            return max_profit, max_risk

        elif strategy_type == StrategyType.IRON_CONDOR.value:
            # Max profit = net premium received
            # Max risk = wider spread width - net premium
            put_strikes = sorted(leg.strike for leg in legs if leg.option_type == "P")
            call_strikes = sorted(leg.strike for leg in legs if leg.option_type == "C")

            put_width = put_strikes[-1] - put_strikes[0] if len(put_strikes) >= 2 else Decimal("0")
            call_width = call_strikes[-1] - call_strikes[0] if len(call_strikes) >= 2 else Decimal("0")
            max_width = max(put_width, call_width)

            max_profit = net_premium * multiplier
            max_risk = (max_width - net_premium) * multiplier
            return max_profit, max_risk

        elif strategy_type == StrategyType.IRON_BUTTERFLY.value:
            # Similar to iron condor but ATM short strikes
            put_strikes = sorted(leg.strike for leg in legs if leg.option_type == "P")
            call_strikes = sorted(leg.strike for leg in legs if leg.option_type == "C")

            if put_strikes and call_strikes:
                width = max(call_strikes[-1] - call_strikes[0], put_strikes[-1] - put_strikes[0])
                max_profit = net_premium * multiplier
                max_risk = (width - net_premium) * multiplier
                return max_profit, max_risk

        elif strategy_type in [StrategyType.STRADDLE.value, StrategyType.STRANGLE.value]:
            if net_premium > 0:  # Short straddle/strangle
                max_profit = net_premium * multiplier
                max_risk = None  # Unlimited
            else:  # Long straddle/strangle
                max_profit = None  # Unlimited
                max_risk = abs(net_premium) * multiplier
            return max_profit, max_risk

        elif strategy_type == StrategyType.SINGLE.value:
            leg = legs[0]
            if leg.quantity > 0:  # Long option
                max_profit = None  # Unlimited for calls
                max_risk = abs(net_premium) * multiplier
                if leg.option_type == "P":
                    max_profit = (leg.strike - abs(net_premium)) * multiplier
            else:  # Short option
                max_profit = abs(net_premium) * multiplier
                max_risk = None  # Unlimited for calls
                if leg.option_type == "P":
                    max_risk = (leg.strike - abs(net_premium)) * multiplier
            return max_profit, max_risk

        elif strategy_type == StrategyType.CASH_SECURED_PUT.value:
            leg = legs[0]
            max_profit = net_premium * multiplier
            max_risk = (leg.strike - net_premium) * multiplier
            return max_profit, max_risk

        elif strategy_type == StrategyType.COVERED_CALL.value:
            # Simplified - would need stock cost basis for accurate calculation
            max_profit = net_premium * multiplier
            max_risk = None  # Risk is in the stock
            return max_profit, max_risk

        return None, None

    def calculate_dte(self, legs: list[LegData]) -> int | None:
        """Calculate days to expiration for the front month.

        For calendar spreads, uses the nearest expiration.

        Args:
            legs: List of leg data

        Returns:
            Days to expiration or None
        """
        if not legs:
            return None

        expirations = [leg.expiration for leg in legs if leg.expiration]
        if not expirations:
            return None

        # Use front month (earliest expiration)
        front_exp = min(expirations)
        today = datetime.now().date()
        exp_date = front_exp.date() if isinstance(front_exp, datetime) else front_exp

        return (exp_date - today).days

    def calculate_analytics(
        self,
        legs: list[LegData],
        strategy_type: str,
        underlying_price: Decimal,
        net_premium: Decimal,
        iv_percentile: Decimal | None = None,
        iv_rank: Decimal | None = None,
        collateral: Decimal | None = None,
    ) -> TradeAnalytics:
        """Calculate complete analytics for a trade.

        Args:
            legs: List of leg data with Greeks and IV
            strategy_type: Type of strategy
            underlying_price: Current underlying price
            net_premium: Net premium received (positive) or paid (negative)
            iv_percentile: Pre-calculated IV percentile (optional)
            iv_rank: Pre-calculated IV rank (optional)
            collateral: Pre-calculated collateral requirement (optional)

        Returns:
            TradeAnalytics object with all calculations
        """
        # Net Greeks
        greeks = self.calculate_net_greeks(legs)

        # Trade-level IV
        trade_iv = self.get_trade_iv(legs, strategy_type)

        # Breakevens
        breakevens = self.calculate_breakevens(legs, strategy_type, net_premium)

        # Max profit/risk
        max_profit, max_risk = self.calculate_max_profit_risk(
            legs, strategy_type, net_premium
        )

        # Risk/reward ratio
        risk_reward = None
        if max_profit and max_risk and max_risk > 0:
            risk_reward = max_profit / max_risk

        # DTE
        dte = self.calculate_dte(legs)

        # Probability of profit
        pop = None
        if breakevens and trade_iv and dte and dte > 0:
            # Use first breakeven for simplicity
            is_credit = net_premium > 0
            pop = self.calculate_pop_black_scholes(
                underlying_price,
                breakevens[0],
                trade_iv,
                dte,
                is_credit,
            )

        return TradeAnalytics(
            net_delta=greeks["net_delta"],
            net_gamma=greeks["net_gamma"],
            net_theta=greeks["net_theta"],
            net_vega=greeks["net_vega"],
            trade_iv=trade_iv,
            iv_percentile=iv_percentile,
            iv_rank=iv_rank,
            pop=pop,
            breakeven=breakevens,
            max_profit=max_profit,
            max_risk=max_risk,
            risk_reward_ratio=risk_reward,
            collateral_required=collateral,
            dte=dte,
        )
