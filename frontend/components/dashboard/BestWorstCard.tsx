'use client';

import { TrendingUp, TrendingDown } from 'lucide-react';
import { StrategyStats, UnderlyingStats } from '@/types';

interface BestWorstCardProps {
  title: string;
  best: StrategyStats | UnderlyingStats | null;
  worst: StrategyStats | UnderlyingStats | null;
  type: 'strategy' | 'ticker';
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

function getName(item: StrategyStats | UnderlyingStats, type: 'strategy' | 'ticker'): string {
  if (type === 'strategy') {
    return (item as StrategyStats).strategy_type;
  }
  return (item as UnderlyingStats).underlying;
}

export function BestWorstCard({ title, best, worst, type }: BestWorstCardProps) {
  return (
    <div className="rounded-lg bg-white p-6 shadow dark:bg-gray-800">
      <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">{title}</h3>

      <div className="mt-4 space-y-4">
        {/* Best */}
        <div className="flex items-center justify-between rounded-lg bg-green-50 p-3 dark:bg-green-900/20">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-green-600 dark:text-green-400" />
            <div>
              <p className="text-xs text-gray-500 dark:text-gray-400">Best</p>
              <p className="font-medium text-gray-900 dark:text-white">
                {best ? getName(best, type) : '-'}
              </p>
            </div>
          </div>
          <div className="text-right">
            <p className="text-sm font-semibold text-green-600 dark:text-green-400">
              {best ? formatCurrency(best.total_pnl) : '-'}
            </p>
            {best && (
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {best.win_rate.toFixed(0)}% win rate
              </p>
            )}
          </div>
        </div>

        {/* Worst */}
        <div className="flex items-center justify-between rounded-lg bg-red-50 p-3 dark:bg-red-900/20">
          <div className="flex items-center gap-2">
            <TrendingDown className="h-4 w-4 text-red-600 dark:text-red-400" />
            <div>
              <p className="text-xs text-gray-500 dark:text-gray-400">Worst</p>
              <p className="font-medium text-gray-900 dark:text-white">
                {worst ? getName(worst, type) : '-'}
              </p>
            </div>
          </div>
          <div className="text-right">
            <p className="text-sm font-semibold text-red-600 dark:text-red-400">
              {worst ? formatCurrency(worst.total_pnl) : '-'}
            </p>
            {worst && (
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {worst.win_rate.toFixed(0)}% win rate
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
