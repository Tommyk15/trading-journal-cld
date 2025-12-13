'use client';

import { useEffect, useState } from 'react';
import { Header } from '@/components/layout/Header';
import { api } from '@/lib/api/client';
import { formatCurrency, formatPercent } from '@/lib/utils';
import { TrendingUp, TrendingDown, Activity, Target } from 'lucide-react';
import type {
  WinRateMetrics,
  DrawdownMetrics,
  CumulativePnL,
} from '@/types';

interface StatCardProps {
  title: string;
  value: string;
  change?: string;
  trend?: 'up' | 'down' | 'neutral';
  icon: React.ReactNode;
}

function StatCard({ title, value, change, trend, icon }: StatCardProps) {
  const trendColors = {
    up: 'text-green-600',
    down: 'text-red-600',
    neutral: 'text-gray-600',
  };

  return (
    <div className="rounded-lg bg-white p-6 shadow">
      <div className="flex items-center justify-between">
        <div className="flex-1">
          <p className="text-sm font-medium text-gray-600">{title}</p>
          <p className="mt-2 text-3xl font-bold text-gray-900">{value}</p>
          {change && (
            <p className={`mt-2 text-sm ${trendColors[trend || 'neutral']}`}>
              {change}
            </p>
          )}
        </div>
        <div className="rounded-full bg-blue-50 p-3">{icon}</div>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [winRate, setWinRate] = useState<WinRateMetrics | null>(null);
  const [drawdown, setDrawdown] = useState<DrawdownMetrics | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        const [winRateData, drawdownData] = await Promise.all([
          api.analytics.winRate(),
          api.performance.drawdown(),
        ]);
        setWinRate(winRateData as WinRateMetrics);
        setDrawdown(drawdownData as DrawdownMetrics);
      } catch (error) {
        console.error('Error fetching dashboard data:', error);
      } finally {
        setLoading(false);
      }
    }

    fetchData();
  }, []);

  if (loading) {
    return (
      <div>
        <Header title="Dashboard" subtitle="Overview of your trading performance" />
        <div className="p-6">
          <div className="animate-pulse">
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
              {[1, 2, 3, 4].map((i) => (
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
        title="Dashboard"
        subtitle="Overview of your trading performance"
      />

      <div className="p-6">
        {/* Stats Grid */}
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
          <StatCard
            title="Total P&L"
            value={formatCurrency(winRate?.total_pnl || 0)}
            trend={
              winRate && winRate.total_pnl > 0
                ? 'up'
                : winRate && winRate.total_pnl < 0
                ? 'down'
                : 'neutral'
            }
            icon={<TrendingUp className="h-6 w-6 text-blue-600" />}
          />

          <StatCard
            title="Win Rate"
            value={formatPercent((winRate?.win_rate || 0) / 100)}
            change={`${winRate?.winning_trades || 0} / ${winRate?.total_trades || 0} trades`}
            trend="neutral"
            icon={<Target className="h-6 w-6 text-blue-600" />}
          />

          <StatCard
            title="Profit Factor"
            value={(winRate?.profit_factor || 0).toFixed(2)}
            trend={
              winRate && winRate.profit_factor > 1
                ? 'up'
                : winRate && winRate.profit_factor < 1
                ? 'down'
                : 'neutral'
            }
            icon={<Activity className="h-6 w-6 text-blue-600" />}
          />

          <StatCard
            title="Max Drawdown"
            value={formatPercent((drawdown?.max_drawdown_percent || 0) / 100)}
            change={formatCurrency(drawdown?.max_drawdown || 0)}
            trend="down"
            icon={<TrendingDown className="h-6 w-6 text-blue-600" />}
          />
        </div>

        {/* Welcome Message */}
        <div className="mt-8 rounded-lg bg-blue-50 p-6">
          <h2 className="text-lg font-semibold text-gray-900">
            Welcome to Trading Journal
          </h2>
          <p className="mt-2 text-sm text-gray-600">
            Your trading analytics dashboard is ready. Explore the different
            sections using the sidebar to view detailed analytics, positions,
            trades, and performance metrics.
          </p>
        </div>

        {/* Quick Stats */}
        <div className="mt-8 grid gap-6 md:grid-cols-2">
          <div className="rounded-lg bg-white p-6 shadow">
            <h3 className="text-lg font-semibold text-gray-900">
              Trade Statistics
            </h3>
            <div className="mt-4 space-y-3">
              <div className="flex justify-between">
                <span className="text-sm text-gray-600">Total Trades</span>
                <span className="text-sm font-medium text-gray-900">
                  {winRate?.total_trades || 0}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-gray-600">Average Win</span>
                <span className="text-sm font-medium text-green-600">
                  {formatCurrency(winRate?.avg_win || 0)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-gray-600">Average Loss</span>
                <span className="text-sm font-medium text-red-600">
                  {formatCurrency(winRate?.avg_loss || 0)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-gray-600">Largest Win</span>
                <span className="text-sm font-medium text-green-600">
                  {formatCurrency(winRate?.largest_win || 0)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-gray-600">Largest Loss</span>
                <span className="text-sm font-medium text-red-600">
                  {formatCurrency(winRate?.largest_loss || 0)}
                </span>
              </div>
            </div>
          </div>

          <div className="rounded-lg bg-white p-6 shadow">
            <h3 className="text-lg font-semibold text-gray-900">
              Drawdown Analysis
            </h3>
            <div className="mt-4 space-y-3">
              <div className="flex justify-between">
                <span className="text-sm text-gray-600">Current Drawdown</span>
                <span className="text-sm font-medium text-gray-900">
                  {formatPercent((drawdown?.current_drawdown_percent || 0) / 100)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-gray-600">Peak Value</span>
                <span className="text-sm font-medium text-gray-900">
                  {formatCurrency(drawdown?.peak_value || 0)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-gray-600">Current Value</span>
                <span className="text-sm font-medium text-gray-900">
                  {formatCurrency(drawdown?.current_value || 0)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-gray-600">Days in Drawdown</span>
                <span className="text-sm font-medium text-gray-900">
                  {drawdown?.days_in_drawdown || 0}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
