'use client';

import React, { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { LegGreeks } from '@/types';
import { formatCurrency, formatDate } from '@/lib/utils';

interface LegGreeksTableProps {
  legs: LegGreeks[];
}

export default function LegGreeksTable({ legs }: LegGreeksTableProps) {
  const [expandedLeg, setExpandedLeg] = useState<number | null>(null);

  const formatGreek = (value: number | string | null, decimals: number = 4) => {
    if (value === null || value === undefined) return '—';
    const num = Number(value);
    const sign = num >= 0 ? '+' : '';
    return `${sign}${num.toFixed(decimals)}`;
  };

  const formatIV = (value: number | string | null) => {
    if (value === null || value === undefined) return '—';
    const num = Number(value);
    return `${(num * 100).toFixed(1)}%`;
  };

  const getGreekColor = (value: number | string | null) => {
    if (value === null || value === undefined) return 'text-gray-500 dark:text-gray-400';
    const num = Number(value);
    return num >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400';
  };

  const getQuantityColor = (quantity: number | string) => {
    const num = Number(quantity);
    return num >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400';
  };

  const formatLegName = (leg: LegGreeks) => {
    if (!leg.strike || !leg.expiration || !leg.option_type) {
      return `Leg ${leg.leg_index + 1}`;
    }
    const expDate = new Date(leg.expiration);
    const month = expDate.toLocaleString('default', { month: 'short' });
    const day = expDate.getDate();
    return `${month}${day} ${leg.strike}${leg.option_type}`;
  };

  // Calculate net Greeks (convert strings to numbers)
  const netGreeks = {
    delta: legs.reduce((sum, leg) => sum + Number(leg.delta ?? 0) * Number(leg.quantity), 0),
    gamma: legs.reduce((sum, leg) => sum + Number(leg.gamma ?? 0) * Number(leg.quantity), 0),
    theta: legs.reduce((sum, leg) => sum + Number(leg.theta ?? 0) * Number(leg.quantity), 0),
    vega: legs.reduce((sum, leg) => sum + Number(leg.vega ?? 0) * Number(leg.quantity), 0),
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 dark:border-gray-700">
            <th className="py-2 px-2 text-left font-medium text-gray-500 dark:text-gray-400">Leg</th>
            <th className="py-2 px-2 text-right font-medium text-gray-500 dark:text-gray-400">Qty</th>
            <th className="py-2 px-2 text-right font-medium text-gray-500 dark:text-gray-400">Delta</th>
            <th className="py-2 px-2 text-right font-medium text-gray-500 dark:text-gray-400">Gamma</th>
            <th className="py-2 px-2 text-right font-medium text-gray-500 dark:text-gray-400">Theta</th>
            <th className="py-2 px-2 text-right font-medium text-gray-500 dark:text-gray-400">Vega</th>
            <th className="py-2 px-2 text-right font-medium text-gray-500 dark:text-gray-400">IV</th>
            <th className="py-2 px-2 text-center font-medium text-gray-500 dark:text-gray-400"></th>
          </tr>
        </thead>
        <tbody>
          {legs.map((leg) => (
            <React.Fragment key={leg.leg_index}>
              <tr
                className="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700/50"
              >
                <td className="py-2 px-2 font-medium text-gray-900 dark:text-white">
                  {formatLegName(leg)}
                </td>
                <td className={`py-2 px-2 text-right font-medium ${getQuantityColor(leg.quantity)}`}>
                  {leg.quantity > 0 ? `+${leg.quantity}` : leg.quantity}
                </td>
                <td className={`py-2 px-2 text-right ${getGreekColor(leg.delta)}`}>
                  {formatGreek(leg.delta, 4)}
                </td>
                <td className={`py-2 px-2 text-right ${getGreekColor(leg.gamma)}`}>
                  {formatGreek(leg.gamma, 4)}
                </td>
                <td className={`py-2 px-2 text-right ${getGreekColor(leg.theta)}`}>
                  {leg.theta !== null ? formatCurrency(leg.theta) : '—'}
                </td>
                <td className={`py-2 px-2 text-right ${getGreekColor(leg.vega)}`}>
                  {leg.vega !== null ? formatCurrency(leg.vega) : '—'}
                </td>
                <td className="py-2 px-2 text-right text-gray-900 dark:text-white">
                  {formatIV(leg.iv)}
                </td>
                <td className="py-2 px-2 text-center">
                  <button
                    onClick={() => setExpandedLeg(expandedLeg === leg.leg_index ? null : leg.leg_index)}
                    className="p-1 hover:bg-gray-200 dark:hover:bg-gray-600 rounded"
                  >
                    {expandedLeg === leg.leg_index ? (
                      <ChevronUp className="h-4 w-4 text-gray-500" />
                    ) : (
                      <ChevronDown className="h-4 w-4 text-gray-500" />
                    )}
                  </button>
                </td>
              </tr>
              {/* Expanded details row */}
              {expandedLeg === leg.leg_index && (
                <tr className="bg-gray-50 dark:bg-gray-700/30">
                  <td colSpan={8} className="py-2 px-4">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
                      <div>
                        <span className="text-gray-500 dark:text-gray-400">Bid/Ask</span>
                        <p className="font-medium text-gray-900 dark:text-white">
                          {leg.bid !== null ? formatCurrency(leg.bid) : '—'} / {leg.ask !== null ? formatCurrency(leg.ask) : '—'}
                        </p>
                      </div>
                      <div>
                        <span className="text-gray-500 dark:text-gray-400">Spread</span>
                        <p className="font-medium text-gray-900 dark:text-white">
                          {leg.bid_ask_spread !== null ? formatCurrency(leg.bid_ask_spread) : '—'}
                        </p>
                      </div>
                      <div>
                        <span className="text-gray-500 dark:text-gray-400">Open Interest</span>
                        <p className="font-medium text-gray-900 dark:text-white">
                          {leg.open_interest !== null ? leg.open_interest.toLocaleString() : '—'}
                        </p>
                      </div>
                      <div>
                        <span className="text-gray-500 dark:text-gray-400">Volume</span>
                        <p className="font-medium text-gray-900 dark:text-white">
                          {leg.volume !== null ? leg.volume.toLocaleString() : '—'}
                        </p>
                      </div>
                      <div>
                        <span className="text-gray-500 dark:text-gray-400">Option Price</span>
                        <p className="font-medium text-gray-900 dark:text-white">
                          {leg.option_price !== null ? formatCurrency(leg.option_price) : '—'}
                        </p>
                      </div>
                      <div>
                        <span className="text-gray-500 dark:text-gray-400">Underlying</span>
                        <p className="font-medium text-gray-900 dark:text-white">
                          {leg.underlying_price !== null ? formatCurrency(leg.underlying_price) : '—'}
                        </p>
                      </div>
                      <div>
                        <span className="text-gray-500 dark:text-gray-400">Source</span>
                        <p className="font-medium text-gray-900 dark:text-white">
                          {leg.data_source || '—'}
                        </p>
                      </div>
                      <div>
                        <span className="text-gray-500 dark:text-gray-400">Captured</span>
                        <p className="font-medium text-gray-900 dark:text-white">
                          {leg.captured_at ? formatDate(leg.captured_at) : '—'}
                        </p>
                      </div>
                    </div>
                  </td>
                </tr>
              )}
            </React.Fragment>
          ))}
          {/* NET totals row */}
          <tr className="bg-gray-100 dark:bg-gray-700 font-medium">
            <td className="py-2 px-2 text-gray-900 dark:text-white">NET</td>
            <td className="py-2 px-2 text-right text-gray-500 dark:text-gray-400">—</td>
            <td className={`py-2 px-2 text-right ${getGreekColor(netGreeks.delta)}`}>
              {formatGreek(netGreeks.delta, 2)}
            </td>
            <td className={`py-2 px-2 text-right ${getGreekColor(netGreeks.gamma)}`}>
              {formatGreek(netGreeks.gamma, 4)}
            </td>
            <td className={`py-2 px-2 text-right ${getGreekColor(netGreeks.theta)}`}>
              {formatCurrency(netGreeks.theta)}
            </td>
            <td className={`py-2 px-2 text-right ${getGreekColor(netGreeks.vega)}`}>
              {formatCurrency(netGreeks.vega)}
            </td>
            <td className="py-2 px-2 text-right text-gray-500 dark:text-gray-400">—</td>
            <td className="py-2 px-2"></td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
