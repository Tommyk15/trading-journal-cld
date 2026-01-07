'use client';

import { useEffect, useState, useMemo } from 'react';
import { api } from '@/lib/api/client';
import {
  TimePeriodSelector,
  MetricCard,
  DualMetricCard,
  GreeksPanel,
  BestWorstCard,
  RiskMetricsPanel,
  MultiMetricChart,
} from '@/components/dashboard';
import type {
  TimePeriod,
  DashboardSummary,
  MetricsTimeSeriesResponse,
  PortfolioGreeksSummary,
} from '@/types';

export default function Dashboard() {
  const [period, setPeriod] = useState<TimePeriod>('all');
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [timeSeries, setTimeSeries] = useState<MetricsTimeSeriesResponse | null>(null);
  const [portfolioGreeks, setPortfolioGreeks] = useState<PortfolioGreeksSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Main dashboard data fetch
  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        setError(null);

        const [summaryData, timeSeriesData] = await Promise.all([
          api.dashboard.summary({ period }),
          api.dashboard.metricsTimeSeries({ period }),
        ]);

        setSummary(summaryData as DashboardSummary);
        setTimeSeries(timeSeriesData as MetricsTimeSeriesResponse);
      } catch (err) {
        console.error('Error fetching dashboard data:', err);
        setError(err instanceof Error ? err.message : 'Failed to load dashboard');
      } finally {
        setLoading(false);
      }
    }

    fetchData();
  }, [period]);

  // Fetch portfolio greeks separately (non-blocking)
  useEffect(() => {
    async function fetchGreeks() {
      try {
        const marketData = await api.marketData.getPositionsMarketData();
        if (marketData) {
          const optionPositionCount = marketData.positions?.filter(p => p.legs?.some(l => l.security_type === 'OPT')).length ?? 0;
          if (marketData.total_delta || marketData.total_gamma || marketData.total_theta || marketData.total_vega || optionPositionCount > 0) {
            setPortfolioGreeks({
              total_delta: marketData.total_delta ?? 0,
              total_gamma: marketData.total_gamma ?? 0,
              total_theta: marketData.total_theta ?? 0,
              total_vega: marketData.total_vega ?? 0,
              position_count: optionPositionCount,
              last_updated: marketData.timestamp,
            });
          }
        }
      } catch (greeksErr) {
        console.log('Could not fetch portfolio greeks:', greeksErr);
      }
    }

    fetchGreeks();
  }, []); // Only fetch once on mount, not on period change

  // Extract sparkline data and period changes from time series
  const sparklineData = useMemo(() => {
    if (!timeSeries?.data_points || timeSeries.data_points.length === 0) {
      return {
        pnl: [],
        tradeCount: [],
        winRate: [],
        profitFactor: [],
        drawdown: [],
        avgWinner: [],
        avgLoser: [],
        dailyPnl: [],
        pnlChange: undefined,
        tradeCountChange: undefined,
        winRateChange: undefined,
        profitFactorChange: undefined,
        drawdownChange: undefined,
        avgWinnerChange: undefined,
        avgLoserChange: undefined,
        dailyPnlChange: undefined,
      };
    }

    const points = timeSeries.data_points;
    const first = points[0];
    const last = points[points.length - 1];

    // Filter out null values for avg winner/loser
    const avgWinnerPoints = points.filter((p) => p.avg_winner !== null);
    const avgLoserPoints = points.filter((p) => p.avg_loser !== null);

    // Calculate daily P&L from cumulative (difference between consecutive days)
    const dailyPnl = points.map((p, i) => {
      if (i === 0) return p.cumulative_pnl;
      return p.cumulative_pnl - points[i - 1].cumulative_pnl;
    });

    return {
      pnl: points.map((p) => p.cumulative_pnl),
      tradeCount: points.map((p) => p.trade_count),
      winRate: points.map((p) => p.win_rate),
      profitFactor: points.map((p) => p.profit_factor ?? 0),
      drawdown: points.map((p) => p.drawdown_percent),
      avgWinner: avgWinnerPoints.map((p) => p.avg_winner as number),
      avgLoser: avgLoserPoints.map((p) => p.avg_loser as number),
      dailyPnl,
      pnlChange: last.cumulative_pnl - first.cumulative_pnl,
      tradeCountChange: last.trade_count - first.trade_count,
      winRateChange: last.win_rate - first.win_rate,
      profitFactorChange:
        last.profit_factor !== null && first.profit_factor !== null
          ? last.profit_factor - first.profit_factor
          : undefined,
      drawdownChange: last.drawdown_percent - first.drawdown_percent,
      avgWinnerChange:
        avgWinnerPoints.length >= 2
          ? (avgWinnerPoints[avgWinnerPoints.length - 1].avg_winner as number) -
            (avgWinnerPoints[0].avg_winner as number)
          : undefined,
      avgLoserChange:
        avgLoserPoints.length >= 2
          ? (avgLoserPoints[avgLoserPoints.length - 1].avg_loser as number) -
            (avgLoserPoints[0].avg_loser as number)
          : undefined,
      dailyPnlChange:
        dailyPnl.length >= 2
          ? dailyPnl[dailyPnl.length - 1] - dailyPnl[0]
          : undefined,
    };
  }, [timeSeries]);

  // Calculate trades per week
  const tradesPerWeek = useMemo(() => {
    if (!timeSeries?.data_points || timeSeries.data_points.length === 0 || !summary?.total_trades) {
      return null;
    }

    // Calculate number of weeks in the period
    const startDate = timeSeries.start_date ? new Date(timeSeries.start_date) : null;
    const endDate = timeSeries.end_date ? new Date(timeSeries.end_date) : null;

    if (!startDate || !endDate) return null;

    const msPerWeek = 7 * 24 * 60 * 60 * 1000;
    const weeks = Math.max(1, (endDate.getTime() - startDate.getTime()) / msPerWeek);

    return (summary.total_trades / weeks).toFixed(1);
  }, [timeSeries, summary]);

  // Loading skeleton
  if (loading) {
    return (
      <div className="min-h-screen bg-gray-100 dark:bg-gray-900 transition-colors">
        <div className="p-6">
          <div className="flex justify-end mb-6">
            <div className="h-10 w-64 animate-pulse rounded-lg bg-gray-200 dark:bg-gray-700" />
          </div>
          <div className="animate-pulse space-y-6">
            <div className="grid gap-4 md:grid-cols-3 lg:grid-cols-6">
              {[1, 2, 3, 4, 5, 6].map((i) => (
                <div key={i} className="h-24 rounded-lg bg-gray-200 dark:bg-gray-700" />
              ))}
            </div>
            <div className="h-96 rounded-lg bg-gray-200 dark:bg-gray-700" />
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="h-24 rounded-lg bg-gray-200 dark:bg-gray-700" />
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="min-h-screen bg-gray-100 dark:bg-gray-900 transition-colors p-6">
        <div className="rounded-lg bg-red-50 dark:bg-red-900/30 p-6 text-center">
          <p className="text-red-600 dark:text-red-400">{error}</p>
          <button
            onClick={() => window.location.reload()}
            className="mt-4 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900 transition-colors">
      <div className="p-4 space-y-3">
        {/* Time Period Selector */}
        <div className="flex justify-end">
          <TimePeriodSelector selected={period} onChange={setPeriod} />
        </div>

        {/* Row 1: Primary Metrics - 6 columns */}
        <div className="grid gap-2 grid-cols-3 lg:grid-cols-6">
          <MetricCard
            title="Total P&L"
            value={summary?.total_pnl ?? 0}
            format="currency"
            size="sm"
            sparklineData={sparklineData.pnl}
            periodChange={sparklineData.pnlChange}
            showScale
            tooltip="Net profit or loss across all closed trades for the selected period."
          />
          <MetricCard
            title="Total Trades"
            value={summary?.total_trades ?? 0}
            format="number"
            size="sm"
            sparklineData={sparklineData.tradeCount}
            periodChange={sparklineData.tradeCountChange}
            showScale
            subtitle={tradesPerWeek ? `${tradesPerWeek}/week` : undefined}
            tooltip="Total number of closed trades in the selected period."
          />
          <MetricCard
            title="Win Rate"
            value={summary?.win_rate ?? 0}
            format="percent"
            size="sm"
            sparklineData={sparklineData.winRate}
            periodChange={sparklineData.winRateChange}
            showScale
            tooltip="Percentage of trades that were profitable."
          />
          <MetricCard
            title="Avg Winner"
            value={summary?.avg_winner ?? 0}
            format="currency"
            size="sm"
            sparklineData={sparklineData.avgWinner}
            periodChange={sparklineData.avgWinnerChange}
            showScale
            tooltip="Average profit on winning trades."
          />
          <MetricCard
            title="Avg Loser"
            value={summary?.avg_loser ?? 0}
            format="currency"
            size="sm"
            sparklineData={sparklineData.avgLoser}
            periodChange={sparklineData.avgLoserChange}
            showScale
            invertColors
            tooltip="Average loss on losing trades."
          />
          <MetricCard
            title="Profit Factor"
            value={summary?.profit_factor}
            format="ratio"
            size="sm"
            sparklineData={sparklineData.profitFactor}
            periodChange={sparklineData.profitFactorChange}
            showScale
            tooltip="Gross profits / gross losses. Above 1.0 = profitable."
          />
        </div>

        {/* Row 2: Risk Metrics + Best/Worst + Greeks - 6 columns */}
        <div className="grid gap-2 grid-cols-3 lg:grid-cols-6">
          <MetricCard
            title="Max Drawdown"
            value={summary?.max_drawdown_percent ?? 0}
            format="percent"
            size="sm"
            sparklineData={sparklineData.drawdown}
            periodChange={sparklineData.drawdownChange}
            showScale
            invertColors
            tooltip="Largest peak-to-trough decline. Lower is better."
          />
          <MetricCard
            title="Avg Profit/Day"
            value={summary?.avg_profit_per_day ?? 0}
            format="currency"
            size="sm"
            sparklineData={sparklineData.dailyPnl}
            periodChange={sparklineData.dailyPnlChange}
            showScale
            sparklineColorByValue
            subtitle={`${summary?.trading_days ?? 0} days`}
            tooltip="Average daily profit across all trading days."
          />
          <DualMetricCard
            title="Risk-Adjusted Returns"
            size="sm"
            metrics={[
              {
                label: 'Sharpe',
                value: summary?.sharpe_ratio,
                tooltip: 'Risk-adjusted return. Above 1 good, above 2 excellent.',
              },
              {
                label: 'Sortino',
                value: summary?.sortino_ratio,
                tooltip: 'Like Sharpe but only penalizes downside volatility.',
              },
            ]}
          />
          <BestWorstCard
            title="Strategy Performance"
            best={summary?.best_strategy ?? null}
            worst={summary?.worst_strategy ?? null}
            type="strategy"
          />
          <BestWorstCard
            title="Ticker Performance"
            best={summary?.best_ticker ?? null}
            worst={summary?.worst_ticker ?? null}
            type="ticker"
          />
          <GreeksPanel greeks={portfolioGreeks ?? summary?.portfolio_greeks ?? null} />
        </div>

        {/* Row 4: Risk Metrics Panel */}
        <RiskMetricsPanel
          expectancy={summary?.expectancy ?? 0}
          streakInfo={summary?.streak_info ?? {
            max_consecutive_wins: 0,
            max_consecutive_losses: 0,
            current_streak: 0,
            current_streak_type: 'none',
          }}
        />

        {/* Row 5: Performance Chart (at bottom) */}
        <MultiMetricChart data={timeSeries?.data_points ?? []} height={350} />
      </div>
    </div>
  );
}
