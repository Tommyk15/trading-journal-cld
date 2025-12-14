'use client';

import { useState } from 'react';
import { PortfolioGreeksSummary } from '@/types';
import { Info } from 'lucide-react';

interface GreeksPanelProps {
  greeks: PortfolioGreeksSummary | null;
}

function formatGreek(value: number, decimals: number = 0): string {
  if (value === null || value === undefined) return '-';
  return value >= 0 ? `+${value.toFixed(decimals)}` : value.toFixed(decimals);
}

function getGreekColor(value: number): string {
  if (value > 0) return 'text-green-600 dark:text-green-400';
  if (value < 0) return 'text-red-600 dark:text-red-400';
  return 'text-gray-600 dark:text-gray-400';
}

function GreekItem({
  label,
  value,
  symbol,
  decimals,
  tooltip,
}: {
  label: string;
  value: number;
  symbol: string;
  decimals: number;
  tooltip: string;
}) {
  const [showTooltip, setShowTooltip] = useState(false);

  return (
    <div className="text-center relative">
      <div className="text-xs text-gray-500 dark:text-gray-400 flex items-center justify-center gap-1">
        <span className="font-medium">{symbol}</span> {label}
        <div className="relative">
          <button
            type="button"
            className="text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 focus:outline-none"
            onMouseEnter={() => setShowTooltip(true)}
            onMouseLeave={() => setShowTooltip(false)}
            onClick={() => setShowTooltip(!showTooltip)}
            aria-label="More info"
          >
            <Info className="h-3 w-3" />
          </button>
          {showTooltip && (
            <div className="absolute left-1/2 -translate-x-1/2 top-5 z-50 w-48 rounded-lg bg-gray-900 dark:bg-gray-700 p-2 text-xs text-white shadow-lg text-left">
              {tooltip}
              <div className="absolute -top-1 left-1/2 -translate-x-1/2 h-2 w-2 rotate-45 bg-gray-900 dark:bg-gray-700" />
            </div>
          )}
        </div>
      </div>
      <div className={`mt-1 text-lg font-semibold ${getGreekColor(value)}`}>
        {formatGreek(value, decimals)}
      </div>
    </div>
  );
}

export function GreeksPanel({ greeks }: GreeksPanelProps) {
  if (!greeks || greeks.position_count === 0) {
    return (
      <div className="rounded-lg bg-white p-6 shadow dark:bg-gray-800">
        <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">Portfolio Greeks</h3>
        <p className="mt-4 text-sm text-gray-400 dark:text-gray-500">No open option positions</p>
      </div>
    );
  }

  const greekItems = [
    { label: 'Delta', value: greeks.total_delta, symbol: '\u0394', decimals: 0, tooltip: 'Directional exposure. Positive = bullish, negative = bearish. Measures $ change per $1 move in underlying.' },
    { label: 'Gamma', value: greeks.total_gamma, symbol: '\u0393', decimals: 2, tooltip: 'Rate of delta change. High gamma = delta changes quickly with price moves. Important near expiration.' },
    { label: 'Theta', value: greeks.total_theta, symbol: '\u0398', decimals: 0, tooltip: 'Daily time decay. Negative = losing value daily, positive = collecting premium daily.' },
    { label: 'Vega', value: greeks.total_vega, symbol: 'V', decimals: 0, tooltip: 'Volatility exposure. $ change per 1% change in implied volatility. Positive = benefits from rising IV.' },
  ];

  return (
    <div className="rounded-lg bg-white p-6 shadow dark:bg-gray-800">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">Portfolio Greeks</h3>
        <span className="text-xs text-gray-400 dark:text-gray-500">
          {greeks.position_count} position{greeks.position_count !== 1 ? 's' : ''}
        </span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-4">
        {greekItems.map((item) => (
          <GreekItem
            key={item.label}
            label={item.label}
            value={item.value}
            symbol={item.symbol}
            decimals={item.decimals}
            tooltip={item.tooltip}
          />
        ))}
      </div>

      {greeks.last_updated && (
        <p className="mt-4 text-xs text-gray-400 dark:text-gray-500 text-center">
          Updated: {new Date(greeks.last_updated).toLocaleString()}
        </p>
      )}
    </div>
  );
}
