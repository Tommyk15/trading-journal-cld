'use client';

import { useEffect, useState } from 'react';
import { Header } from '@/components/layout/Header';
import { StrategyBreakdownChart } from '@/components/charts/StrategyBreakdownChart';
import { api } from '@/lib/api/client';
import { formatCurrency, formatPercent } from '@/lib/utils';
import type { StrategyBreakdown, UnderlyingBreakdown, WinRateMetrics } from '@/types';

export default function AnalyticsPage() {
  const [winRate, setWinRate] = useState<WinRateMetrics | null>(null);
  const [strategies, setStrategies] = useState<StrategyBreakdown[]>([]);
  const [underlyings, setUnderlyings] = useState<UnderlyingBreakdown[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        const [winRateData, strategyData, underlyingData] = await Promise.all([
          api.analytics.winRate(),
          api.analytics.strategyBreakdown(),
          api.analytics.underlyingBreakdown(),
        ]);
        setWinRate(winRateData as WinRateMetrics);
        // API returns { strategies: [...] }, extract the array
        const strategyArray = (strategyData as any)?.strategies || strategyData || [];
        setStrategies(Array.isArray(strategyArray) ? strategyArray : []);
        // API returns { underlyings: [...] }, extract the array
        const underlyingArray = (underlyingData as any)?.underlyings || underlyingData || [];
        setUnderlyings(Array.isArray(underlyingArray) ? underlyingArray : []);
      } catch (error) {
        console.error('Error fetching analytics data:', error);
      } finally {
        setLoading(false);
      }
    }

    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-100 dark:bg-gray-900 transition-colors">
        <Header
          title="Analytics"
          subtitle="Detailed performance analytics and breakdowns"
        />
        <div className="p-6">
          <div className="animate-pulse space-y-6">
            <div className="h-96 rounded-lg bg-gray-200 dark:bg-gray-700" />
            <div className="h-64 rounded-lg bg-gray-200 dark:bg-gray-700" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900 transition-colors">
      <Header
        title="Analytics"
        subtitle="Detailed performance analytics and breakdowns"
      />

      <div className="p-6 space-y-6">
        {/* Win Rate Overview */}
        <div className="rounded-lg bg-white dark:bg-gray-800 p-6 shadow transition-colors">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Win Rate Metrics
          </h2>
          <div className="grid gap-6 md:grid-cols-5">
            <div>
              <p className="text-sm text-gray-600 dark:text-gray-400">Win Rate</p>
              <p className="mt-1 text-2xl font-bold text-gray-900 dark:text-white">
                {formatPercent((winRate?.win_rate || 0) / 100)}
              </p>
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                {winRate?.winning_trades} / {winRate?.total_trades} trades
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-600 dark:text-gray-400">Profit Factor</p>
              <p className="mt-1 text-2xl font-bold text-gray-900 dark:text-white">
                {winRate?.profit_factor?.toFixed(2) || 'N/A'}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-600 dark:text-gray-400">Avg Win</p>
              <p className="mt-1 text-2xl font-bold text-green-600 dark:text-green-400">
                {formatCurrency(winRate?.avg_win || 0)}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-600 dark:text-gray-400">Avg Loss</p>
              <p className="mt-1 text-2xl font-bold text-red-600 dark:text-red-400">
                {formatCurrency(winRate?.avg_loss || 0)}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-600 dark:text-gray-400">Total P&L</p>
              <p className="mt-1 text-2xl font-bold text-gray-900 dark:text-white">
                {formatCurrency(winRate?.total_pnl || 0)}
              </p>
            </div>
          </div>
        </div>

        {/* Strategy Breakdown Chart */}
        <div className="rounded-lg bg-white dark:bg-gray-800 p-6 shadow transition-colors">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Strategy Performance
          </h2>
          {strategies.length > 0 ? (
            <StrategyBreakdownChart data={strategies} />
          ) : (
            <div className="flex h-96 items-center justify-center text-gray-500 dark:text-gray-400">
              No strategy data available
            </div>
          )}
        </div>

        {/* Strategy Table */}
        <div className="rounded-lg bg-white dark:bg-gray-800 shadow overflow-hidden transition-colors">
          <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              Strategy Details
            </h2>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead className="bg-gray-50 dark:bg-gray-700">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                    Strategy
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                    Trades
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                    Win Rate
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                    Total P&L
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                    Avg P&L
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                    Profit Factor
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                {strategies.map((strategy: any, idx) => (
                  <tr key={idx} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-white">
                      {(strategy.strategy_type || strategy.strategy || '').replace(/_/g, ' ')}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white text-right">
                      {strategy.total_trades || strategy.trade_count || 0}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white text-right">
                      {formatPercent((strategy.win_rate || 0) / 100)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white text-right">
                      {formatCurrency(parseFloat(strategy.total_pnl || strategy.net_pnl || 0))}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white text-right">
                      {formatCurrency(parseFloat(strategy.average_pnl || strategy.avg_pnl_per_trade || 0))}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white text-right">
                      {(strategy.winning_trades && strategy.losing_trades)
                        ? (strategy.winning_trades / Math.max(strategy.losing_trades, 1)).toFixed(2)
                        : (strategy.profit_factor || 0).toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Underlying Symbol Breakdown */}
        <div className="rounded-lg bg-white dark:bg-gray-800 shadow overflow-hidden transition-colors">
          <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              Performance by Underlying Symbol
            </h2>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead className="bg-gray-50 dark:bg-gray-700">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                    Symbol
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                    Trades
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                    Win Rate
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                    Total P&L
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                    Avg P&L
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                {underlyings.map((underlying: any, idx) => (
                  <tr key={idx} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-white">
                      {underlying.underlying || underlying.underlying_symbol}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white text-right">
                      {underlying.total_trades || underlying.trade_count || 0}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white text-right">
                      {formatPercent((underlying.win_rate || 0) / 100)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white text-right">
                      {formatCurrency(parseFloat(underlying.total_pnl || underlying.net_pnl || 0))}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white text-right">
                      {formatCurrency(parseFloat(underlying.average_pnl || underlying.avg_pnl_per_trade || 0))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
