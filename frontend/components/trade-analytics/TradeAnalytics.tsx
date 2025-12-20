'use client';

import { useState } from 'react';
import { RefreshCw, ChevronDown, ChevronUp, TrendingUp, TrendingDown } from 'lucide-react';
import { api } from '@/lib/api/client';
import { TradeAnalytics as TradeAnalyticsType, LegGreeks, TradeLegsResponse, FetchGreeksResponse } from '@/types';
import { formatCurrency, formatPercent, getPnlColor } from '@/lib/utils';
import LegGreeksTable from './LegGreeksTable';

interface TradeAnalyticsProps {
  tradeId: number;
  analytics: TradeAnalyticsType | null;
  tradeStatus?: string;
  onAnalyticsUpdate?: (analytics: TradeAnalyticsType) => void;
}

export default function TradeAnalytics({ tradeId, analytics, tradeStatus, onAnalyticsUpdate }: TradeAnalyticsProps) {
  const [loading, setLoading] = useState(false);
  const [fetchingGreeks, setFetchingGreeks] = useState(false);
  const [legs, setLegs] = useState<LegGreeks[]>([]);
  const [showLegs, setShowLegs] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchGreeks = async () => {
    setFetchingGreeks(true);
    setError(null);
    try {
      const response = await api.tradeAnalytics.fetchGreeks(tradeId, true) as FetchGreeksResponse;
      if (response.success && response.legs_fetched > 0) {
        // Refetch analytics after Greeks update
        const updatedAnalytics = await api.tradeAnalytics.get(tradeId) as TradeAnalyticsType;
        onAnalyticsUpdate?.(updatedAnalytics);
      } else if (response.success && response.legs_fetched === 0) {
        // No legs to fetch (likely a closed trade)
        setError(response.message || 'No active option legs to fetch Greeks for. Greeks can only be fetched for open trades.');
      } else {
        setError(response.message);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch Greeks');
    } finally {
      setFetchingGreeks(false);
    }
  };

  const loadLegs = async () => {
    if (legs.length > 0) {
      setShowLegs(!showLegs);
      return;
    }

    setLoading(true);
    try {
      const response = await api.tradeAnalytics.getLegs(tradeId) as TradeLegsResponse;
      setLegs(response.legs);
      setShowLegs(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load legs');
    } finally {
      setLoading(false);
    }
  };

  const formatGreek = (value: number | string | null, decimals: number = 4) => {
    if (value === null || value === undefined) return '—';
    const num = Number(value);
    const sign = num >= 0 ? '+' : '';
    return `${sign}${num.toFixed(decimals)}`;
  };

  const formatIV = (value: number | string | null) => {
    if (value === null || value === undefined) return '—';
    const num = Number(value);
    return `${(num * 100).toFixed(1)}%`;
  };

  const getGreekColor = (value: number | string | null) => {
    if (value === null || value === undefined) return 'text-gray-500 dark:text-gray-400';
    const num = Number(value);
    return num >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400';
  };

  // Check if Greeks have actually been fetched (not just empty analytics record)
  const hasGreeksData = analytics && (
    analytics.net_delta !== null ||
    analytics.net_gamma !== null ||
    analytics.net_theta !== null ||
    analytics.net_vega !== null ||
    analytics.greeks_source !== null
  );

  // Check if trade is closed
  const isClosed = tradeStatus === 'CLOSED' || analytics?.status === 'CLOSED';

  // No analytics yet or no Greeks data - show fetch button
  if (!analytics || analytics.greeks_pending || !hasGreeksData) {
    return (
      <div className="mt-4 p-4 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between">
          <div>
            <h4 className="font-medium text-gray-900 dark:text-white">Trade Analytics</h4>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {analytics?.greeks_pending
                ? 'Greeks fetch pending'
                : isClosed
                  ? 'Greeks not available for closed trades (options may have expired)'
                  : 'No Greeks data available - click to fetch from Polygon.io'}
            </p>
          </div>
          {!isClosed && (
            <button
              onClick={fetchGreeks}
              disabled={fetchingGreeks}
              className="flex items-center gap-2 px-3 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <RefreshCw className={`h-4 w-4 ${fetchingGreeks ? 'animate-spin' : ''}`} />
              {fetchingGreeks ? 'Fetching...' : 'Fetch Greeks'}
            </button>
          )}
        </div>
        {error && (
          <p className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>
        )}
      </div>
    );
  }

  return (
    <div className="mt-4 p-4 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h4 className="font-medium text-gray-900 dark:text-white">Trade Analytics</h4>
          {analytics.greeks_source && (
            <span className="text-xs px-2 py-0.5 bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded">
              {analytics.greeks_source}
            </span>
          )}
        </div>
        <button
          onClick={fetchGreeks}
          disabled={fetchingGreeks}
          className="flex items-center gap-1 px-2 py-1 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 rounded"
          title="Refresh Greeks"
        >
          <RefreshCw className={`h-3 w-3 ${fetchingGreeks ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {error && (
        <p className="mb-4 text-sm text-red-600 dark:text-red-400">{error}</p>
      )}

      {/* Analytics Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {/* Price & IV Section */}
        <div className="space-y-2">
          <h5 className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Price & IV</h5>
          <div className="space-y-1">
            <div className="flex justify-between">
              <span className="text-sm text-gray-600 dark:text-gray-300">Underlying</span>
              <span className="text-sm font-medium text-gray-900 dark:text-white">
                {analytics.underlying_price ? formatCurrency(analytics.underlying_price) : '—'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-gray-600 dark:text-gray-300">Trade IV</span>
              <span className="text-sm font-medium text-gray-900 dark:text-white">
                {formatIV(analytics.trade_iv)}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-gray-600 dark:text-gray-300">IV Rank</span>
              <span className="text-sm font-medium text-gray-900 dark:text-white">
                {analytics.iv_rank_52w !== null ? `${analytics.iv_rank_52w.toFixed(0)}%` : '—'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-gray-600 dark:text-gray-300">IV Percentile</span>
              <span className="text-sm font-medium text-gray-900 dark:text-white">
                {analytics.iv_percentile_52w !== null ? `${analytics.iv_percentile_52w.toFixed(0)}%` : '—'}
              </span>
            </div>
          </div>
        </div>

        {/* Net Greeks Section */}
        <div className="space-y-2">
          <h5 className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Net Greeks</h5>
          <div className="space-y-1">
            <div className="flex justify-between">
              <span className="text-sm text-gray-600 dark:text-gray-300">Delta</span>
              <span className={`text-sm font-medium ${getGreekColor(analytics.net_delta)}`}>
                {formatGreek(analytics.net_delta, 2)}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-gray-600 dark:text-gray-300">Gamma</span>
              <span className={`text-sm font-medium ${getGreekColor(analytics.net_gamma)}`}>
                {formatGreek(analytics.net_gamma, 4)}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-gray-600 dark:text-gray-300">Theta</span>
              <span className={`text-sm font-medium ${getGreekColor(analytics.net_theta)}`}>
                {analytics.net_theta !== null ? formatCurrency(analytics.net_theta) : '—'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-gray-600 dark:text-gray-300">Vega</span>
              <span className={`text-sm font-medium ${getGreekColor(analytics.net_vega)}`}>
                {analytics.net_vega !== null ? formatCurrency(analytics.net_vega) : '—'}
              </span>
            </div>
          </div>
        </div>

        {/* Risk Metrics Section */}
        <div className="space-y-2">
          <h5 className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Risk Metrics</h5>
          <div className="space-y-1">
            <div className="flex justify-between">
              <span className="text-sm text-gray-600 dark:text-gray-300">Max Profit</span>
              <span className="text-sm font-medium text-green-600 dark:text-green-400">
                {analytics.max_profit !== null ? formatCurrency(analytics.max_profit) : '∞'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-gray-600 dark:text-gray-300">Max Risk</span>
              <span className="text-sm font-medium text-red-600 dark:text-red-400">
                {analytics.max_risk !== null ? formatCurrency(analytics.max_risk) : '∞'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-gray-600 dark:text-gray-300">Collateral</span>
              <span className="text-sm font-medium text-gray-900 dark:text-white">
                {analytics.collateral_calculated !== null ? formatCurrency(analytics.collateral_calculated) : '—'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-gray-600 dark:text-gray-300">PoP</span>
              <span className="text-sm font-medium text-gray-900 dark:text-white">
                {analytics.pop !== null ? `${analytics.pop.toFixed(0)}%` : '—'}
              </span>
            </div>
          </div>
        </div>

        {/* Result Section */}
        <div className="space-y-2">
          <h5 className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Result</h5>
          <div className="space-y-1">
            <div className="flex justify-between">
              <span className="text-sm text-gray-600 dark:text-gray-300">Days Held</span>
              <span className="text-sm font-medium text-gray-900 dark:text-white">
                {analytics.days_held !== null ? analytics.days_held : '—'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-gray-600 dark:text-gray-300">DTE</span>
              <span className="text-sm font-medium text-gray-900 dark:text-white">
                {analytics.dte !== null ? analytics.dte : '—'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-gray-600 dark:text-gray-300">R:R Ratio</span>
              <span className="text-sm font-medium text-gray-900 dark:text-white">
                {analytics.risk_reward_ratio !== null ? `1:${analytics.risk_reward_ratio.toFixed(2)}` : '—'}
              </span>
            </div>
            {analytics.pnl_percent !== null && (
              <div className="mt-2">
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-gray-600 dark:text-gray-300">% of Max Profit</span>
                  <span className={getPnlColor(analytics.pnl_percent)}>
                    {analytics.pnl_percent.toFixed(0)}%
                  </span>
                </div>
                <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                  <div
                    className={`h-2 rounded-full ${analytics.pnl_percent >= 0 ? 'bg-green-500' : 'bg-red-500'}`}
                    style={{ width: `${Math.min(Math.abs(analytics.pnl_percent), 100)}%` }}
                  />
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Leg Greeks Toggle */}
      <button
        onClick={loadLegs}
        className="mt-4 flex items-center gap-2 text-sm text-blue-600 dark:text-blue-400 hover:underline"
      >
        {showLegs ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        {loading ? 'Loading...' : showLegs ? 'Hide Leg Greeks' : 'Show Leg Greeks'}
      </button>

      {/* Leg Greeks Table */}
      {showLegs && legs.length > 0 && (
        <div className="mt-4">
          <LegGreeksTable legs={legs} />
        </div>
      )}
    </div>
  );
}
