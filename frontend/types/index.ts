// Core trading types matching backend API schemas

export interface Tag {
  id: number;
  name: string;
  color: string;
  created_at: string;
}

export interface Execution {
  id: number;
  exec_id: string;
  symbol: string;
  underlying: string;
  security_type: string;
  side: string;
  open_close_indicator?: string; // O = Open, C = Close
  quantity: number;
  price: number;
  commission: number;
  net_amount: number;
  execution_time: string;
  account_id: string;
  order_id: number;
  perm_id: number;
  option_type?: string;
  strike?: number;
  expiration?: string;
  multiplier?: number;
  trade_id?: number | null;
  created_at: string;
}

export interface Trade {
  id: number;
  symbol: string;
  underlying_symbol: string;
  underlying: string;
  strategy: string;
  strategy_type: string;
  side: string;
  quantity: number;
  avg_open_price: number;
  avg_close_price?: number;
  realized_pnl?: number;
  commission_total: number;
  opened_at: string;
  closed_at?: string;
  status: string;
  executions: Execution[];
  created_at: string;
  updated_at: string;

  // Trade Open Snapshot (Greeks & IV at entry)
  underlying_price_open?: number;
  iv_open?: number;
  iv_percentile_52w_open?: number;
  iv_rank_52w_open?: number;
  delta_open?: number;
  gamma_open?: number;
  theta_open?: number;
  vega_open?: number;
  pop_open?: number;
  max_profit?: number;
  max_risk?: number;

  // Trade Close Snapshot
  underlying_price_close?: number;
  iv_close?: number;
  delta_close?: number;
  pnl_percent?: number;

  // Greeks metadata
  greeks_source?: string;
  greeks_pending?: boolean;

  // Tags
  tag_list?: Tag[];
}

export interface Position {
  id: number;
  symbol: string;
  underlying_symbol: string;
  position_type: string;
  quantity: number;
  avg_cost: number;
  current_price?: number;
  market_value?: number;
  unrealized_pnl?: number;
  strike?: number;
  expiration?: string;
  option_type?: string;
  account_id: string;
  last_updated: string;
}

export interface Greeks {
  id: number;
  position_id: number;
  delta?: number;
  gamma?: number;
  theta?: number;
  vega?: number;
  rho?: number;
  implied_volatility?: number;
  timestamp: string;
}

export interface WinRateMetrics {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  total_pnl: number;
  avg_win: number;
  avg_loss: number;
  profit_factor: number;
  largest_win: number;
  largest_loss: number;
}

export interface StrategyBreakdown {
  strategy: string;
  trade_count: number;
  win_rate: number;
  total_pnl: number;
  avg_pnl_per_trade: number;
  profit_factor: number;
}

export interface UnderlyingBreakdown {
  underlying_symbol: string;
  trade_count: number;
  win_rate: number;
  total_pnl: number;
  avg_pnl_per_trade: number;
}

export interface MonthlyPerformance {
  year: number;
  month: number;
  trade_count: number;
  total_pnl: number;
  win_rate: number;
  best_trade: number;
  worst_trade: number;
}

export interface CumulativePnL {
  date: string;
  cumulative_pnl: number;
  trade_count: number;
}

export interface DailyPnL {
  date: string;
  daily_pnl: number;
  trade_count: number;
  cumulative_pnl: number;
}

export interface DrawdownMetrics {
  current_drawdown: number;
  current_drawdown_percent: number;
  max_drawdown: number;
  max_drawdown_percent: number;
  peak_value: number;
  current_value: number;
  days_in_drawdown: number;
}

export interface SharpeRatioMetrics {
  sharpe_ratio: number;
  annual_return: number;
  annual_volatility: number;
  risk_free_rate: number;
  total_days: number;
}

export interface UpcomingExpiration {
  expiration_date: string;
  days_until: number;
  position_count: number;
  total_quantity: number;
  positions: Position[];
}

export interface TradesByWeek {
  week_start: string;
  week_end: string;
  trade_count: number;
  total_pnl: number;
  win_rate: number;
}

export interface RollChain {
  chain_length: number;
  total_pnl: number;
  first_trade_date: string;
  last_trade_date: string;
  trades: Trade[];
}

// Filter types
export interface TradeFilters {
  strategy?: string;
  underlying_symbol?: string;
  status?: string;
  start_date?: string;
  end_date?: string;
}

export interface PositionFilters {
  underlying_symbol?: string;
  position_type?: string;
}

// Manual trade creation types
export interface ManualTradeCreateRequest {
  execution_ids: number[];
  strategy_type: string;
  custom_strategy?: string;
  notes?: string;
  tags?: string;
}

export interface TradeExecutionsUpdateRequest {
  add_execution_ids?: number[];
  remove_execution_ids?: number[];
}

export interface SuggestedGroupFill {
  id: number;
  action: string;
  quantity: number;
  price: number;
  execution_time: string;
  net_amount: number;
}

