'use client';

import { useState, useMemo } from 'react';
import {
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { MetricsTimePoint } from '@/types';

interface MultiMetricChartProps {
  data: MetricsTimePoint[];
  height?: number;
}

type MetricKey = 'cumulative_pnl' | 'win_rate' | 'drawdown_percent';

interface MetricConfig {
  key: MetricKey;
  label: string;
  color: string;
  yAxisId: string;
}

const metrics: MetricConfig[] = [
  {
    key: 'cumulative_pnl',
    label: 'P&L',
    color: '#2563eb',
    yAxisId: 'pnl',
  },
  {
    key: 'win_rate',
    label: 'Win Rate',
    color: '#16a34a',
    yAxisId: 'percent',
  },
  {
    key: 'drawdown_percent',
    label: 'Drawdown',
    color: '#dc2626',
    yAxisId: 'percent',
  },
];

export function MultiMetricChart({ data, height = 400 }: MultiMetricChartProps) {
  const [activeMetrics, setActiveMetrics] = useState<Set<MetricKey>>(
    new Set(['cumulative_pnl', 'win_rate'])
  );

  const toggleMetric = (key: MetricKey) => {
    setActiveMetrics((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  // Create a date-to-index lookup and process data
  const { processedData, dateRange, mondayIndices, monthBoundaries } = useMemo(() => {
    if (!data || data.length === 0) {
      return { processedData: [], dateRange: { min: 0, max: 0 }, mondayIndices: [], monthBoundaries: [] };
    }

    const firstDate = new Date(data[0].date);
    const lastDate = new Date(data[data.length - 1].date);

    // Create a map of date string to day index from start
    const startTime = firstDate.getTime();
    const msPerDay = 24 * 60 * 60 * 1000;

    // Process data with day indices
    const processed = data.map((point) => {
      const pointDate = new Date(point.date);
      const dayIndex = Math.round((pointDate.getTime() - startTime) / msPerDay);
      return {
        ...point,
        dayIndex,
      };
    });

    const totalDays = Math.round((lastDate.getTime() - startTime) / msPerDay);

    // Find all Mondays
    const mondays: number[] = [];
    const current = new Date(firstDate);
    // Move to first Monday
    while (current.getDay() !== 1) {
      current.setDate(current.getDate() + 1);
    }
    while (current <= lastDate) {
      const idx = Math.round((current.getTime() - startTime) / msPerDay);
      mondays.push(idx);
      current.setDate(current.getDate() + 7);
    }

    // Find month boundaries - include the first month
    const boundaries: { dayIndex: number; label: string }[] = [];

    // Add the first month at the start
    boundaries.push({
      dayIndex: 0,
      label: firstDate.toLocaleDateString('en-US', { month: 'short' }),
    });

    // Add subsequent month boundaries
    const checkDate = new Date(firstDate);
    checkDate.setDate(1);
    checkDate.setMonth(checkDate.getMonth() + 1); // Start of next month

    while (checkDate <= lastDate) {
      const idx = Math.round((checkDate.getTime() - startTime) / msPerDay);
      boundaries.push({
        dayIndex: idx,
        label: checkDate.toLocaleDateString('en-US', { month: 'short' }),
      });
      checkDate.setMonth(checkDate.getMonth() + 1);
    }

    return {
      processedData: processed,
      dateRange: { min: 0, max: totalDays },
      mondayIndices: mondays,
      monthBoundaries: boundaries,
    };
  }, [data]);

  // Format date for X-axis tick
  const formatTick = (dayIndex: number) => {
    if (!data || data.length === 0) return '';
    const firstDate = new Date(data[0].date);
    const tickDate = new Date(firstDate.getTime() + dayIndex * 24 * 60 * 60 * 1000);
    return tickDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  // Format number with commas
  const formatNumber = (value: number): string => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);
  };

  // Custom tooltip
  const CustomTooltip = ({ active, payload }: {
    active?: boolean;
    payload?: Array<{ dataKey: string; value: number; color: string; payload: { date: string } }>;
  }) => {
    if (!active || !payload?.length) return null;

    const dateStr = payload[0]?.payload?.date;
    const displayDate = dateStr
      ? new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
      : '';

    return (
      <div className="rounded-lg bg-white p-3 shadow-lg border border-gray-200 dark:bg-gray-800 dark:border-gray-700">
        <p className="text-sm font-medium text-gray-900 dark:text-white mb-2">
          {displayDate}
        </p>
        {payload.map((entry) => {
          const metric = metrics.find((m) => m.key === entry.dataKey);
          if (!metric) return null;

          let formattedValue: string;
          if (metric.key === 'cumulative_pnl') {
            formattedValue = formatNumber(entry.value);
          } else {
            formattedValue = `${entry.value.toFixed(1)}%`;
          }

          return (
            <p key={entry.dataKey} className="text-sm" style={{ color: entry.color }}>
              {metric.label}: {formattedValue}
            </p>
          );
        })}
      </div>
    );
  };

  if (!data || data.length === 0) {
    return (
      <div className="rounded-lg bg-white p-4 shadow dark:bg-gray-800">
        <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">Performance Over Time</h3>
        <div className="flex h-64 items-center justify-center">
          <p className="text-gray-400 dark:text-gray-500">No data available</p>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg bg-white p-2 shadow dark:bg-gray-800">
      <div className="flex items-center justify-between mb-1 px-1">
        <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">Performance Over Time</h3>

        {/* Metric toggles */}
        <div className="flex gap-3">
          {metrics.map((metric) => (
            <label
              key={metric.key}
              className="flex items-center gap-1.5 cursor-pointer"
            >
              <input
                type="checkbox"
                checked={activeMetrics.has(metric.key)}
                onChange={() => toggleMetric(metric.key)}
                className="rounded border-gray-300 dark:border-gray-600 h-3.5 w-3.5"
                style={{ accentColor: metric.color }}
              />
              <span
                className="text-xs"
                style={{ color: activeMetrics.has(metric.key) ? metric.color : '#9ca3af' }}
              >
                {metric.label}
              </span>
            </label>
          ))}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={processedData} margin={{ top: 15, right: 25, left: 5, bottom: 30 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.2} />

          <XAxis
            dataKey="dayIndex"
            type="number"
            domain={[dateRange.min, dateRange.max]}
            ticks={mondayIndices}
            tickFormatter={formatTick}
            stroke="#9ca3af"
            fontSize={9}
            angle={-45}
            textAnchor="end"
            height={35}
            interval={0}
            axisLine={{ stroke: '#4b5563' }}
            tickLine={{ stroke: '#4b5563' }}
          />

          {/* P&L axis (left) - always render for reference lines */}
          <YAxis
            yAxisId="pnl"
            orientation="left"
            stroke={activeMetrics.has('cumulative_pnl') ? '#2563eb' : 'transparent'}
            fontSize={11}
            tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
            width={55}
            tick={activeMetrics.has('cumulative_pnl') ? undefined : false}
            axisLine={activeMetrics.has('cumulative_pnl')}
          />

          {/* Percent axis (right) */}
          {(activeMetrics.has('win_rate') || activeMetrics.has('drawdown_percent')) && (
            <YAxis
              yAxisId="percent"
              orientation="right"
              stroke="#9ca3af"
              fontSize={11}
              tickFormatter={(v) => `${v}%`}
              domain={[0, 100]}
              width={40}
            />
          )}

          <Tooltip content={<CustomTooltip />} />

          {/* Monthly vertical separator lines */}
          {monthBoundaries.map((boundary) => (
            <ReferenceLine
              key={boundary.dayIndex}
              x={boundary.dayIndex}
              yAxisId="pnl"
              stroke="#6b7280"
              strokeWidth={1}
              strokeDasharray="4 4"
              label={{
                value: boundary.label,
                position: 'top',
                fill: '#9ca3af',
                fontSize: 10,
                fontWeight: 600,
              }}
            />
          ))}

          {metrics.map((metric) =>
            activeMetrics.has(metric.key) ? (
              <Line
                key={metric.key}
                type="monotone"
                dataKey={metric.key}
                name={metric.label}
                stroke={metric.color}
                yAxisId={metric.yAxisId}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
                connectNulls
              />
            ) : null
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
