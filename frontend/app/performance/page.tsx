'use client';

import { useEffect, useState } from 'react';
import { Header } from '@/components/layout/Header';
import { EquityCurveChart } from '@/components/charts/EquityCurveChart';
import { api } from '@/lib/api/client';
import { formatCurrency, formatPercent } from '@/lib/utils';
import type { CumulativePnL, SharpeRatioMetrics, DrawdownMetrics } from '@/types';

export default function PerformancePage() {
  const [equityData, setEquityData] = useState<CumulativePnL[]>([]);
  const [sharpe, setSharpe] = useState<SharpeRatioMetrics | null>(null);
  const [drawdown, setDrawdown] = useState<DrawdownMetrics | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        const [equityCurve, sharpeData, drawdownData] = await Promise.all([
          api.performance.cumulativePnl(),
          api.performance.sharpeRatio(),
          api.performance.drawdown(),
        ]);
        setEquityData(equityCurve as CumulativePnL[]);
        setSharpe(sharpeData as SharpeRatioMetrics);
        setDrawdown(drawdownData as DrawdownMetrics);
      } catch (error) {
        console.error('Error fetching performance data:', error);
      } finally {
        setLoading(false);
      }
    }

    fetchData();
  }, []);

  if (loading) {
    return (
      <div>
        <Header
          title="Performance"
          subtitle="Track your trading performance over time"
        />
        <div className="p-6">
          <div className="animate-pulse space-y-6">
            <div className="h-96 rounded-lg bg-gray-200" />
            <div className="grid gap-6 md:grid-cols-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-32 rounded-lg bg-gray-200" />
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div>
      <Header
        title="Performance"
        subtitle="Track your trading performance over time"
      />

      <div className="p-6 space-y-6">
        {/* Equity Curve */}
        <div className="rounded-lg bg-white p-6 shadow">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            Equity Curve
          </h2>
          {equityData.length > 0 ? (
            <EquityCurveChart data={equityData} />
          ) : (
            <div className="flex h-96 items-center justify-center text-gray-500">
              No performance data available
            </div>
          )}
        </div>

        {/* Performance Metrics */}
        <div className="grid gap-6 md:grid-cols-3">
          {/* Sharpe Ratio */}
          <div className="rounded-lg bg-white p-6 shadow">
            <h3 className="text-sm font-medium text-gray-600">Sharpe Ratio</h3>
            <p className="mt-2 text-3xl font-bold text-gray-900">
              {sharpe?.sharpe_ratio.toFixed(2) || '0.00'}
            </p>
            <div className="mt-4 space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">Annual Return</span>
                <span className="font-medium text-gray-900">
                  {formatPercent((sharpe?.annual_return || 0) / 100)}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">Annual Volatility</span>
                <span className="font-medium text-gray-900">
                  {formatPercent((sharpe?.annual_volatility || 0) / 100)}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">Risk-Free Rate</span>
                <span className="font-medium text-gray-900">
                  {formatPercent((sharpe?.risk_free_rate || 0) / 100)}
                </span>
              </div>
            </div>
          </div>

          {/* Max Drawdown */}
          <div className="rounded-lg bg-white p-6 shadow">
            <h3 className="text-sm font-medium text-gray-600">Max Drawdown</h3>
            <p className="mt-2 text-3xl font-bold text-red-600">
              {formatPercent((drawdown?.max_drawdown_percent || 0) / 100)}
            </p>
            <div className="mt-4 space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">Amount</span>
                <span className="font-medium text-gray-900">
                  {formatCurrency(drawdown?.max_drawdown || 0)}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">Peak Value</span>
                <span className="font-medium text-gray-900">
                  {formatCurrency(drawdown?.peak_value || 0)}
                </span>
              </div>
            </div>
          </div>

          {/* Current Drawdown */}
          <div className="rounded-lg bg-white p-6 shadow">
            <h3 className="text-sm font-medium text-gray-600">
              Current Drawdown
            </h3>
            <p className="mt-2 text-3xl font-bold text-orange-600">
              {formatPercent((drawdown?.current_drawdown_percent || 0) / 100)}
            </p>
            <div className="mt-4 space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">Amount</span>
                <span className="font-medium text-gray-900">
                  {formatCurrency(drawdown?.current_drawdown || 0)}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">Days in Drawdown</span>
                <span className="font-medium text-gray-900">
                  {drawdown?.days_in_drawdown || 0}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">Current Value</span>
                <span className="font-medium text-gray-900">
                  {formatCurrency(drawdown?.current_value || 0)}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Summary Statistics */}
        <div className="rounded-lg bg-white p-6 shadow">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            Performance Summary
          </h2>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <div>
              <p className="text-sm text-gray-600">Total Trading Days</p>
              <p className="mt-1 text-xl font-semibold text-gray-900">
                {sharpe?.total_days || 0}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-600">Total Trades</p>
              <p className="mt-1 text-xl font-semibold text-gray-900">
                {equityData[equityData.length - 1]?.trade_count || 0}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-600">Final P&L</p>
              <p className="mt-1 text-xl font-semibold text-gray-900">
                {formatCurrency(
                  equityData[equityData.length - 1]?.cumulative_pnl || 0
                )}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-600">Starting P&L</p>
              <p className="mt-1 text-xl font-semibold text-gray-900">
                {formatCurrency(equityData[0]?.cumulative_pnl || 0)}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
