'use client';

import { TimePeriod } from '@/types';

interface TimePeriodSelectorProps {
  selected: TimePeriod;
  onChange: (period: TimePeriod) => void;
}

const periods: { value: TimePeriod; label: string }[] = [
  { value: 'all', label: 'Max' },
  { value: 'ytd', label: 'YTD' },
  { value: 'monthly', label: 'Monthly' },
  { value: 'weekly', label: 'Weekly' },
];

export function TimePeriodSelector({ selected, onChange }: TimePeriodSelectorProps) {
  return (
    <div className="inline-flex rounded-lg bg-gray-100 p-1 dark:bg-gray-800">
      {periods.map((period) => (
        <button
          key={period.value}
          onClick={() => onChange(period.value)}
          className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
            selected === period.value
              ? 'bg-white text-gray-900 shadow dark:bg-gray-700 dark:text-white'
              : 'text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white'
          }`}
        >
          {period.label}
        </button>
      ))}
    </div>
  );
}
