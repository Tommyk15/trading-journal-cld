'use client';

import { useEffect, useState, useMemo } from 'react';
import { api } from '@/lib/api/client';
import { formatCurrency } from '@/lib/utils';
import { ChevronLeft, ChevronRight } from 'lucide-react';

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
  winners: number;
  losers: number;
}

interface MonthData {
  month: number;
  year: number;
  pnl: number;
  trades: number;
  winners: number;
  losers: number;
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

  function handleDayClick(dayData: DayData) {
    setSelectedDay(dayData);
    fetchExecutionsForTrades(dayData.trades);
  }

  function formatDateLocal(date: Date): string {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  function formatK(amount: number): string {
    if (Math.abs(amount) >= 1000) {
      return `${amount >= 0 ? '' : '-'}$${Math.abs(amount / 1000).toFixed(1)}K`;
    }
    return `${amount >= 0 ? '' : '-'}$${Math.abs(amount).toFixed(0)}`;
  }

  function getDaysInMonth(date: Date): Date[] {
    const year = date.getFullYear();
    const month = date.getMonth();
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);

    const days: Date[] = [];

    const startDayOfWeek = firstDay.getDay();
    for (let i = startDayOfWeek - 1; i >= 0; i--) {
      const d = new Date(year, month, -i);
      days.push(d);
    }

    for (let d = 1; d <= lastDay.getDate(); d++) {
      days.push(new Date(year, month, d));
    }

    while (days.length < 42) {
      const nextDay = days.length - startDayOfWeek - lastDay.getDate() + 1;
      days.push(new Date(year, month + 1, nextDay));
    }

    return days;
  }

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
      totalTrades: closed,
      winningTrades,
      losingTrades,
      opened,
      closed,
      trades: dayTrades
    };
  }

  // Calculate yearly month data for bar chart
  const yearlyMonthData = useMemo((): MonthData[] => {
    const year = currentMonth.getFullYear();
    const months: MonthData[] = [];

    for (let m = 0; m < 12; m++) {
      let pnl = 0;
      let tradeCount = 0;
      let winners = 0;
      let losers = 0;

      trades.forEach(trade => {
        if (trade.closed_at) {
          const closedDate = new Date(trade.closed_at);
          if (closedDate.getFullYear() === year && closedDate.getMonth() === m) {
            const tradePnl = trade.realized_pnl ? parseFloat(trade.realized_pnl) : 0;
            pnl += tradePnl;
            tradeCount++;
            if (tradePnl > 0) winners++;
            else if (tradePnl < 0) losers++;
          }
        }
      });

      months.push({ month: m, year, pnl, trades: tradeCount, winners, losers });
    }

    return months;
  }, [trades, currentMonth]);

  // Calculate weekly data aligned with calendar rows
  function getWeeklyData(days: Date[]): WeekData[] {
    const weeks: WeekData[] = [];

    for (let i = 0; i < 6; i++) {
      const weekDays = days.slice(i * 7, (i + 1) * 7);
      let weekPnl = 0;
      let tradingDays = 0;
      let winners = 0;
      let losers = 0;

      weekDays.forEach(day => {
        const dayData = getDayData(day);
        if (dayData.totalTrades > 0) {
          weekPnl += dayData.pnl;
          tradingDays++;
          winners += dayData.winningTrades;
          losers += dayData.losingTrades;
        }
      });

      weeks.push({ weekNum: i + 1, pnl: weekPnl, tradingDays, winners, losers });
    }

    return weeks;
  }

  // Calculate monthly stats for the displayed month
  const monthlyStats = useMemo(() => {
    const year = currentMonth.getFullYear();
    const month = currentMonth.getMonth();

    let totalWinners = 0;
    let totalLosers = 0;
    let totalWinAmount = 0;
    let totalLossAmount = 0;
    let netPnl = 0;
    let totalTrades = 0;

    trades.forEach(trade => {
      if (trade.closed_at) {
        const closedDate = new Date(trade.closed_at);
        if (closedDate.getFullYear() === year && closedDate.getMonth() === month) {
          const tradePnl = trade.realized_pnl ? parseFloat(trade.realized_pnl) : 0;
          netPnl += tradePnl;
          totalTrades++;

          if (tradePnl > 0) {
            totalWinners++;
            totalWinAmount += tradePnl;
          } else if (tradePnl < 0) {
            totalLosers++;
            totalLossAmount += Math.abs(tradePnl);
          }
        }
      }
    });

    const winRatio = totalTrades > 0 ? (totalWinners / totalTrades) * 100 : 0;
    const avgWinner = totalWinners > 0 ? totalWinAmount / totalWinners : 0;
    const avgLoser = totalLosers > 0 ? totalLossAmount / totalLosers : 0;

    return {
      totalWinners,
      totalLosers,
      avgWinner,
      avgLoser,
      winRatio,
      netPnl,
      totalTrades
    };
  }, [trades, currentMonth]);

  function prevMonth() {
    setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1, 1));
    setSelectedDay(null);
  }

  function nextMonth() {
    setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1, 1));
    setSelectedDay(null);
  }

  function goToMonth(monthIndex: number) {
    setCurrentMonth(new Date(currentMonth.getFullYear(), monthIndex, 1));
    setSelectedDay(null);
  }

  function goToThisMonth() {
    setCurrentMonth(new Date());
    setSelectedDay(null);
  }

  function isCurrentMonth(date: Date): boolean {
    return date.getMonth() === currentMonth.getMonth() && date.getFullYear() === currentMonth.getFullYear();
  }

  function isToday(date: Date): boolean {
    const today = new Date();
    return date.toDateString() === today.toDateString();
  }

  function getDayBgClass(dayData: DayData, isInMonth: boolean): string {
    if (!isInMonth) return 'bg-gray-50 dark:bg-gray-800/50';
    if (dayData.opened === 0 && dayData.closed === 0) return 'bg-white dark:bg-gray-800';
    if (dayData.closed > 0) {
      if (dayData.pnl > 0) return 'bg-green-50 dark:bg-green-900/20';
      if (dayData.pnl < 0) return 'bg-red-50 dark:bg-red-900/20';
      return 'bg-gray-100 dark:bg-gray-700';
    }
    return 'bg-blue-50 dark:bg-blue-900/20';
  }

  const days = getDaysInMonth(currentMonth);
  const weeklyData = getWeeklyData(days);

  const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const weekDays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

  // Calculate max P&L for bar chart scaling
  const maxAbsPnl = Math.max(...yearlyMonthData.map(m => Math.abs(m.pnl)), 1);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-100 dark:bg-gray-900 p-6 transition-colors">
        <div className="animate-pulse">
          <div className="h-[800px] rounded-lg bg-gray-200 dark:bg-gray-700" />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900 transition-colors">
      <div className="p-6 space-y-4">
        {/* Yearly P&L Bar Chart */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm p-4 transition-colors">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{currentMonth.getFullYear()} Monthly P&L</h2>
            <div className="text-sm text-gray-500 dark:text-gray-400">
              YTD: <span className={`font-semibold ${yearlyMonthData.reduce((s, m) => s + m.pnl, 0) >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                {formatCurrency(yearlyMonthData.reduce((s, m) => s + m.pnl, 0))}
              </span>
            </div>
          </div>
          <div className="flex items-end justify-between gap-1 h-24">
            {yearlyMonthData.map((m, idx) => {
              const barHeight = maxAbsPnl > 0 ? (Math.abs(m.pnl) / maxAbsPnl) * 100 : 0;
              const isSelected = idx === currentMonth.getMonth();

              return (
                <div
                  key={idx}
                  className="flex-1 flex flex-col items-center cursor-pointer group"
                  onClick={() => goToMonth(idx)}
                >
                  <div className="relative w-full h-20 flex items-end justify-center">
                    {m.pnl !== 0 && (
                      <div
                        className={`
                          w-full max-w-[40px] rounded-t transition-all
                          ${m.pnl >= 0 ? 'bg-green-500' : 'bg-red-500'}
                          ${isSelected ? 'opacity-100' : 'opacity-60 group-hover:opacity-80'}
                        `}
                        style={{ height: `${Math.max(barHeight, 4)}%` }}
                      />
                    )}
                    {m.pnl === 0 && (
                      <div className="w-full max-w-[40px] h-1 bg-gray-200 dark:bg-gray-600 rounded" />
                    )}
                  </div>
                  <div className={`
                    text-xs mt-1 font-medium
                    ${isSelected ? 'text-blue-600 dark:text-blue-400' : 'text-gray-500 dark:text-gray-400'}
                  `}>
                    {monthNames[idx]}
                  </div>
                  <div className={`
                    text-xs
                    ${m.pnl >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}
                    ${m.pnl === 0 ? 'text-gray-400 dark:text-gray-500' : ''}
                  `}>
                    {m.pnl === 0 ? '-' : formatK(m.pnl)}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Monthly Stats Bar */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm px-6 py-4 transition-colors">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-8">
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">Net P&L</p>
                <p className={`text-2xl font-bold ${monthlyStats.netPnl >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                  {formatCurrency(monthlyStats.netPnl)}
                </p>
              </div>
              <div className="h-12 w-px bg-gray-200 dark:bg-gray-700" />
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">Total Trades</p>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">{monthlyStats.totalTrades}</p>
              </div>
              <div className="h-12 w-px bg-gray-200 dark:bg-gray-700" />
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">Win Ratio</p>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">{monthlyStats.winRatio.toFixed(1)}%</p>
              </div>
              <div className="h-12 w-px bg-gray-200 dark:bg-gray-700" />
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">Winners</p>
                <p className="text-xl font-semibold text-green-600 dark:text-green-400">{monthlyStats.totalWinners}</p>
                <p className="text-xs text-gray-500 dark:text-gray-400">avg {formatCurrency(monthlyStats.avgWinner)}</p>
              </div>
              <div className="h-12 w-px bg-gray-200 dark:bg-gray-700" />
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">Losers</p>
                <p className="text-xl font-semibold text-red-600 dark:text-red-400">{monthlyStats.totalLosers}</p>
                <p className="text-xs text-gray-500 dark:text-gray-400">avg {formatCurrency(monthlyStats.avgLoser)}</p>
              </div>
            </div>
            <button
              onClick={goToThisMonth}
              className="px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg transition-colors"
            >
              Today
            </button>
          </div>
        </div>

        {/* Calendar with Inline Weekly Summaries */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm overflow-hidden transition-colors">
          {/* Header */}
          <div className="px-6 py-4 flex items-center justify-between border-b border-gray-100 dark:border-gray-700">
            <div className="flex items-center gap-4">
              <button
                onClick={prevMonth}
                className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded transition-colors"
              >
                <ChevronLeft className="h-5 w-5 text-gray-600 dark:text-gray-400" />
              </button>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white min-w-[180px] text-center">
                {currentMonth.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}
              </h2>
              <button
                onClick={nextMonth}
                className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded transition-colors"
              >
                <ChevronRight className="h-5 w-5 text-gray-600 dark:text-gray-400" />
              </button>
            </div>
          </div>

          {/* Week Day Headers + Weekly Summary Header */}
          <div className="grid grid-cols-8 border-b border-gray-100 dark:border-gray-700">
            {weekDays.map(day => (
              <div
                key={day}
                className="px-2 py-3 text-center text-sm font-medium text-gray-500 dark:text-gray-400"
              >
                {day}
              </div>
            ))}
            <div className="px-2 py-3 text-center text-sm font-medium text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-900/50">
              Week
            </div>
          </div>

          {/* Calendar Grid with Weekly Summaries */}
          {[0, 1, 2, 3, 4, 5].map(weekIndex => {
            const weekDaysSlice = days.slice(weekIndex * 7, (weekIndex + 1) * 7);
            const week = weeklyData[weekIndex];
            const hasWeekActivity = week.tradingDays > 0;

            return (
              <div key={weekIndex} className="grid grid-cols-8">
                {/* Day Cells */}
                {weekDaysSlice.map((date, dayIdx) => {
                  const dayData = getDayData(date);
                  const inMonth = isCurrentMonth(date);
                  const today = isToday(date);
                  const hasActivity = dayData.opened > 0 || dayData.closed > 0;
                  const winRate = dayData.closed > 0
                    ? ((dayData.winningTrades / dayData.closed) * 100).toFixed(0)
                    : 0;

                  return (
                    <div
                      key={dayIdx}
                      onClick={() => hasActivity && inMonth ? handleDayClick(dayData) : null}
                      className={`
                        min-h-[100px] p-2 border-b border-r border-gray-100 dark:border-gray-700 relative
                        ${getDayBgClass(dayData, inMonth)}
                        ${hasActivity && inMonth ? 'cursor-pointer hover:opacity-80' : ''}
                        ${!inMonth ? 'opacity-40' : ''}
                      `}
                    >
                      <div className="flex justify-end">
                        <span className={`
                          text-sm font-medium
                          ${today ? 'bg-blue-500 text-white w-6 h-6 rounded-full flex items-center justify-center text-xs' : ''}
                          ${!today && inMonth ? 'text-gray-700 dark:text-gray-200' : ''}
                          ${!inMonth ? 'text-gray-400 dark:text-gray-500' : ''}
                        `}>
                          {date.getDate()}
                        </span>
                      </div>

                      {inMonth && hasActivity && (
                        <div className="mt-1 text-center">
                          {dayData.closed > 0 && (
                            <div className={`text-base font-bold ${dayData.pnl >= 0 ? 'text-green-700 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                              {formatK(dayData.pnl)}
                            </div>
                          )}
                          <div className="flex justify-center gap-1 mt-0.5">
                            {dayData.opened > 0 && (
                              <span className="text-xs px-1 py-0.5 bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300 rounded">
                                +{dayData.opened}
                              </span>
                            )}
                            {dayData.closed > 0 && (
                              <span className="text-xs px-1 py-0.5 bg-gray-200 dark:bg-gray-600 text-gray-700 dark:text-gray-200 rounded">
                                -{dayData.closed}
                              </span>
                            )}
                          </div>
                          {dayData.closed > 0 && (
                            <div className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                              {winRate}%
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}

                {/* Weekly Summary Cell */}
                <div className={`
                  min-h-[100px] p-2 border-b border-gray-100 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50
                  flex flex-col justify-center items-center
                `}>
                  {hasWeekActivity ? (
                    <>
                      <div className={`text-lg font-bold ${week.pnl >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-500 dark:text-red-400'}`}>
                        {formatK(week.pnl)}
                      </div>
                      <div className="flex gap-1 mt-1">
                        <span className="text-xs text-green-600 dark:text-green-400">{week.winners}W</span>
                        <span className="text-xs text-gray-400 dark:text-gray-500">/</span>
                        <span className="text-xs text-red-500 dark:text-red-400">{week.losers}L</span>
                      </div>
                      <div className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                        {week.tradingDays} day{week.tradingDays !== 1 ? 's' : ''}
                      </div>
                    </>
                  ) : (
                    <span className="text-xs text-gray-400 dark:text-gray-500">-</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Selected Day Details Modal */}
        {selectedDay && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setSelectedDay(null)}>
            <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl max-w-2xl w-full mx-4 max-h-[80vh] overflow-hidden" onClick={e => e.stopPropagation()}>
              <div className="px-6 py-4 bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                  {selectedDay.date.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}
                </h3>
                <button
                  onClick={() => setSelectedDay(null)}
                  className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 text-2xl leading-none"
                >
                  &times;
                </button>
              </div>

              <div className="px-6 py-4 grid grid-cols-5 gap-4 border-b border-gray-200 dark:border-gray-700">
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">P&L</p>
                  <p className={`text-xl font-bold ${selectedDay.pnl >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                    {formatCurrency(selectedDay.pnl)}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">Opened</p>
                  <p className="text-xl font-bold text-blue-600 dark:text-blue-400">{selectedDay.opened}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">Closed</p>
                  <p className="text-xl font-bold text-gray-900 dark:text-white">{selectedDay.closed}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">Winners</p>
                  <p className="text-xl font-bold text-green-600 dark:text-green-400">{selectedDay.winningTrades}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">Losers</p>
                  <p className="text-xl font-bold text-red-600 dark:text-red-400">{selectedDay.losingTrades}</p>
                </div>
              </div>

              {selectedDay.trades.length > 0 && (
                <div className="overflow-auto max-h-[400px]">
                  {loadingExecutions ? (
                    <div className="p-6 text-center text-gray-500 dark:text-gray-400">Loading trade details...</div>
                  ) : (
                    <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                      <thead className="bg-gray-50 dark:bg-gray-900 sticky top-0">
                        <tr>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Ticker</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Strategy</th>
                          <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Qty</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Strike</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Exp</th>
                          <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Action</th>
                          <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">P&L</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                        {selectedDay.trades.map(trade => {
                          const dateStr = formatDateLocal(selectedDay.date);
                          const wasOpened = trade.opened_at?.split('T')[0] === dateStr;
                          const wasClosed = trade.closed_at?.split('T')[0] === dateStr;
                          const executions = tradeExecutions[trade.id] || [];

                          const strikes = [...new Set(executions.map(e => e.strike).filter(s => s))].sort((a, b) => (a || 0) - (b || 0));
                          const expirations = [...new Set(executions.map(e => e.expiration).filter(e => e))];
                          const totalQty = executions.reduce((sum, e) => sum + e.quantity, 0) / 2 || trade.num_legs;

                          const expDisplay = expirations.length > 0
                            ? new Date(expirations[0]!).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
                            : '-';

                          return (
                            <tr key={trade.id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                              <td className="px-4 py-3 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-white">
                                {trade.underlying}
                              </td>
                              <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">
                                {trade.strategy_type}
                              </td>
                              <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900 dark:text-white text-right">
                                {Math.round(totalQty) || '-'}
                              </td>
                              <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900 dark:text-white">
                                {strikes.length > 0 ? strikes.join('/') : '-'}
                              </td>
                              <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900 dark:text-white">
                                {expDisplay}
                              </td>
                              <td className="px-4 py-3 whitespace-nowrap text-sm text-center">
                                <div className="flex justify-center gap-1">
                                  {wasOpened && (
                                    <span className="px-2 py-0.5 bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300 rounded text-xs">
                                      Opened
                                    </span>
                                  )}
                                  {wasClosed && (
                                    <span className="px-2 py-0.5 bg-gray-200 dark:bg-gray-600 text-gray-700 dark:text-gray-200 rounded text-xs">
                                      Closed
                                    </span>
                                  )}
                                </div>
                              </td>
                              <td className="px-4 py-3 whitespace-nowrap text-sm text-right">
                                {wasClosed ? (
                                  <span className={`font-semibold ${parseFloat(trade.realized_pnl || '0') >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                                    {formatCurrency(parseFloat(trade.realized_pnl || '0'))}
                                  </span>
                                ) : (
                                  <span className="text-gray-400 dark:text-gray-500">-</span>
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
