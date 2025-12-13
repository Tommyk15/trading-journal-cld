'use client';

import { useEffect, useState } from 'react';
import { Header } from '@/components/layout/Header';
import { api } from '@/lib/api/client';
import { formatCurrency, formatDate } from '@/lib/utils';
import { Calendar, AlertCircle } from 'lucide-react';
import type { UpcomingExpiration } from '@/types';

export default function CalendarPage() {
  const [expirations, setExpirations] = useState<UpcomingExpiration[]>([]);
  const [loading, setLoading] = useState(true);
  const [daysAhead, setDaysAhead] = useState(30);

  async function fetchExpirations() {
    try {
      setLoading(true);
      const data = await api.calendar.upcomingExpirations(daysAhead);
      // API returns { expirations: [...] }, extract the array
      const expArray = (data as any)?.expirations || data || [];
      setExpirations(Array.isArray(expArray) ? expArray : []);
    } catch (error) {
      console.error('Error fetching expirations:', error);
      setExpirations([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchExpirations();
  }, [daysAhead]);

  const totalPositionsExpiring = (expirations || []).reduce(
    (sum, exp: any) => sum + (exp.position_count || 0),
    0
  );

  if (loading) {
    return (
      <div>
        <Header
          title="Calendar"
          subtitle="View upcoming option expirations and trade schedule"
        />
        <div className="p-6">
          <div className="animate-pulse">
            <div className="h-96 rounded-lg bg-gray-200" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div>
      <Header
        title="Calendar"
        subtitle="View upcoming option expirations and trade schedule"
      />

      <div className="p-6 space-y-6">
        {/* Summary */}
        <div className="grid gap-6 md:grid-cols-3">
          <div className="rounded-lg bg-white p-6 shadow">
            <div className="flex items-center gap-2">
              <Calendar className="h-5 w-5 text-blue-600" />
              <h3 className="text-sm font-medium text-gray-600">
                Expiration Dates
              </h3>
            </div>
            <p className="mt-2 text-3xl font-bold text-gray-900">
              {expirations.length}
            </p>
            <p className="mt-1 text-sm text-gray-500">
              in next {daysAhead} days
            </p>
          </div>
          <div className="rounded-lg bg-white p-6 shadow">
            <div className="flex items-center gap-2">
              <AlertCircle className="h-5 w-5 text-orange-600" />
              <h3 className="text-sm font-medium text-gray-600">
                Positions Expiring
              </h3>
            </div>
            <p className="mt-2 text-3xl font-bold text-gray-900">
              {totalPositionsExpiring}
            </p>
          </div>
          <div className="rounded-lg bg-white p-6 shadow">
            <label className="block text-sm font-medium text-gray-700">
              Days Ahead
            </label>
            <select
              value={daysAhead}
              onChange={(e) => setDaysAhead(Number(e.target.value))}
              className="mt-2 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
            >
              <option value={7}>7 days</option>
              <option value={14}>14 days</option>
              <option value={30}>30 days</option>
              <option value={60}>60 days</option>
              <option value={90}>90 days</option>
            </select>
          </div>
        </div>

        {/* Expirations List */}
        {expirations.length === 0 ? (
          <div className="rounded-lg bg-white p-12 text-center shadow">
            <Calendar className="mx-auto h-12 w-12 text-gray-400" />
            <h3 className="mt-4 text-lg font-medium text-gray-900">
              No Upcoming Expirations
            </h3>
            <p className="mt-2 text-sm text-gray-500">
              You don't have any options expiring in the next {daysAhead} days.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {expirations.map((expiration, idx) => (
              <div key={idx} className="rounded-lg bg-white shadow overflow-hidden">
                <div className="bg-gray-50 px-6 py-4 border-b border-gray-200">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-lg font-semibold text-gray-900">
                        {formatDate(expiration.expiration_date)}
                      </h3>
                      <p className="mt-1 text-sm text-gray-500">
                        {expiration.days_until === 0
                          ? 'Expires today'
                          : expiration.days_until === 1
                          ? 'Expires tomorrow'
                          : `${expiration.days_until} days until expiration`}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-2xl font-bold text-gray-900">
                        {expiration.position_count}
                      </p>
                      <p className="text-sm text-gray-500">
                        {expiration.position_count === 1 ? 'position' : 'positions'}
                      </p>
                    </div>
                  </div>
                </div>

                {/* Positions Table */}
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Symbol
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Type
                        </th>
                        <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Strike
                        </th>
                        <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Quantity
                        </th>
                        <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Current Price
                        </th>
                        <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Market Value
                        </th>
                        <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Unrealized P&L
                        </th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                      {expiration.positions.map((position) => (
                        <tr key={position.id} className="hover:bg-gray-50">
                          <td className="px-6 py-4 whitespace-nowrap">
                            <div>
                              <div className="text-sm font-medium text-gray-900">
                                {position.symbol}
                              </div>
                              <div className="text-sm text-gray-500">
                                {position.underlying_symbol}
                              </div>
                            </div>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                            {position.option_type}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 text-right">
                            {formatCurrency(position.strike || 0)}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 text-right">
                            {position.quantity}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 text-right">
                            {position.current_price
                              ? formatCurrency(position.current_price)
                              : '-'}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 text-right">
                            {position.market_value
                              ? formatCurrency(position.market_value)
                              : '-'}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-right">
                            <span
                              className={
                                (position.unrealized_pnl || 0) > 0
                                  ? 'text-green-600'
                                  : (position.unrealized_pnl || 0) < 0
                                  ? 'text-red-600'
                                  : 'text-gray-600'
                              }
                            >
                              {position.unrealized_pnl
                                ? formatCurrency(position.unrealized_pnl)
                                : '-'}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
