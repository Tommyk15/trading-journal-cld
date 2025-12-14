"""Add Greeks and trade analytics schema

Revision ID: 20251214_greeks
Revises: 76552649b90a
Create Date: 2025-12-14

Adds:
- Greeks and IV columns to trades table (open and close snapshots)
- trade_leg_greeks table for per-leg Greeks
- underlying_iv_history table for IV rank/percentile calculations
- margin_settings table for per-underlying margin configuration
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251214_greeks"
down_revision: Union[str, None] = "76552649b90a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # ===========================================
    # Add Greeks/IV columns to trades table
    # ===========================================

    # Trade Open Snapshot
    op.add_column("trades", sa.Column("underlying_price_open", sa.Numeric(12, 4), nullable=True))
    op.add_column("trades", sa.Column("iv_open", sa.Numeric(8, 6), nullable=True))
    op.add_column("trades", sa.Column("iv_percentile_52w_open", sa.Numeric(5, 2), nullable=True))
    op.add_column("trades", sa.Column("iv_rank_52w_open", sa.Numeric(5, 2), nullable=True))
    op.add_column("trades", sa.Column("iv_percentile_custom_open", sa.Numeric(5, 2), nullable=True))
    op.add_column("trades", sa.Column("iv_rank_custom_open", sa.Numeric(5, 2), nullable=True))
    op.add_column("trades", sa.Column("iv_custom_period_days", sa.Integer(), nullable=True))
    op.add_column("trades", sa.Column("delta_open", sa.Numeric(8, 6), nullable=True))
    op.add_column("trades", sa.Column("gamma_open", sa.Numeric(8, 6), nullable=True))
    op.add_column("trades", sa.Column("theta_open", sa.Numeric(10, 4), nullable=True))
    op.add_column("trades", sa.Column("vega_open", sa.Numeric(10, 4), nullable=True))
    op.add_column("trades", sa.Column("rho_open", sa.Numeric(10, 4), nullable=True))
    op.add_column("trades", sa.Column("pop_open", sa.Numeric(5, 2), nullable=True))

    # Risk analytics at open
    op.add_column("trades", sa.Column("max_profit", sa.Numeric(12, 2), nullable=True))
    op.add_column("trades", sa.Column("max_risk", sa.Numeric(12, 2), nullable=True))
    op.add_column("trades", sa.Column("collateral_calculated", sa.Numeric(12, 2), nullable=True))
    op.add_column("trades", sa.Column("collateral_ibkr", sa.Numeric(12, 2), nullable=True))

    # Trade Close Snapshot
    op.add_column("trades", sa.Column("underlying_price_close", sa.Numeric(12, 4), nullable=True))
    op.add_column("trades", sa.Column("iv_close", sa.Numeric(8, 6), nullable=True))
    op.add_column("trades", sa.Column("delta_close", sa.Numeric(8, 6), nullable=True))
    op.add_column("trades", sa.Column("gamma_close", sa.Numeric(8, 6), nullable=True))
    op.add_column("trades", sa.Column("theta_close", sa.Numeric(10, 4), nullable=True))
    op.add_column("trades", sa.Column("vega_close", sa.Numeric(10, 4), nullable=True))
    op.add_column("trades", sa.Column("rho_close", sa.Numeric(10, 4), nullable=True))
    op.add_column("trades", sa.Column("pnl_percent", sa.Numeric(8, 4), nullable=True))

    # Greeks metadata
    op.add_column("trades", sa.Column("greeks_source", sa.String(20), nullable=True))
    op.add_column(
        "trades", sa.Column("greeks_pending", sa.Boolean(), nullable=False, server_default="false")
    )

    # ===========================================
    # Create trade_leg_greeks table
    # ===========================================
    op.create_table(
        "trade_leg_greeks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trade_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_type", sa.String(10), nullable=False),
        sa.Column("leg_index", sa.Integer(), nullable=False),
        sa.Column("underlying", sa.String(10), nullable=False),
        sa.Column("option_type", sa.String(1), nullable=True),
        sa.Column("strike", sa.Numeric(10, 2), nullable=True),
        sa.Column("expiration", sa.DateTime(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("delta", sa.Numeric(8, 6), nullable=True),
        sa.Column("gamma", sa.Numeric(8, 6), nullable=True),
        sa.Column("theta", sa.Numeric(10, 4), nullable=True),
        sa.Column("vega", sa.Numeric(10, 4), nullable=True),
        sa.Column("rho", sa.Numeric(10, 4), nullable=True),
        sa.Column("iv", sa.Numeric(8, 6), nullable=True),
        sa.Column("underlying_price", sa.Numeric(12, 4), nullable=True),
        sa.Column("option_price", sa.Numeric(10, 4), nullable=True),
        sa.Column("bid", sa.Numeric(10, 4), nullable=True),
        sa.Column("ask", sa.Numeric(10, 4), nullable=True),
        sa.Column("bid_ask_spread", sa.Numeric(10, 4), nullable=True),
        sa.Column("open_interest", sa.Integer(), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("data_source", sa.String(20), nullable=True),
        sa.Column("captured_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["trade_id"], ["trades.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trade_leg_greeks_trade_id", "trade_leg_greeks", ["trade_id"])

    # ===========================================
    # Create underlying_iv_history table
    # ===========================================
    op.create_table(
        "underlying_iv_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("underlying", sa.String(10), nullable=False),
        sa.Column("recorded_date", sa.Date(), nullable=False),
        sa.Column("iv", sa.Numeric(8, 6), nullable=False),
        sa.Column("iv_high", sa.Numeric(8, 6), nullable=True),
        sa.Column("iv_low", sa.Numeric(8, 6), nullable=True),
        sa.Column("underlying_price", sa.Numeric(12, 4), nullable=True),
        sa.Column("data_source", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("underlying", "recorded_date", name="uix_underlying_date"),
    )
    op.create_index("ix_underlying_iv_history_underlying", "underlying_iv_history", ["underlying"])
    op.create_index("ix_underlying_iv_history_recorded_date", "underlying_iv_history", ["recorded_date"])

    # ===========================================
    # Create margin_settings table
    # ===========================================
    op.create_table(
        "margin_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("underlying", sa.String(10), nullable=False),
        sa.Column("naked_put_margin_pct", sa.Numeric(5, 2), nullable=False, server_default="20.00"),
        sa.Column("naked_call_margin_pct", sa.Numeric(5, 2), nullable=False, server_default="20.00"),
        sa.Column("spread_margin_pct", sa.Numeric(5, 2), nullable=False, server_default="100.00"),
        sa.Column("iron_condor_margin_pct", sa.Numeric(5, 2), nullable=False, server_default="100.00"),
        sa.Column("notes", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("underlying"),
    )
    op.create_index("ix_margin_settings_underlying", "margin_settings", ["underlying"])


def downgrade() -> None:
    """Downgrade database schema."""
    # Drop new tables
    op.drop_table("margin_settings")
    op.drop_table("underlying_iv_history")
    op.drop_table("trade_leg_greeks")

    # Drop columns from trades table (in reverse order)
    op.drop_column("trades", "greeks_pending")
    op.drop_column("trades", "greeks_source")
    op.drop_column("trades", "pnl_percent")
    op.drop_column("trades", "rho_close")
    op.drop_column("trades", "vega_close")
    op.drop_column("trades", "theta_close")
    op.drop_column("trades", "gamma_close")
    op.drop_column("trades", "delta_close")
    op.drop_column("trades", "iv_close")
    op.drop_column("trades", "underlying_price_close")
    op.drop_column("trades", "collateral_ibkr")
    op.drop_column("trades", "collateral_calculated")
    op.drop_column("trades", "max_risk")
    op.drop_column("trades", "max_profit")
    op.drop_column("trades", "pop_open")
    op.drop_column("trades", "rho_open")
    op.drop_column("trades", "vega_open")
    op.drop_column("trades", "theta_open")
    op.drop_column("trades", "gamma_open")
    op.drop_column("trades", "delta_open")
    op.drop_column("trades", "iv_custom_period_days")
    op.drop_column("trades", "iv_rank_custom_open")
    op.drop_column("trades", "iv_percentile_custom_open")
    op.drop_column("trades", "iv_rank_52w_open")
    op.drop_column("trades", "iv_percentile_52w_open")
    op.drop_column("trades", "iv_open")
    op.drop_column("trades", "underlying_price_open")
