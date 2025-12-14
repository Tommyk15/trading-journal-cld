'use client';

import { useState } from 'react';
import { TrendingUp, TrendingDown, Minus, Info } from 'lucide-react';

type MetricFormat = 'currency' | 'percent' | 'number' | 'ratio';
type TrendType = 'up' | 'down' | 'neutral';

interface MetricCardProps {
  title: string;
  value: number | string | null | undefined;
  format?: MetricFormat;
  trend?: TrendType;
  subtitle?: string;
  size?: 'sm' | 'md' | 'lg';
  tooltip?: string;
}

function formatValue(value: number | string | null | undefined, format: MetricFormat): string {
  if (value === null || value === undefined) return '-';

  const numValue = typeof value === 'string' ? parseFloat(value) : value;

  if (isNaN(numValue)) return String(value);

  switch (format) {
    case 'currency':
      return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
      }).format(numValue);
    case 'percent':
      return `${numValue.toFixed(1)}%`;
    case 'ratio':
      return numValue.toFixed(2);
    case 'number':
    default:
      return numValue.toLocaleString();
  }
}

function getTrendColor(trend: TrendType, format: MetricFormat): string {
  // For drawdown, down is actually bad (more negative is worse)
  if (trend === 'up') return 'text-green-600 dark:text-green-400';
  if (trend === 'down') return 'text-red-600 dark:text-red-400';
  return 'text-gray-500 dark:text-gray-400';
}

function getTrendIcon(trend: TrendType) {
  if (trend === 'up') return <TrendingUp className="h-4 w-4" />;
  if (trend === 'down') return <TrendingDown className="h-4 w-4" />;
  return <Minus className="h-4 w-4" />;
}

export function MetricCard({
  title,
  value,
  format = 'number',
  trend,
  subtitle,
  size = 'md',
  tooltip,
}: MetricCardProps) {
  const [showTooltip, setShowTooltip] = useState(false);
  const formattedValue = formatValue(value, format);

  const sizeClasses = {
    sm: 'p-3',
    md: 'p-4',
    lg: 'p-6',
  };

  const valueSizeClasses = {
    sm: 'text-lg',
    md: 'text-2xl',
    lg: 'text-3xl',
  };

  return (
    <div className={`relative rounded-lg bg-white shadow dark:bg-gray-800 ${sizeClasses[size]}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1">
          <p className="text-sm font-medium text-gray-500 dark:text-gray-400">{title}</p>
          {tooltip && (
            <div className="relative">
              <button
                type="button"
                className="text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 focus:outline-none"
                onMouseEnter={() => setShowTooltip(true)}
                onMouseLeave={() => setShowTooltip(false)}
                onClick={() => setShowTooltip(!showTooltip)}
                aria-label="More info"
              >
                <Info className="h-3.5 w-3.5" />
              </button>
              {showTooltip && (
                <div className="absolute left-0 top-6 z-50 w-64 rounded-lg bg-gray-900 dark:bg-gray-700 p-2 text-xs text-white shadow-lg">
                  {tooltip}
                  <div className="absolute -top-1 left-2 h-2 w-2 rotate-45 bg-gray-900 dark:bg-gray-700" />
                </div>
              )}
            </div>
          )}
        </div>
        {trend && (
          <span className={getTrendColor(trend, format)}>
            {getTrendIcon(trend)}
          </span>
        )}
      </div>
      <p className={`mt-1 font-semibold text-gray-900 dark:text-white ${valueSizeClasses[size]}`}>
        {formattedValue}
      </p>
      {subtitle && (
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{subtitle}</p>
      )}
    </div>
  );
}
