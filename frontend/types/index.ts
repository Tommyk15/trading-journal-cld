// Core trading types matching backend API schemas

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
  strategy: string;
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
