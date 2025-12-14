'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api/client';
import { formatCurrency } from '@/lib/utils';
import { ChevronLeft, ChevronRight, Settings, Camera, Info } from 'lucide-react';

interface Trade {
  id: number;
  underlying: string;
  strategy_type: string;
  status: string;
  opened_at: string;
  closed_at: string | null;
  realized_pnl: string | null;
  num_legs: number;
}

interface Execution {
  id: number;
  strike: number | null;
  expiration: string | null;
  quantity: number;
  option_type: string | null;
}

interface DayData {
  date: Date;
  pnl: number;
  totalTrades: number;
  winningTrades: number;
  losingTrades: number;
  opened: number;
  closed: number;
  trades: Trade[];
}

interface WeekData {
  weekNum: number;
  pnl: number;
  tradingDays: number;
}

export default function CalendarPage() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [currentMonth, setCurrentMonth] = useState(new Date());
  const [selectedDay, setSelectedDay] = useState<DayData | null>(null);
  const [tradeExecutions, setTradeExecutions] = useState<Record<number, Execution[]>>({});
  const [loadingExecutions, setLoadingExecutions] = useState(false);

  async function fetchTrades() {
    try {
      setLoading(true);
      // Fetch all trades with pagination (API has limit restrictions)
      let allTrades: Trade[] = [];
      let offset = 0;
      const batchSize = 100;
      let hasMore = true;

      while (hasMore) {
        const data: any = await api.trades.list({ limit: batchSize, skip: offset });
        const batch = data.trades || [];
        allTrades = [...allTrades, ...batch];

        if (batch.length < batchSize || allTrades.length >= (data.total || 0)) {
          hasMore = false;
        } else {
          offset += batchSize;
        }
      }

      setTrades(allTrades);
    } catch (error) {
      console.error('Error fetching trades:', error);
      setTrades([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchTrades();
  }, []);

  // Fetch executions for trades when a day is selected
  async function fetchExecutionsForTrades(dayTrades: Trade[]) {
    setLoadingExecutions(true);
    const newExecutions: Record<number, Execution[]> = { ...tradeExecutions };

    await Promise.all(
      dayTrades.map(async (trade) => {
        if (!newExecutions[trade.id]) {
          try {
            const response = await fetch(`http://localhost:8000/api/v1/trades/${trade.id}/executions`);
            const data = await response.json();
            newExecutions[trade.id] = data.executions || [];
          } catch (error) {
            console.error(`Error fetching executions for trade ${trade.id}:`, error);
            newExecutions[trade.id] = [];
          }
        }
      })
    );

    setTradeExecutions(newExecutions);
    setLoadingExecutions(false);
  }

  // Handle day click
  function handleDayClick(dayData: DayData) {
    setSelectedDay(dayData);
    fetchExecutionsForTrades(dayData.trades);
  }

  // Format date to YYYY-MM-DD in local timezone
  function formatDateLocal(date: Date): string {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  // Format currency in K format
  function formatK(amount: number): string {
    if (Math.abs(amount) >= 1000) {
      return `${amount >= 0 ? '' : '-'}$${Math.abs(amount / 1000).toFixed(2)}K`;
    }
    return `${amount >= 0 ? '' : '-'}$${Math.abs(amount).toFixed(0)}`;
  }

  // Get days in month with padding
  function getDaysInMonth(date: Date): Date[] {
    const year = date.getFullYear();
    const month = date.getMonth();
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);

    const days: Date[] = [];

    // Add padding days from previous month
    const startDayOfWeek = firstDay.getDay();
    for (let i = startDayOfWeek - 1; i >= 0; i--) {
      const d = new Date(year, month, -i);
      days.push(d);
    }

    // Add days of current month
    for (let d = 1; d <= lastDay.getDate(); d++) {
      days.push(new Date(year, month, d));
    }

    // Add padding days from next month to complete 6 rows (42 days)
    while (days.length < 42) {
      const nextDay = days.length - startDayOfWeek - lastDay.getDate() + 1;
      days.push(new Date(year, month + 1, nextDay));
    }

    return days;
  }

  // Calculate day data from trades
  function getDayData(date: Date): DayData {
    const dateStr = formatDateLocal(date);

    let pnl = 0;
    let winningTrades = 0;
    let losingTrades = 0;
    let opened = 0;
    let closed = 0;
    const dayTrades: Trade[] = [];

    trades.forEach(trade => {
      const openedDate = trade.opened_at ? trade.opened_at.split('T')[0] : null;
      const closedDate = trade.closed_at ? trade.closed_at.split('T')[0] : null;

      if (openedDate === dateStr) {
        opened++;
        if (!dayTrades.includes(trade)) {
          dayTrades.push(trade);
        }
      }

      if (closedDate === dateStr) {
        closed++;
        const tradePnl = trade.realized_pnl ? parseFloat(trade.realized_pnl) : 0;
        pnl += tradePnl;
        if (tradePnl > 0) winningTrades++;
        else if (tradePnl < 0) losingTrades++;
        if (!dayTrades.includes(trade)) {
          dayTrades.push(trade);
        }
      }
    });

    return {
      date,
      pnl,
      totalTrades: closed, // Total trades closed (for P&L calculation)
      winningTrades,
      losingTrades,
      opened,
      closed,
      trades: dayTrades
    };
  }

  // Calculate weekly summaries
  function getWeeklyData(days: Date[]): WeekData[] {
    const weeks: WeekData[] = [];

    for (let i = 0; i < 6; i++) {
      const weekDays = days.slice(i * 7, (i + 1) * 7);
      let weekPnl = 0;
      let tradingDays = 0;

      weekDays.forEach(day => {
        if (isCurrentMonth(day)) {
          const dayData = getDayData(day);
          if (dayData.totalTrades > 0) {
            weekPnl += dayData.pnl;
            tradingDays++;
          }
        }
      });

      weeks.push({ weekNum: i + 1, pnl: weekPnl, tradingDays });
    }

    return weeks;
  }

  // Navigate months
  function prevMonth() {
    setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1, 1));
    setSelectedDay(null);
  }

  function nextMonth() {
    setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1, 1));
    setSelectedDay(null);
  }

  function goToThisMonth() {
    setCurrentMonth(new Date());
    setSelectedDay(null);
  }

  // Check if date is in current month
  function isCurrentMonth(date: Date): boolean {
    return date.getMonth() === currentMonth.getMonth() && date.getFullYear() === currentMonth.getFullYear();
  }

  // Check if date is today
  function isToday(date: Date): boolean {
    const today = new Date();
    return date.toDateString() === today.toDateString();
  }

  // Get background color class based on P&L
  function getDayBgClass(dayData: DayData, isInMonth: boolean): string {
    if (!isInMonth) return 'bg-gray-50';
    if (dayData.opened === 0 && dayData.closed === 0) return 'bg-white';
    // Color based on closed trade P&L
    if (dayData.closed > 0) {
      if (dayData.pnl > 0) return 'bg-green-100';
      if (dayData.pnl < 0) return 'bg-red-100';
      return 'bg-gray-100'; // break even
    }
    // Only opened trades - light blue
    return 'bg-blue-50';
  }

  const days = getDaysInMonth(currentMonth);
  const weeklyData = getWeeklyData(days);

  // Calculate monthly totals
  const monthlyData = days.filter(d => isCurrentMonth(d)).map(d => getDayData(d));
  const monthlyPnl = monthlyData.reduce((sum, d) => sum + d.pnl, 0);
  const tradingDays = monthlyData.filter(d => d.totalTrades > 0).length;

  const weekDays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-100 p-6">
        <div className="animate-pulse">
          <div className="h-[600px] rounded-lg bg-gray-200" />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-100">
      <div className="p-6">
        <div className="flex gap-6">
          {/* Main Calendar */}
          <div className="flex-1 bg-white rounded-xl shadow-sm overflow-hidden">
            {/* Header */}
            <div className="px-6 py-4 flex items-center justify-between border-b border-gray-100">
              <div className="flex items-center gap-4">
                <button
                  onClick={prevMonth}
                  className="p-1 hover:bg-gray-100 rounded transition-colors"
                >
                  <ChevronLeft className="h-5 w-5 text-gray-600" />
                </button>
                <h2 className="text-lg font-semibold text-gray-900 min-w-[180px] text-center">
                  {currentMonth.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}
                </h2>
                <button
                  onClick={nextMonth}
                  className="p-1 hover:bg-gray-100 rounded transition-colors"
                >
                  <ChevronRight className="h-5 w-5 text-gray-600" />
                </button>
                <button
                  onClick={goToThisMonth}
                  className="ml-2 px-3 py-1.5 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
                >
                  This month
                </button>
              </div>
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-gray-500">Monthly stats:</span>
                  <span className={`font-semibold ${monthlyPnl >= 0 ? 'text-green-600' : 'text-red-500'}`}>
                    {formatK(monthlyPnl)}
                  </span>
                  <span className="text-gray-400">|</span>
                  <span className="text-gray-700">{tradingDays} days</span>
                </div>
                <div className="flex items-center gap-2 text-gray-400">
                  <button className="p-1.5 hover:bg-gray-100 rounded"><Settings className="h-4 w-4" /></button>
                  <button className="p-1.5 hover:bg-gray-100 rounded"><Camera className="h-4 w-4" /></button>
                  <button className="p-1.5 hover:bg-gray-100 rounded"><Info className="h-4 w-4" /></button>
                </div>
              </div>
            </div>

            {/* Week Day Headers */}
            <div className="grid grid-cols-7 border-b border-gray-100">
              {weekDays.map(day => (
                <div
                  key={day}
                  className="px-2 py-3 text-center text-sm font-medium text-gray-500"
                >
                  {day}
                </div>
              ))}
            </div>

            {/* Calendar Grid */}
            <div className="grid grid-cols-7">
              {days.map((date, idx) => {
                const dayData = getDayData(date);
                const inMonth = isCurrentMonth(date);
                const today = isToday(date);
                const hasActivity = dayData.opened > 0 || dayData.closed > 0;
                const winRate = dayData.closed > 0
                  ? ((dayData.winningTrades / dayData.closed) * 100).toFixed(dayData.closed > 2 ? 2 : 1)
                  : 0;

                return (
                  <div
                    key={idx}
                    onClick={() => hasActivity && inMonth ? handleDayClick(dayData) : null}
                    className={`
                      min-h-[110px] p-2 border-b border-r border-gray-100 relative
                      ${getDayBgClass(dayData, inMonth)}
                      ${hasActivity && inMonth ? 'cursor-pointer hover:opacity-80' : ''}
                      ${!inMonth ? 'opacity-40' : ''}
                    `}
                  >
                    {/* Day Number */}
                    <div className="flex justify-end">
                      <span className={`
                        text-sm font-medium
                        ${today ? 'bg-blue-500 text-white w-7 h-7 rounded-full flex items-center justify-center' : ''}
                        ${!today && inMonth ? 'text-gray-700' : ''}
                        ${!inMonth ? 'text-gray-400' : ''}
                      `}>
                        {date.getDate()}
                      </span>
                    </div>

                    {/* Day Stats */}
                    {inMonth && hasActivity && (
                      <div className="mt-1 text-center">
                        {/* P&L - only show if closed trades */}
                        {dayData.closed > 0 && (
                          <div className={`text-lg font-bold ${dayData.pnl >= 0 ? 'text-gray-900' : 'text-red-600'}`}>
                            {formatK(dayData.pnl)}
                          </div>
                        )}
                        {/* Opened/Closed counts */}
                        <div className="flex justify-center gap-1 mt-0.5">
                          {dayData.opened > 0 && (
                            <span className="text-xs px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded">
                              +{dayData.opened}
                            </span>
                          )}
                          {dayData.closed > 0 && (
                            <span className="text-xs px-1.5 py-0.5 bg-gray-200 text-gray-700 rounded">
                              -{dayData.closed}
                            </span>
                          )}
                        </div>
                        {/* Win rate - only show if closed trades */}
                        {dayData.closed > 0 && (
                          <div className="text-xs text-gray-400 mt-0.5">
                            {winRate}%
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Weekly Summary Sidebar */}
          <div className="w-48 space-y-3">
            {weeklyData.map((week) => (
              <div
                key={week.weekNum}
                className="bg-white rounded-xl p-4 shadow-sm"
              >
                <div className="text-sm text-gray-500 mb-1">Week {week.weekNum}</div>
                <div className={`text-xl font-bold ${week.pnl >= 0 ? 'text-green-600' : 'text-red-500'}`}>
                  {week.pnl === 0 ? '$0' : formatK(week.pnl)}
                </div>
                <div className="mt-1">
                  <span className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded-full">
                    {week.tradingDays} day{week.tradingDays !== 1 ? 's' : ''}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Selected Day Details Modal */}
        {selectedDay && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setSelectedDay(null)}>
            <div className="bg-white rounded-xl shadow-xl max-w-2xl w-full mx-4 max-h-[80vh] overflow-hidden" onClick={e => e.stopPropagation()}>
              <div className="px-6 py-4 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
                <h3 className="text-lg font-semibold text-gray-900">
                  {selectedDay.date.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}
                </h3>
                <button
                  onClick={() => setSelectedDay(null)}
                  className="text-gray-400 hover:text-gray-600 text-2xl leading-none"
                >
                  &times;
                </button>
              </div>

              {/* Day Summary */}
              <div className="px-6 py-4 grid grid-cols-5 gap-4 border-b border-gray-200">
                <div>
                  <p className="text-sm text-gray-500">P&L</p>
                  <p className={`text-xl font-bold ${selectedDay.pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {formatCurrency(selectedDay.pnl)}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Opened</p>
                  <p className="text-xl font-bold text-blue-600">{selectedDay.opened}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Closed</p>
                  <p className="text-xl font-bold text-gray-900">{selectedDay.closed}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Winners</p>
                  <p className="text-xl font-bold text-green-600">{selectedDay.winningTrades}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Losers</p>
                  <p className="text-xl font-bold text-red-600">{selectedDay.losingTrades}</p>
                </div>
              </div>

              {/* Trades List */}
              {selectedDay.trades.length > 0 && (
                <div className="overflow-auto max-h-[400px]">
                  {loadingExecutions ? (
                    <div className="p-6 text-center text-gray-500">Loading trade details...</div>
                  ) : (
                    <table className="min-w-full divide-y divide-gray-200">
                      <thead className="bg-gray-50 sticky top-0">
                        <tr>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Ticker</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Strategy</th>
                          <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Qty</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Strike</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Exp</th>
                          <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Action</th>
                          <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">P&L</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-200">
                        {selectedDay.trades.map(trade => {
                          const dateStr = formatDateLocal(selectedDay.date);
                          const wasOpened = trade.opened_at?.split('T')[0] === dateStr;
                          const wasClosed = trade.closed_at?.split('T')[0] === dateStr;
                          const executions = tradeExecutions[trade.id] || [];

                          // Get unique strikes and expirations
                          const strikes = [...new Set(executions.map(e => e.strike).filter(s => s))].sort((a, b) => (a || 0) - (b || 0));
                          const expirations = [...new Set(executions.map(e => e.expiration).filter(e => e))];
                          const totalQty = executions.reduce((sum, e) => {
                            // Only count opening transactions
                            return sum + e.quantity;
                          }, 0) / 2 || trade.num_legs; // Divide by 2 to account for open+close, fallback to num_legs

                          // Format expiration date
                          const expDisplay = expirations.length > 0
                            ? new Date(expirations[0]!).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
                            : '-';

                          return (
                            <tr key={trade.id} className="hover:bg-gray-50">
                              <td className="px-4 py-3 whitespace-nowrap text-sm font-medium text-gray-900">
                                {trade.underlying}
                              </td>
                              <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600">
                                {trade.strategy_type}
                              </td>
                              <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900 text-right">
                                {Math.round(totalQty) || '-'}
                              </td>
                              <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900">
                                {strikes.length > 0 ? strikes.join('/') : '-'}
                              </td>
                              <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900">
                                {expDisplay}
                              </td>
                              <td className="px-4 py-3 whitespace-nowrap text-sm text-center">
                                <div className="flex justify-center gap-1">
                                  {wasOpened && (
                                    <span className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-xs">
                                      Opened
                                    </span>
                                  )}
                                  {wasClosed && (
                                    <span className="px-2 py-0.5 bg-gray-200 text-gray-700 rounded text-xs">
                                      Closed
                                    </span>
                                  )}
                                </div>
                              </td>
                              <td className="px-4 py-3 whitespace-nowrap text-sm text-right">
                                {wasClosed ? (
                                  <span className={`font-semibold ${parseFloat(trade.realized_pnl || '0') >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                                    {formatCurrency(parseFloat(trade.realized_pnl || '0'))}
                                  </span>
                                ) : (
                                  <span className="text-gray-400">-</span>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
