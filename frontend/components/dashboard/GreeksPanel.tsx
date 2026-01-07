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
      <div className="text-[10px] text-gray-500 dark:text-gray-400 flex items-center justify-center gap-0.5">
        <span className="font-medium">{symbol}</span>
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
            <div className="absolute left-1/2 -translate-x-1/2 top-4 z-50 w-36 rounded-lg bg-gray-900 dark:bg-gray-700 p-1.5 text-[10px] text-white shadow-lg text-left">
              {tooltip}
              <div className="absolute -top-1 left-1/2 -translate-x-1/2 h-2 w-2 rotate-45 bg-gray-900 dark:bg-gray-700" />
            </div>
          )}
        </div>
      </div>
      <div className={`text-sm font-semibold ${getGreekColor(value)}`}>
        {formatGreek(value, decimals)}
      </div>
    </div>
  );
}

export function GreeksPanel({ greeks }: GreeksPanelProps) {
  if (!greeks || greeks.position_count === 0) {
    return (
      <div className="rounded-lg bg-white p-3 shadow dark:bg-gray-800">
        <h3 className="text-xs font-medium text-gray-500 dark:text-gray-400">Portfolio Greeks</h3>
        <p className="mt-2 text-xs text-gray-400 dark:text-gray-500">No open option positions</p>
      </div>
    );
  }

  const greekItems = [
    { label: 'Delta', value: greeks.total_delta, symbol: '\u0394', decimals: 0, tooltip: 'Directional exposure. +bullish, -bearish.' },
    { label: 'Gamma', value: greeks.total_gamma, symbol: '\u0393', decimals: 2, tooltip: 'Rate of delta change.' },
    { label: 'Theta', value: greeks.total_theta, symbol: '\u0398', decimals: 0, tooltip: 'Daily time decay.' },
    { label: 'Vega', value: greeks.total_vega, symbol: 'V', decimals: 0, tooltip: 'IV exposure.' },
  ];

  return (
    <div className="rounded-lg bg-white p-3 shadow dark:bg-gray-800">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-medium text-gray-500 dark:text-gray-400">Portfolio Greeks</h3>
        <span className="text-[10px] text-gray-400 dark:text-gray-500">
          {greeks.position_count} pos
        </span>
      </div>

      <div className="mt-2 grid grid-cols-4 gap-1">
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
        <p className="mt-2 text-[10px] text-gray-400 dark:text-gray-500 text-center">
          {new Date(greeks.last_updated).toLocaleTimeString()}
        </p>
      )}
    </div>
  );
}
