'use client';

import { useState } from 'react';
import { Info } from 'lucide-react';

interface MetricValue {
  label: string;
  value: number | string | null | undefined;
  tooltip?: string;
}

interface DualMetricCardProps {
  title: string;
  metrics: [MetricValue, MetricValue];
  size?: 'sm' | 'md' | 'lg';
}

function formatRatio(value: number | string | null | undefined): string {
  if (value === null || value === undefined) return '-';
  const numValue = typeof value === 'string' ? parseFloat(value) : value;
  if (isNaN(numValue)) return '-';
  return numValue.toFixed(2);
}

function getValueColor(value: number | string | null | undefined): string {
  if (value === null || value === undefined) return 'text-gray-900 dark:text-white';
  const numValue = typeof value === 'string' ? parseFloat(value) : value;
  if (isNaN(numValue)) return 'text-gray-900 dark:text-white';
  if (numValue > 0) return 'text-green-600 dark:text-green-400';
  if (numValue < 0) return 'text-red-600 dark:text-red-400';
  return 'text-gray-900 dark:text-white';
}

function MetricItem({ metric }: { metric: MetricValue }) {
  const [showTooltip, setShowTooltip] = useState(false);

  return (
    <div className="text-center">
      <div className="flex items-center justify-center gap-1">
        <span className="text-[10px] text-gray-500 dark:text-gray-400">{metric.label}</span>
        {metric.tooltip && (
          <div className="relative">
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
              <div className="absolute left-1/2 -translate-x-1/2 top-4 z-50 w-48 rounded-lg bg-gray-900 dark:bg-gray-700 p-2 text-xs text-white shadow-lg text-left">
                {metric.tooltip}
                <div className="absolute -top-1 left-1/2 -translate-x-1/2 h-2 w-2 rotate-45 bg-gray-900 dark:bg-gray-700" />
              </div>
            )}
          </div>
        )}
      </div>
      <p className={`text-lg font-semibold ${getValueColor(metric.value)}`}>
        {formatRatio(metric.value)}
      </p>
    </div>
  );
}

export function DualMetricCard({ title, metrics, size = 'md' }: DualMetricCardProps) {
  const sizeClasses = {
    sm: 'p-2',
    md: 'p-3',
    lg: 'p-4',
  };

  return (
    <div className={`relative rounded-lg bg-white shadow dark:bg-gray-800 ${sizeClasses[size]}`}>
      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 text-center">{title}</p>
      <div className="mt-1 grid grid-cols-2 gap-2">
        {metrics.map((metric, idx) => (
          <MetricItem key={idx} metric={metric} />
        ))}
      </div>
    </div>
  );
}
