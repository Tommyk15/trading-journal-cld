'use client';

import { useState } from 'react';
import { StreakInfo } from '@/types';
import { Flame, Target, TrendingUp, TrendingDown, Info } from 'lucide-react';

interface RiskMetricsPanelProps {
  expectancy: number;
  streakInfo: StreakInfo;
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

function MetricItem({
  label,
  value,
  icon: Icon,
  color,
  bgColor,
  tooltip,
}: {
  label: string;
  value: string;
  icon: React.ComponentType<{ className?: string }>;
  color: string;
  bgColor: string;
  tooltip: string;
}) {
  const [showTooltip, setShowTooltip] = useState(false);

  return (
    <div className={`relative rounded p-2 ${bgColor}`}>
      <div className="flex items-center gap-1">
        <Icon className={`h-3 w-3 ${color}`} />
        <span className="text-[10px] text-gray-500 dark:text-gray-400">{label}</span>
        <div className="relative ml-auto">
          <button
            type="button"
            className="text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 focus:outline-none"
            onMouseEnter={() => setShowTooltip(true)}
            onMouseLeave={() => setShowTooltip(false)}
            onClick={() => setShowTooltip(!showTooltip)}
            aria-label="More info"
          >
            <Info className="h-2.5 w-2.5" />
          </button>
          {showTooltip && (
            <div className="absolute right-0 top-4 z-50 w-48 rounded-lg bg-gray-900 dark:bg-gray-700 p-1.5 text-[10px] text-white shadow-lg">
              {tooltip}
              <div className="absolute -top-1 right-2 h-2 w-2 rotate-45 bg-gray-900 dark:bg-gray-700" />
            </div>
          )}
        </div>
      </div>
      <p className={`text-sm font-semibold ${color}`}>
        {value}
      </p>
    </div>
  );
}

export function RiskMetricsPanel({ expectancy, streakInfo }: RiskMetricsPanelProps) {
  const metrics = [
    {
      label: 'Expectancy',
      value: formatCurrency(expectancy),
      icon: Target,
      color: expectancy >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400',
      bgColor: expectancy >= 0 ? 'bg-green-50 dark:bg-green-900/20' : 'bg-red-50 dark:bg-red-900/20',
      tooltip: 'Expected profit per trade. Positive = profitable strategy.',
    },
    {
      label: 'Max Win',
      value: streakInfo.max_consecutive_wins.toString(),
      icon: TrendingUp,
      color: 'text-green-600 dark:text-green-400',
      bgColor: 'bg-green-50 dark:bg-green-900/20',
      tooltip: 'Longest consecutive winning trades.',
    },
    {
      label: 'Max Loss',
      value: streakInfo.max_consecutive_losses.toString(),
      icon: TrendingDown,
      color: 'text-red-600 dark:text-red-400',
      bgColor: 'bg-red-50 dark:bg-red-900/20',
      tooltip: 'Longest consecutive losing trades.',
    },
    {
      label: 'Current',
      value: `${streakInfo.current_streak}${streakInfo.current_streak_type === 'win' ? 'W' : streakInfo.current_streak_type === 'loss' ? 'L' : ''}`,
      icon: Flame,
      color: streakInfo.current_streak_type === 'win'
        ? 'text-green-600 dark:text-green-400'
        : streakInfo.current_streak_type === 'loss'
        ? 'text-red-600 dark:text-red-400'
        : 'text-gray-500 dark:text-gray-400',
      bgColor: streakInfo.current_streak_type === 'win'
        ? 'bg-green-50 dark:bg-green-900/20'
        : streakInfo.current_streak_type === 'loss'
        ? 'bg-red-50 dark:bg-red-900/20'
        : 'bg-gray-50 dark:bg-gray-700/50',
      tooltip: 'Current win/loss streak.',
    },
  ];

  return (
    <div className="rounded-lg bg-white p-3 shadow dark:bg-gray-800">
      <h3 className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">Streak & Expectancy</h3>

      <div className="grid grid-cols-4 gap-2">
        {metrics.map((metric) => (
          <MetricItem
            key={metric.label}
            label={metric.label}
            value={metric.value}
            icon={metric.icon}
            color={metric.color}
            bgColor={metric.bgColor}
            tooltip={metric.tooltip}
          />
        ))}
      </div>
    </div>
  );
}