export interface SuggestedGroupLeg {
  option_type?: string;
  strike?: number;
  expiration?: string;
  security_type: string;
  total_quantity: number;
  actions: string[];
  fills: SuggestedGroupFill[];
}

export interface SuggestedGroup {
  execution_ids: number[];
  suggested_strategy: string;
  underlying: string;
  total_pnl: number;
  status: string;
  legs: SuggestedGroupLeg[];
  open_date?: string;
  close_date?: string;
  num_executions: number;
}

export interface SuggestGroupingResponse {
  groups: SuggestedGroup[];
  message: string;
}

// Strategy options constant
export const STRATEGY_OPTIONS = [
  'Long Call',
  'Short Call',
  'Long Put',
  'Short Put',
  'Bull Call Spread',
  'Bear Call Spread',
  'Bull Put Spread',
  'Bear Put Spread',
  'Iron Condor',
  'Butterfly',
  'Calendar Spread',
  'Diagonal Spread',
  'Covered Call',
  'Cash Secured Put',
  'Straddle',
  'Strangle',
  'Custom',
] as const;

export type StrategyType = (typeof STRATEGY_OPTIONS)[number];

// Dashboard types
export type TimePeriod = 'all' | 'ytd' | 'monthly' | 'weekly';

export interface PortfolioGreeksSummary {
  total_delta: number;
  total_gamma: number;
  total_theta: number;
  total_vega: number;
  position_count: number;
  last_updated: string | null;
}

export interface StreakInfo {
  max_consecutive_wins: number;
  max_consecutive_losses: number;
  current_streak: number;
  current_streak_type: 'win' | 'loss' | 'none';
}

export interface StrategyStats {
  strategy_type: string;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  total_pnl: number;
  total_commission: number;
  net_pnl: number;
  average_pnl: number;
}

export interface UnderlyingStats {
  underlying: string;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  total_pnl: number;
  total_commission: number;
  net_pnl: number;
  average_pnl: number;
}

export interface DashboardSummary {
  // Core metrics
  total_pnl: number;
  total_trades: number;
  win_rate: number;
  avg_winner: number;
  avg_loser: number;
  profit_factor: number | null;
  max_drawdown_percent: number;

  // Daily metrics
  avg_profit_per_day: number;
  trading_days: number;

  // Best/Worst performers
  best_strategy: StrategyStats | null;
  worst_strategy: StrategyStats | null;
  best_ticker: UnderlyingStats | null;
  worst_ticker: UnderlyingStats | null;

  // Risk metrics
  sharpe_ratio: number | null;
  sortino_ratio: number | null;
  expectancy: number;

  // Streak info
  streak_info: StreakInfo;

  // Portfolio Greeks
  portfolio_greeks: PortfolioGreeksSummary | null;
}

export interface MetricsTimePoint {
  date: string;
  cumulative_pnl: number;
  trade_count: number;
  win_rate: number;
  profit_factor: number | null;
  drawdown_percent: number;
}

export interface MetricsTimeSeriesResponse {
  data_points: MetricsTimePoint[];
  period: TimePeriod;
  start_date: string | null;
  end_date: string | null;
}

// Trade Analytics types
export interface TradeAnalytics {
  trade_id: number;
  underlying: string;
  strategy_type: string;
  status: string;
  // Net Greeks
  net_delta: number | null;
  net_gamma: number | null;
  net_theta: number | null;
  net_vega: number | null;
  // IV metrics
  trade_iv: number | null;
  iv_percentile_52w: number | null;
  iv_rank_52w: number | null;
  iv_percentile_custom: number | null;
  iv_rank_custom: number | null;
  // Risk analytics
  pop: number | null;
  breakevens: number[];
  max_profit: number | null;
  max_risk: number | null;
  risk_reward_ratio: number | null;
  pnl_percent: number | null;
  // Collateral
  collateral_calculated: number | null;
  collateral_ibkr: number | null;
  // Time
  dte: number | null;
  days_held: number | null;
  // Metadata
  greeks_source: string | null;
  greeks_pending: boolean;
  underlying_price: number | null;
}

export interface LegGreeks {
  leg_index: number;
  option_type: string | null;
  strike: number | null;
  expiration: string | null;
  quantity: number;
  delta: number | null;
  gamma: number | null;
  theta: number | null;
  vega: number | null;
  rho: number | null;
  iv: number | null;
  underlying_price: number | null;
  option_price: number | null;
  bid: number | null;
  ask: number | null;
  bid_ask_spread: number | null;
  open_interest: number | null;
  volume: number | null;
  data_source: string | null;
  captured_at: string | null;
}

export interface TradeLegsResponse {
  trade_id: number;
  snapshot_type: string;
  legs: LegGreeks[];
  captured_at: string | null;
}

export interface FetchGreeksResponse {
  trade_id: number;
  success: boolean;
  legs_fetched: number;
  source: string | null;
  message: string;
}
