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
    <div className="rounded-lg bg-white p-3 shadow dark:bg-gray-800">
      <h3 className="text-xs font-medium text-gray-500 dark:text-gray-400">{title}</h3>

      <div className="mt-2 space-y-2">
        {/* Best */}
        <div className="flex items-center justify-between rounded bg-green-50 p-2 dark:bg-green-900/20">
          <div className="flex items-center gap-1.5">
            <TrendingUp className="h-3 w-3 text-green-600 dark:text-green-400" />
            <div>
              <p className="text-[10px] text-gray-500 dark:text-gray-400">Best</p>
              <p className="text-xs font-medium text-gray-900 dark:text-white truncate max-w-[100px]">
                {best ? getName(best, type) : '-'}
              </p>
            </div>
          </div>
          <div className="text-right">
            <p className="text-xs font-semibold text-green-600 dark:text-green-400">
              {best ? formatCurrency(best.total_pnl) : '-'}
            </p>
            {best && (
              <p className="text-[10px] text-gray-500 dark:text-gray-400">
                {best.win_rate.toFixed(0)}% WR
              </p>
            )}
          </div>
        </div>

        {/* Worst */}
        <div className="flex items-center justify-between rounded bg-red-50 p-2 dark:bg-red-900/20">
          <div className="flex items-center gap-1.5">
            <TrendingDown className="h-3 w-3 text-red-600 dark:text-red-400" />
            <div>
              <p className="text-[10px] text-gray-500 dark:text-gray-400">Worst</p>
              <p className="text-xs font-medium text-gray-900 dark:text-white truncate max-w-[100px]">
                {worst ? getName(worst, type) : '-'}
              </p>
            </div>
          </div>
          <div className="text-right">
            <p className="text-xs font-semibold text-red-600 dark:text-red-400">
              {worst ? formatCurrency(worst.total_pnl) : '-'}
            </p>
            {worst && (
              <p className="text-[10px] text-gray-500 dark:text-gray-400">
                {worst.win_rate.toFixed(0)}% WR
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
