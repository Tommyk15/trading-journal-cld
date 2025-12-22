'use client';

import React, { useEffect, useState, useRef, useCallback } from 'react';
import { Header } from '@/components/layout/Header';
import { api } from '@/lib/api/client';
import { formatCurrency, formatDate, getPnlColor, formatPriceSmart, formatNumberSmart } from '@/lib/utils';
import type { Trade, TradeAnalytics as TradeAnalyticsType, Tag } from '@/types';
import { ChevronDown, ChevronRight, ChevronUp, Merge, AlertCircle, Calendar } from 'lucide-react';
import TradeAnalytics from '@/components/trade-analytics/TradeAnalytics';
import { TableColumnConfig, LightweightChartWidget } from '@/components/trade-analytics';
import type { ColumnConfig } from '@/components/trade-analytics/TableColumnConfig';
import { useTimezone } from '@/contexts/TimezoneContext';
import TagSelector from '@/components/tags/TagSelector';

// Default column configuration for trades table
const DEFAULT_COLUMNS: ColumnConfig[] = [
  { id: 'select', label: 'Select', visible: true },
  { id: 'expand', label: 'Expand', visible: true },
  { id: 'status', label: 'Status', visible: true },
  { id: 'openTime', label: 'Open Time', visible: true },
  { id: 'closeTime', label: 'Close Time', visible: true },
  { id: 'ticker', label: 'Ticker', visible: true },
  { id: 'qty', label: 'Qty', visible: true },
  { id: 'strategy', label: 'Strategy', visible: true },
  { id: 'strike', label: 'Strike', visible: true },
  { id: 'expiration', label: 'Expiration', visible: true },
  { id: 'dte', label: 'DTE', visible: true },
  { id: 'openPrice', label: 'Open Price', visible: true },
  { id: 'closePrice', label: 'Close Price', visible: true },
  { id: 'marketValue', label: 'Market Value', visible: false },
  { id: 'commission', label: 'Commission', visible: false },
  { id: 'pnl', label: 'Net P&L', visible: true },
  { id: 'tags', label: 'Tags', visible: true },
  // Analytics columns - Greeks visible by default
  { id: 'delta', label: 'Delta', visible: true },
  { id: 'gamma', label: 'Gamma', visible: true },
  { id: 'theta', label: 'Theta', visible: true },
  { id: 'vega', label: 'Vega', visible: true },
  { id: 'iv', label: 'IV', visible: true },
  { id: 'pop', label: 'PoP', visible: false },
  { id: 'maxProfit', label: 'Max Profit', visible: false },
  { id: 'maxRisk', label: 'Max Risk', visible: false },
  { id: 'ivRank', label: 'IV Rank', visible: false },
  { id: 'daysHeld', label: 'Days Held', visible: false },
  { id: 'pnlPercent', label: '% Profit', visible: false },
];

// Default column widths (in pixels)
const DEFAULT_COLUMN_WIDTHS: Record<string, number> = {
  select: 40,
  expand: 32,
  status: 65,
  openTime: 95,
  closeTime: 95,
  ticker: 55,
  qty: 40,
  strategy: 100,
  strike: 60,
  expiration: 75,
  dte: 40,
  openPrice: 75,
  closePrice: 75,
  marketValue: 85,
  commission: 70,
  pnl: 80,
  tags: 100,
  delta: 55,
  gamma: 55,
  theta: 60,
  vega: 55,
  iv: 50,
  pop: 45,
  maxProfit: 80,
  maxRisk: 80,
  ivRank: 60,
  daysHeld: 60,
  pnlPercent: 60,
};

const COLUMN_WIDTHS_STORAGE_KEY = 'trades-table-column-widths';

// Sortable column type
type SortColumn = 'status' | 'openTime' | 'closeTime' | 'ticker' | 'qty' | 'strategy' | 'strike' | 'expiration' | 'dte' | 'pnl' | 'delta' | 'theta' | 'iv' | null;
type SortDirection = 'asc' | 'desc';


export default function TradesPage() {
  const { formatDateTime, getTimezoneAbbr } = useTimezone();
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedTrades, setExpandedTrades] = useState<Set<number>>(new Set());
  const [tradeExecutions, setTradeExecutions] = useState<Record<number, any[]>>({});
  const [selectedTradeIds, setSelectedTradeIds] = useState<Set<number>>(new Set());
  const [merging, setMerging] = useState(false);
  const [mergeError, setMergeError] = useState<string | null>(null);
  const [filters, setFilters] = useState({
    strategy: '',
    underlying_symbol: '',
    status: '',
    dateRange: 'all' as 'day' | 'prevday' | 'week' | 'month' | 'year' | 'custom' | 'all',
    startDate: '',
    endDate: '',
  });
  const [underlyingInput, setUnderlyingInput] = useState('');
  const [showCustomDatePicker, setShowCustomDatePicker] = useState(false);

  // Helper to calculate date range
  function getDateRange(range: string): { start: string | null; end: string | null } {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());

    switch (range) {
      case 'day': {
        const start = today.toISOString();
        const end = new Date(today.getTime() + 24 * 60 * 60 * 1000).toISOString();
        return { start, end };
      }
      case 'prevday': {
        const yesterday = new Date(today.getTime() - 24 * 60 * 60 * 1000);
        const start = yesterday.toISOString();
        const end = today.toISOString();
        return { start, end };
      }
      case 'week': {
        const dayOfWeek = today.getDay();
        const startOfWeek = new Date(today);
        startOfWeek.setDate(today.getDate() - dayOfWeek);
        return { start: startOfWeek.toISOString(), end: new Date(now.getTime() + 24 * 60 * 60 * 1000).toISOString() };
      }
      case 'month': {
        const startOfMonth = new Date(today.getFullYear(), today.getMonth(), 1);
        return { start: startOfMonth.toISOString(), end: new Date(now.getTime() + 24 * 60 * 60 * 1000).toISOString() };
      }
      case 'year': {
        const startOfYear = new Date(today.getFullYear(), 0, 1);
        return { start: startOfYear.toISOString(), end: new Date(now.getTime() + 24 * 60 * 60 * 1000).toISOString() };
      }
      case 'custom': {
        return {
          start: filters.startDate ? new Date(filters.startDate).toISOString() : null,
          end: filters.endDate ? new Date(filters.endDate + 'T23:59:59').toISOString() : null,
        };
      }
      default:
        return { start: null, end: null };
    }
  }
  const [tradeAnalytics, setTradeAnalytics] = useState<Record<number, TradeAnalyticsType | null>>({});
  const [columns, setColumns] = useState<ColumnConfig[]>(DEFAULT_COLUMNS);
  const [sortColumn, setSortColumn] = useState<SortColumn>('openTime');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');

  // Column resize state
  const [columnWidths, setColumnWidths] = useState<Record<string, number>>(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem(COLUMN_WIDTHS_STORAGE_KEY);
      if (saved) {
        try {
          return { ...DEFAULT_COLUMN_WIDTHS, ...JSON.parse(saved) };
        } catch {
          return DEFAULT_COLUMN_WIDTHS;
        }
      }
    }
    return DEFAULT_COLUMN_WIDTHS;
  });
  const [resizingColumn, setResizingColumn] = useState<string | null>(null);
  const resizeStartX = useRef<number>(0);
  const resizeStartWidth = useRef<number>(0);

  // Handle column resize
  const handleResizeStart = useCallback((e: React.MouseEvent, columnId: string) => {
    e.preventDefault();
    e.stopPropagation();
    setResizingColumn(columnId);
    resizeStartX.current = e.clientX;
    resizeStartWidth.current = columnWidths[columnId] || DEFAULT_COLUMN_WIDTHS[columnId] || 100;
  }, [columnWidths]);

  const handleResizeMove = useCallback((e: MouseEvent) => {
    if (!resizingColumn) return;
    const delta = e.clientX - resizeStartX.current;
    const newWidth = Math.max(40, resizeStartWidth.current + delta);
    setColumnWidths(prev => ({ ...prev, [resizingColumn]: newWidth }));
  }, [resizingColumn]);

  const handleResizeEnd = useCallback(() => {
    if (resizingColumn) {
      // Save to localStorage
      localStorage.setItem(COLUMN_WIDTHS_STORAGE_KEY, JSON.stringify(columnWidths));
    }
    setResizingColumn(null);
  }, [resizingColumn, columnWidths]);

  // Add/remove resize event listeners
  useEffect(() => {
    if (resizingColumn) {
      document.addEventListener('mousemove', handleResizeMove);
      document.addEventListener('mouseup', handleResizeEnd);
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
    }
    return () => {
      document.removeEventListener('mousemove', handleResizeMove);
      document.removeEventListener('mouseup', handleResizeEnd);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [resizingColumn, handleResizeMove, handleResizeEnd]);

  // Handle column header click for sorting
  function handleSort(column: SortColumn) {
    if (sortColumn === column) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortColumn(column);
      setSortDirection('desc');
    }
  }

  // Helper to check if column is visible
  const isColumnVisible = (id: string) => columns.find(c => c.id === id)?.visible ?? false;

  // Sortable columns set for quick lookup
  const sortableColumns = new Set(['status', 'openTime', 'closeTime', 'ticker', 'qty', 'strategy', 'strike', 'expiration', 'dte', 'pnl', 'delta', 'theta', 'iv']);

  // Right-aligned columns
  const rightAlignedColumns = new Set(['qty', 'dte', 'openPrice', 'closePrice', 'marketValue', 'commission', 'pnl', 'pop', 'maxProfit', 'maxRisk', 'delta', 'gamma', 'theta', 'vega', 'iv', 'ivRank', 'daysHeld', 'pnlPercent']);

  // Resize handle component
  function ResizeHandle({ columnId }: { columnId: string }) {
    return (
      <div
        className="absolute right-0 top-0 h-full w-2 cursor-col-resize hover:bg-blue-500 z-20"
        style={{ transform: 'translateX(50%)' }}
        onMouseDown={(e) => {
          e.preventDefault();
          e.stopPropagation();
          handleResizeStart(e, columnId);
        }}
      >
        {/* Larger hit area */}
        <div className="absolute inset-y-0 -left-2 -right-2 cursor-col-resize" />
      </div>
    );
  }

  // Render column header with resize handle
  function renderColumnHeader(col: ColumnConfig) {
    if (!col.visible) return null;

    const align = rightAlignedColumns.has(col.id) ? 'right' : 'left';
    const width = columnWidths[col.id] || DEFAULT_COLUMN_WIDTHS[col.id] || 100;
    const canResize = col.id !== 'select' && col.id !== 'expand';

    // Special cases for select and expand (no resize)
    if (col.id === 'select') {
      return (
        <th
          key={col.id}
          style={{ width: 40, minWidth: 40 }}
          className="px-2 py-2 text-center text-[10px] font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider"
        >
          <input
            type="checkbox"
            checked={selectedTradeIds.size === trades.length && trades.length > 0}
            onChange={toggleSelectAll}
            className="rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-blue-500 h-3 w-3"
          />
        </th>
      );
    }

    if (col.id === 'expand') {
      return (
        <th
          key={col.id}
          style={{ width: 32, minWidth: 32 }}
          className="px-2 py-2 text-left text-[10px] font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider"
        ></th>
      );
    }

    // Sortable columns
    if (sortableColumns.has(col.id)) {
      const isSorted = sortColumn === col.id;
      return (
        <th
          key={col.id}
          style={{ width, minWidth: 40 }}
          onClick={() => handleSort(col.id as SortColumn)}
          className={`relative px-2 py-2 text-${align} text-[10px] font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-600 select-none`}
        >
          <div className={`flex items-center gap-0.5 ${align === 'right' ? 'justify-end' : ''}`}>
            {col.label}
            {isSorted ? (
              sortDirection === 'asc' ? <ChevronUp className="h-2.5 w-2.5" /> : <ChevronDown className="h-2.5 w-2.5" />
            ) : (
              <span className="h-2.5 w-2.5" />
            )}
          </div>
          {canResize && <ResizeHandle columnId={col.id} />}
        </th>
      );
    }

    // Non-sortable columns
    return (
      <th
        key={col.id}
        style={{ width, minWidth: 40 }}
        className={`relative px-2 py-2 text-${align} text-[10px] font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider`}
      >
        {col.label}
        {canResize && <ResizeHandle columnId={col.id} />}
      </th>
    );
  }

  // Helper to get total quantity from executions (opening legs only)
  function getTotalQuantity(executions: any[] | undefined): number {
    if (!executions || executions.length === 0) return 0;
    // Sum up opening executions quantity
    const openingExecs = executions.filter(e => e.open_close_indicator === 'O');
    if (openingExecs.length === 0) {
      // Fallback: if no open_close_indicator, use all buy executions
      const buyExecs = executions.filter(e => e.side === 'BOT');
      return buyExecs.reduce((sum, e) => sum + Math.abs(parseFloat(e.quantity)), 0);
    }
    // Get unique strikes to determine if it's a spread
    const uniqueStrikes = new Set(openingExecs.map(e => e.strike));
    if (uniqueStrikes.size > 1) {
      // It's a spread - take the max leg quantity
      const byStrike: Record<string, number> = {};
      openingExecs.forEach(e => {
        const strike = e.strike || 'STK';
        byStrike[strike] = (byStrike[strike] || 0) + Math.abs(parseFloat(e.quantity));
      });
      return Math.max(...Object.values(byStrike));
    }
    // Single leg - sum all
    return openingExecs.reduce((sum, e) => sum + Math.abs(parseFloat(e.quantity)), 0);
  }


  // Get sorted trades
  function getSortedTrades(): Trade[] {
    if (!sortColumn) return trades;

    return [...trades].sort((a: any, b: any) => {
      let aVal: any;
      let bVal: any;

      const aExecs = tradeExecutions[a.id];
      const bExecs = tradeExecutions[b.id];
      const aAgg = aExecs ? aggregateExecutions(aExecs) : [];
      const bAgg = bExecs ? aggregateExecutions(bExecs) : [];

      switch (sortColumn) {
        case 'status':
          aVal = a.status;
          bVal = b.status;
          break;
        case 'openTime':
          aVal = new Date(a.opened_at).getTime();
          bVal = new Date(b.opened_at).getTime();
          break;
        case 'closeTime':
          aVal = a.closed_at ? new Date(a.closed_at).getTime() : 0;
          bVal = b.closed_at ? new Date(b.closed_at).getTime() : 0;
          break;
        case 'ticker':
          aVal = a.underlying;
          bVal = b.underlying;
          break;
        case 'qty':
          aVal = getTotalQuantity(aExecs);
          bVal = getTotalQuantity(bExecs);
          break;
        case 'strategy':
          aVal = a.strategy_type;
          bVal = b.strategy_type;
          break;
        case 'strike':
          aVal = aAgg.length > 0 ? parseFloat(aAgg[0].strike) : 0;
          bVal = bAgg.length > 0 ? parseFloat(bAgg[0].strike) : 0;
          break;
        case 'expiration':
          aVal = aAgg.length > 0 && aAgg[0].expiration ? new Date(aAgg[0].expiration).getTime() : 0;
          bVal = bAgg.length > 0 && bAgg[0].expiration ? new Date(bAgg[0].expiration).getTime() : 0;
          break;
        case 'dte':
          const aExp = aAgg.length > 0 && aAgg[0].expiration ? new Date(aAgg[0].expiration) : null;
          const bExp = bAgg.length > 0 && bAgg[0].expiration ? new Date(bAgg[0].expiration) : null;
          aVal = aExp ? Math.ceil((aExp.getTime() - new Date().getTime()) / (1000 * 60 * 60 * 24)) : -9999;
          bVal = bExp ? Math.ceil((bExp.getTime() - new Date().getTime()) / (1000 * 60 * 60 * 24)) : -9999;
          break;
        case 'pnl':
          aVal = parseFloat(a.realized_pnl) || 0;
          bVal = parseFloat(b.realized_pnl) || 0;
          break;
        case 'delta':
          aVal = parseFloat(a.delta_open) || 0;
          bVal = parseFloat(b.delta_open) || 0;
          break;
        case 'theta':
          aVal = parseFloat(a.theta_open) || 0;
          bVal = parseFloat(b.theta_open) || 0;
          break;
        case 'iv':
          aVal = parseFloat(a.iv_open) || 0;
          bVal = parseFloat(b.iv_open) || 0;
          break;
        default:
          return 0;
      }

      if (aVal < bVal) return sortDirection === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortDirection === 'asc' ? 1 : -1;
      return 0;
    });
  }

  // Render column cell - takes trade data and computed values
  function renderColumnCell(
    col: ColumnConfig,
    trade: any,
    computed: {
      executions: any[] | undefined;
      strikes: string;
      expiration: Date | null;
      dte: number | null;
      qty: number | string;
      multiplier: number;
      totalCommission: number;
    }
  ) {
    if (!col.visible) return null;

    const { executions, strikes, expiration, dte, qty, multiplier, totalCommission } = computed;
    const align = rightAlignedColumns.has(col.id) ? 'text-right' : '';
    const width = columnWidths[col.id] || DEFAULT_COLUMN_WIDTHS[col.id] || 100;
    const cellStyle = { width, minWidth: 40, maxWidth: width };
    const cellClass = "px-2 py-1.5 whitespace-nowrap text-xs text-gray-900 dark:text-white overflow-hidden";

    switch (col.id) {
      case 'select':
        return (
          <td key={col.id} style={{ width: 40, minWidth: 40 }} className="px-2 py-1.5 whitespace-nowrap text-center">
            <input
              type="checkbox"
              checked={selectedTradeIds.has(trade.id)}
              onChange={() => toggleTradeSelection(trade.id)}
              className="rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-blue-500 h-3 w-3"
            />
          </td>
        );
      case 'expand':
        return (
          <td key={col.id} style={{ width: 32, minWidth: 32 }} className="px-2 py-1.5 whitespace-nowrap">
            <button
              onClick={() => toggleTradeExpansion(trade.id)}
              className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
            >
              {expandedTrades.has(trade.id) ? (
                <ChevronDown className="h-3 w-3" />
              ) : (
                <ChevronRight className="h-3 w-3" />
              )}
            </button>
          </td>
        );
      case 'status':
        return (
          <td key={col.id} style={cellStyle} className="px-2 py-1.5 whitespace-nowrap overflow-hidden">
            <span className={`inline-flex rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${
              trade.status === 'CLOSED'
                ? 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200'
                : trade.status === 'EXPIRED'
                ? 'bg-orange-100 dark:bg-orange-900/50 text-orange-800 dark:text-orange-200'
                : 'bg-blue-100 dark:bg-blue-900/50 text-blue-800 dark:text-blue-200'
            }`}>
              {trade.status}
            </span>
          </td>
        );
      case 'openTime':
        return (
          <td key={col.id} style={cellStyle} className={`${cellClass} text-ellipsis`}>
            {formatDateTime(trade.opened_at)}
          </td>
        );
      case 'closeTime':
        return (
          <td key={col.id} style={cellStyle} className={`${cellClass} text-ellipsis`}>
            {trade.closed_at ? formatDateTime(trade.closed_at) : '-'}
          </td>
        );
      case 'ticker':
        return (
          <td key={col.id} style={cellStyle} className={`${cellClass} font-medium text-ellipsis`}>
            {trade.underlying}
          </td>
        );
      case 'qty':
        return (
          <td key={col.id} style={cellStyle} className={`${cellClass} ${align}`}>
            {qty}
          </td>
        );
      case 'strategy':
        return (
          <td key={col.id} style={cellStyle} className={`${cellClass} text-ellipsis`}>
            {formatStrategyName(trade, executions)}
          </td>
        );
      case 'strike':
        return (
          <td key={col.id} style={cellStyle} className={`${cellClass} text-ellipsis`}>
            {strikes}
          </td>
        );
      case 'expiration':
        return (
          <td key={col.id} style={cellStyle} className={`${cellClass} text-ellipsis`}>
            {expiration ? formatDate(expiration.toISOString()) : '-'}
          </td>
        );
      case 'dte':
        return (
          <td key={col.id} style={cellStyle} className={`${cellClass} ${align}`}>
            {dte !== null ? dte : '-'}
          </td>
        );
      case 'openPrice':
        return (
          <td key={col.id} style={cellStyle} className={`${cellClass} ${align}`}>
            {(() => {
              if (!executions || executions.length === 0) return '-';
              const pairs = pairTransactions(executions);
              if (pairs.length === 0) return '-';
              const totalOpenValue = pairs.reduce((sum, p) => sum + (p.openValue || 0), 0);
              const totalQty = Math.max(...pairs.map(p => p.quantity));
              const pricePerContract = totalQty > 0 ? totalOpenValue / totalQty / multiplier : 0;
              return formatPriceSmart(pricePerContract);
            })()}
          </td>
        );
      case 'closePrice':
        return (
          <td key={col.id} style={cellStyle} className={`${cellClass} ${align}`}>
            {(() => {
              if (trade.status !== 'CLOSED' || !executions || executions.length === 0) return '-';
              const pairs = pairTransactions(executions);
              if (pairs.length === 0) return '-';
              const totalCloseValue = pairs.reduce((sum, p) => sum + (p.closeValue || 0), 0);
              const totalQty = Math.max(...pairs.map(p => p.quantity));
              const pricePerContract = totalQty > 0 ? totalCloseValue / totalQty / multiplier : 0;
              return formatPriceSmart(pricePerContract);
            })()}
          </td>
        );
      case 'marketValue':
        return (
          <td key={col.id} style={cellStyle} className={`${cellClass} ${align}`}>
            {(() => {
              if (!executions || executions.length === 0) return '-';
              const pairs = pairTransactions(executions);
              if (pairs.length === 0) return '-';
              const totalOpenValue = pairs.reduce((sum, p) => sum + (p.openValue || 0), 0);
              const totalOpenCommission = pairs.reduce((sum, p) => sum + (p.openCommission || 0), 0);
              return formatCurrency(totalOpenValue - totalOpenCommission);
            })()}
          </td>
        );
      case 'commission':
        return (
          <td key={col.id} style={cellStyle} className={`${cellClass} ${align}`}>
            ${totalCommission.toFixed(2)}
          </td>
        );
      case 'pnl':
        return (
          <td key={col.id} style={cellStyle} className={`px-2 py-1.5 whitespace-nowrap text-xs overflow-hidden ${align}`}>
            {(() => {
              if (executions && executions.length > 0) {
                const pairs = pairTransactions(executions);
                const totalNetPnl = pairs.reduce((sum, p) => sum + (p.netPnl || 0), 0);
                if (totalNetPnl !== 0 || trade.status === 'CLOSED') {
                  return (
                    <span className={getPnlColor(totalNetPnl)}>
                      {formatCurrency(totalNetPnl)}
                    </span>
                  );
                }
              }
              const pnl = parseFloat(trade.realized_pnl) || 0;
              return (
                <span className={getPnlColor(pnl)}>
                  {trade.realized_pnl ? formatCurrency(pnl) : '-'}
                </span>
              );
            })()}
          </td>
        );
      case 'pop':
        return (
          <td key={col.id} style={cellStyle} className={`${cellClass} ${align}`}>
            {trade.pop_open !== null && trade.pop_open !== undefined ? `${Number(trade.pop_open).toFixed(0)}%` : '-'}
          </td>
        );
      case 'maxProfit':
        return (
          <td key={col.id} style={cellStyle} className={`px-2 py-1.5 whitespace-nowrap text-xs text-green-600 dark:text-green-400 overflow-hidden ${align}`}>
            {trade.max_profit !== null && trade.max_profit !== undefined ? formatCurrency(Number(trade.max_profit)) : '-'}
          </td>
        );
      case 'maxRisk':
        return (
          <td key={col.id} style={cellStyle} className={`px-2 py-1.5 whitespace-nowrap text-xs text-red-600 dark:text-red-400 overflow-hidden ${align}`}>
            {trade.max_risk !== null && trade.max_risk !== undefined ? formatCurrency(Number(trade.max_risk)) : '-'}
          </td>
        );
      case 'delta':
        return (
          <td key={col.id} style={cellStyle} className={`${cellClass} ${align}`}>
            {trade.delta_open !== null && trade.delta_open !== undefined ? (Number(trade.delta_open) >= 0 ? '+' : '') + Number(trade.delta_open).toFixed(2) : '-'}
          </td>
        );
      case 'gamma':
        return (
          <td key={col.id} style={cellStyle} className={`${cellClass} ${align}`}>
            {trade.gamma_open !== null && trade.gamma_open !== undefined ? Number(trade.gamma_open).toFixed(4) : '-'}
          </td>
        );
      case 'theta':
        return (
          <td key={col.id} style={cellStyle} className={`${cellClass} ${align}`}>
            {trade.theta_open !== null && trade.theta_open !== undefined ? formatCurrency(Number(trade.theta_open)) : '-'}
          </td>
        );
      case 'vega':
        return (
          <td key={col.id} style={cellStyle} className={`${cellClass} ${align}`}>
            {trade.vega_open !== null && trade.vega_open !== undefined ? formatCurrency(Number(trade.vega_open)) : '-'}
          </td>
        );
      case 'iv':
        return (
          <td key={col.id} style={cellStyle} className={`${cellClass} ${align}`}>
            {trade.iv_open !== null && trade.iv_open !== undefined ? `${(Number(trade.iv_open) * 100).toFixed(1)}%` : '-'}
          </td>
        );
      case 'ivRank':
        return (
          <td key={col.id} style={cellStyle} className={`${cellClass} ${align}`}>
            {trade.iv_rank_52w_open !== null && trade.iv_rank_52w_open !== undefined ? `${Number(trade.iv_rank_52w_open).toFixed(0)}%` : '-'}
          </td>
        );
      case 'daysHeld':
        return (
          <td key={col.id} style={cellStyle} className={`${cellClass} ${align}`}>
            {trade.opened_at ? Math.floor((new Date().getTime() - new Date(trade.opened_at).getTime()) / (1000 * 60 * 60 * 24)) : '-'}
          </td>
        );
      case 'pnlPercent':
        return (
          <td key={col.id} style={cellStyle} className={`px-2 py-1.5 whitespace-nowrap text-xs overflow-hidden ${align}`}>
            {trade.pnl_percent !== null && trade.pnl_percent !== undefined ? (
              <span className={getPnlColor(Number(trade.pnl_percent))}>
                {Number(trade.pnl_percent).toFixed(0)}%
              </span>
            ) : '-'}
          </td>
        );
      case 'tags':
        return (
          <td key={col.id} style={cellStyle} className="px-2 py-1.5 whitespace-nowrap overflow-visible">
            <TagSelector
              tradeId={trade.id}
              currentTags={trade.tag_list || []}
              onTagsChange={(newTags) => {
                // Update the trade in local state with new tags
                setTrades(prevTrades =>
                  prevTrades.map(t =>
                    t.id === trade.id ? { ...t, tag_list: newTags } : t
                  )
                );
              }}
            />
          </td>
        );
      default:
        return null;
    }
  }

  async function fetchTrades() {
    try {
      setLoading(true);
      const params: any = { limit: 1000 };
      if (filters.strategy) params.strategy_type = filters.strategy;
      if (filters.underlying_symbol) params.underlying = filters.underlying_symbol.toUpperCase();
      if (filters.status) params.status = filters.status;

      // Apply date range filter
      const dateRange = getDateRange(filters.dateRange);
      if (dateRange.start) params.start_date = dateRange.start;
      if (dateRange.end) params.end_date = dateRange.end;

      const data: any = await api.trades.list(params);
      const fetchedTrades = data.trades || [];
      setTrades(fetchedTrades);

      // Fetch executions for all trades to show strike/expiration in table
      const executionsPromises = fetchedTrades.map(async (trade: Trade) => {
        try {
          const response = await fetch(`http://localhost:8000/api/v1/trades/${trade.id}/executions`);
          const execData = await response.json();
          return { tradeId: trade.id, executions: execData.executions };
        } catch {
          return { tradeId: trade.id, executions: [] };
        }
      });

      const executionsResults = await Promise.all(executionsPromises);
      const newExecutions: Record<number, any[]> = {};
      executionsResults.forEach(({ tradeId, executions }) => {
        newExecutions[tradeId] = executions;
      });
      setTradeExecutions(newExecutions);
    } catch (error) {
      console.error('Error fetching trades:', error);
      setTrades([]);
    } finally {
      setLoading(false);
    }
  }

  // Helper function to determine action using IBKR's open_close_indicator
  function getActionLabel(exec: any) {
    const isBuy = exec.side === 'BOT';
    const isOpen = exec.open_close_indicator === 'O';

    if (isBuy && isOpen) return 'BUY TO OPEN';
    if (isBuy && !isOpen) return 'BUY TO CLOSE';
    if (!isBuy && isOpen) return 'SELL TO OPEN';
    return 'SELL TO CLOSE';
  }

  // New function to pair opening and closing transactions
  function pairTransactions(executions: any[]) {
    // Filter out fractional quantity executions (< 1 share) for display
    // These are typically IBKR price improvement rebates
    const displayExecutions = executions.filter((exec) => {
      const qty = parseFloat(exec.quantity);
      return qty >= 1;
    });

    // Group by strike + option_type + expiration
    const groups: Record<string, any[]> = {};

    displayExecutions.forEach((exec) => {
      const expDate = exec.expiration ? new Date(exec.expiration).toISOString().split('T')[0] : 'no-exp';
      const key = `${exec.strike}_${exec.option_type}_${expDate}`;
      if (!groups[key]) {
        groups[key] = [];
      }
      groups[key].push(exec);
    });

    const pairedResults: any[] = [];

    Object.entries(groups).forEach(([key, execs]) => {
      // Separate opening and closing executions
      // First try to use open_close_indicator if available
      let openingExecs = execs.filter(e => e.open_close_indicator === 'O');
      let closingExecs = execs.filter(e => e.open_close_indicator === 'C');

      // If open_close_indicator is not set, infer from execution order and side
      if (openingExecs.length === 0 && closingExecs.length === 0) {
        // Sort by execution time
        const sortedExecs = [...execs].sort((a, b) =>
          new Date(a.execution_time).getTime() - new Date(b.execution_time).getTime()
        );

        // Track cumulative position to determine open vs close
        let position = 0;
        const inferredOpening: any[] = [];
        const inferredClosing: any[] = [];

        for (const exec of sortedExecs) {
          const delta = exec.side === 'BOT' ? exec.quantity : -exec.quantity;

          if (position === 0) {
            // No position - this is opening
            inferredOpening.push(exec);
          } else if ((position > 0 && delta < 0) || (position < 0 && delta > 0)) {
            // Reducing position - this is closing
            inferredClosing.push(exec);
          } else {
            // Increasing position - this is opening (adding to position)
            inferredOpening.push(exec);
          }
          position += delta;
        }

        openingExecs = inferredOpening;
        closingExecs = inferredClosing;
      }

      // Determine if this is a long or short position
      // Long: BTO (open with buy) + STC (close with sell)
      // Short: STO (open with sell) + BTC (close with buy)
      const isLongPosition = openingExecs.length > 0 ? openingExecs.some(e => e.side === 'BOT') : false;

      // Calculate opening details
      const openingBuys = openingExecs.filter(e => e.side === 'BOT');
      const openingSells = openingExecs.filter(e => e.side === 'SLD');

      const openingQty = openingExecs.reduce((sum, e) => sum + e.quantity, 0);
      const openingWeightedPrice = openingQty > 0
        ? openingExecs.reduce((sum, e) => sum + parseFloat(e.price) * e.quantity, 0) / openingQty
        : 0;

      // Calculate closing details
      const closingQty = closingExecs.reduce((sum, e) => sum + e.quantity, 0);
      const closingWeightedPrice = closingQty > 0
        ? closingExecs.reduce((sum, e) => sum + parseFloat(e.price) * e.quantity, 0) / closingQty
        : 0;

      // Get dates
      const openDate = openingExecs.length > 0
        ? new Date(Math.min(...openingExecs.map(e => new Date(e.execution_time).getTime())))
        : null;
      const closeDate = closingExecs.length > 0
        ? new Date(Math.min(...closingExecs.map(e => new Date(e.execution_time).getTime())))
        : null;

      // Calculate commissions
      const openCommission = openingExecs.reduce((sum, e) => sum + parseFloat(e.commission), 0);
      const closeCommission = closingExecs.reduce((sum, e) => sum + parseFloat(e.commission), 0);

      // Calculate values and P&L
      // Stock trades have multiplier=1 (no 100x), even if stored incorrectly as 100
      const isStock = execs[0].security_type === 'STK';
      const multiplier = isStock ? 1 : (execs[0].multiplier || 100);

      // Opening value: for long positions (BTO) it's a debit (positive), for short (STO) it's a credit (negative)
      const openValue = isLongPosition
        ? openingQty * openingWeightedPrice * multiplier
        : -(openingQty * openingWeightedPrice * multiplier);

      // Closing value: for long positions (STC) it's a credit (negative of closing price), for short (BTC) it's a debit (positive of closing price)
      const closeValue = closingQty > 0
        ? (isLongPosition
            ? closingQty * closingWeightedPrice * multiplier
            : -(closingQty * closingWeightedPrice * multiplier))
        : 0;

      // Net P&L = closeValue - openValue - total commissions
      // For long: (sell price - buy price) * qty * multiplier - commissions
      // For short: (sell price - buy price) * qty * multiplier - commissions
      const netPnl = closingQty > 0
        ? (isLongPosition
            ? (closingWeightedPrice - openingWeightedPrice) * Math.min(openingQty, closingQty) * multiplier - openCommission - closeCommission
            : (openingWeightedPrice - closingWeightedPrice) * Math.min(openingQty, closingQty) * multiplier - openCommission - closeCommission)
        : 0;

      // Determine action label
      let action = '';
      if (isLongPosition) {
        action = execs[0].option_type === 'C' ? 'Long Call' : 'Long Put';
      } else {
        action = execs[0].option_type === 'C' ? 'Short Call' : 'Short Put';
      }

      pairedResults.push({
        dateOpened: openDate,
        dateClosed: closeDate,
        action,
        quantity: Math.max(openingQty, closingQty), // Show the larger of opening or closing qty
        type: execs[0].option_type === 'C' ? 'Call' : 'Put',
        strike: execs[0].strike,
        expiration: execs[0].expiration,
        // For short positions, show negative open price (credit received)
        openPrice: openingWeightedPrice ? (isLongPosition ? openingWeightedPrice : -openingWeightedPrice) : null,
        closePrice: closingQty > 0 ? closingWeightedPrice : null,
        openValue,
        closeValue: closingQty > 0 ? closeValue : null,
        openCommission,
        closeCommission: closingQty > 0 ? closeCommission : null,
        totalCommission: openCommission + closeCommission,
        netPnl: closingQty > 0 ? netPnl : null,
        isOpen: closingQty === 0,
      });
    });

    // Sort by strike
    return pairedResults.sort((a, b) => parseFloat(a.strike) - parseFloat(b.strike));
  }

  // Helper function to aggregate executions - show separate rows for each action type
  function aggregateExecutions(executions: any[]) {
    // Filter out fractional quantity executions (< 1 share) for display
    // These are typically IBKR price improvement rebates
    const displayExecutions = executions.filter((exec) => {
      const qty = parseFloat(exec.quantity);
      return qty >= 1;
    });

    // Group by strike/type/expiration/action (keep BTO and STO separate)
    const actionGroups: Record<string, any[]> = {};

    displayExecutions.forEach((exec) => {
      // Use a more precise key that includes expiration date and action
      const expDate = exec.expiration ? new Date(exec.expiration).toISOString().split('T')[0] : 'no-exp';
      const action = getActionLabel(exec);
      const key = `${exec.strike}_${exec.option_type}_${expDate}_${action}`;
      if (!actionGroups[key]) {
        actionGroups[key] = [];
      }
      actionGroups[key].push(exec);
    });

    // Create separate row for each action type
    return Object.entries(actionGroups)
      .map(([key, execs]) => {
        const action = getActionLabel(execs[0]);
        const isBuy = action.includes('BUY');

        const totalQty = execs.reduce((sum, e) => sum + e.quantity, 0);

        // Calculate weighted average price
        const avgPrice = execs.reduce((sum, e) => sum + parseFloat(e.price) * e.quantity, 0) / totalQty;

        // Calculate values and commissions
        // BUY: value is positive (debit), SELL: value is negative (credit)
        const totalValue = isBuy
          ? execs.reduce((sum, e) => sum + Math.abs(parseFloat(e.net_amount)), 0)
          : execs.reduce((sum, e) => sum + (-Math.abs(parseFloat(e.net_amount))), 0);

        const totalCommission = execs.reduce((sum, e) => sum + parseFloat(e.commission), 0);

        // Shorten action labels
        const shortAction = action.replace('BUY TO OPEN', 'BTO')
                                  .replace('SELL TO OPEN', 'STO')
                                  .replace('BUY TO CLOSE', 'BTC')
                                  .replace('SELL TO CLOSE', 'STC');

        // Get earliest execution time for this group
        const executionTime = execs.reduce((earliest, e) => {
          const eTime = new Date(e.execution_time).getTime();
          return eTime < earliest ? eTime : earliest;
        }, new Date(execs[0].execution_time).getTime());

        return {
          action: shortAction,
          executionTime: new Date(executionTime).toISOString(),
          strike: execs[0].strike,
          option_type: execs[0].option_type,
          expiration: execs[0].expiration,
          security_type: execs[0].security_type,
          totalQuantity: totalQty,
          avgPrice: avgPrice,
          totalValue: totalValue,
          totalCommission: totalCommission,
          count: execs.length,
          executions: execs,
        };
      })
      .sort((a, b) => {
        // Sort by strike first, then by action (BTO/BTC before STO/STC)
        const strikeDiff = parseFloat(a.strike) - parseFloat(b.strike);
        if (strikeDiff !== 0) return strikeDiff;
        // BTO/BTC (contains BUY) should come before STO/STC
        const aIsBuy = a.action.includes('BTO') || a.action.includes('BTC');
        const bIsBuy = b.action.includes('BTO') || b.action.includes('BTC');
        if (aIsBuy && !bIsBuy) return -1;
        if (!aIsBuy && bIsBuy) return 1;
        return 0;
      });
  }

  // Helper function to format strategy name - use backend classification
  function formatStrategyName(trade: any, executions?: any[]) {
    // Check for assignment (stock executions after option executions)
    if (executions && executions.length > 0) {
      const hasStock = executions.some(e => e.security_type === 'STK');
      const hasOptions = executions.some(e => e.security_type === 'OPT');
      if (hasStock && hasOptions) {
        return 'Assignment';
      }
    }

    // Use backend's strategy classification
    return trade.strategy_type || 'Unknown';
  }

  async function toggleTradeExpansion(tradeId: number) {
    const newExpanded = new Set(expandedTrades);

    if (expandedTrades.has(tradeId)) {
      newExpanded.delete(tradeId);
      setExpandedTrades(newExpanded);
    } else {
      newExpanded.add(tradeId);
      setExpandedTrades(newExpanded);

      // Fetch executions if not already loaded
      if (!tradeExecutions[tradeId]) {
        try {
          const response = await fetch(`http://localhost:8000/api/v1/trades/${tradeId}/executions`);
          const data = await response.json();
          setTradeExecutions(prev => ({ ...prev, [tradeId]: data.executions }));
        } catch (error) {
          console.error('Error fetching executions:', error);
        }
      }

      // Fetch analytics if not already loaded
      if (tradeAnalytics[tradeId] === undefined) {
        try {
          const analytics = await api.tradeAnalytics.get(tradeId) as TradeAnalyticsType;
          setTradeAnalytics(prev => ({ ...prev, [tradeId]: analytics }));
        } catch (error) {
          console.error('Error fetching analytics:', error);
          setTradeAnalytics(prev => ({ ...prev, [tradeId]: null }));
        }
      }
    }
  }

  useEffect(() => {
    fetchTrades();
  }, [filters]);

  // Toggle single trade selection
  function toggleTradeSelection(tradeId: number) {
    const newSelected = new Set(selectedTradeIds);
    if (newSelected.has(tradeId)) {
      newSelected.delete(tradeId);
    } else {
      newSelected.add(tradeId);
    }
    setSelectedTradeIds(newSelected);
    setMergeError(null);
  }

  // Toggle all trades selection
  function toggleSelectAll() {
    if (selectedTradeIds.size === trades.length) {
      setSelectedTradeIds(new Set());
    } else {
      setSelectedTradeIds(new Set(trades.map((t: any) => t.id)));
    }
    setMergeError(null);
  }

  // Merge selected trades
  async function handleMergeTrades() {
    if (selectedTradeIds.size < 2) {
      setMergeError('Select at least 2 trades to merge');
      return;
    }

    // Check if all selected trades have the same underlying
    const selectedTrades = trades.filter((t: any) => selectedTradeIds.has(t.id));
    const underlyings = new Set(selectedTrades.map((t: any) => t.underlying));
    if (underlyings.size > 1) {
      setMergeError(`Cannot merge trades with different underlyings: ${[...underlyings].join(', ')}`);
      return;
    }

    setMerging(true);
    setMergeError(null);

    try {
      await api.trades.merge([...selectedTradeIds]);
      setSelectedTradeIds(new Set());
      await fetchTrades(); // Refresh the list
    } catch (error) {
      setMergeError(error instanceof Error ? error.message : 'Failed to merge trades');
    } finally {
      setMerging(false);
    }
  }

  const totalPnl = trades
    .filter((t: any) => t.realized_pnl)
    .reduce((sum: number, trade: any) => sum + (parseFloat(trade.realized_pnl) || 0), 0);

  const closedTrades = trades.filter((t: any) => t.status === 'CLOSED').length;
  const openTrades = trades.filter((t: any) => t.status === 'OPEN').length;

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-100 dark:bg-gray-900 transition-colors">
        <Header title="Trades" subtitle="View your complete trade history" />
        <div className="p-6">
          <div className="animate-pulse">
            <div className="h-96 rounded-lg bg-gray-200 dark:bg-gray-700" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900 transition-colors">
      <Header title="Trades" subtitle="View your complete trade history" />

      <div className="p-6 space-y-6">
        {/* Date Range Quick Filters */}
        <div className="flex items-center gap-2">
          <Calendar className="h-4 w-4 text-gray-500 dark:text-gray-400" />
          <div className="flex rounded-lg border border-gray-300 dark:border-gray-600 overflow-hidden">
            {(['all', 'day', 'prevday', 'week', 'month', 'year', 'custom'] as const).map((range) => (
              <button
                key={range}
                onClick={() => {
                  if (range === 'custom') {
                    setShowCustomDatePicker(!showCustomDatePicker);
                    setFilters({ ...filters, dateRange: 'custom' });
                  } else {
                    setShowCustomDatePicker(false);
                    setFilters({ ...filters, dateRange: range, startDate: '', endDate: '' });
                  }
                }}
                className={`px-3 py-1.5 text-sm font-medium transition-colors ${
                  filters.dateRange === range
                    ? 'bg-blue-600 text-white'
                    : 'bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'
                } ${range !== 'all' ? 'border-l border-gray-300 dark:border-gray-600' : ''}`}
              >
                {range === 'all' ? 'All' : range === 'prevday' ? 'Prev Day' : range.charAt(0).toUpperCase() + range.slice(1)}
              </button>
            ))}
          </div>

          {/* Custom Date Range Picker */}
          {showCustomDatePicker && (
            <div className="flex items-center gap-2 ml-2">
              <input
                type="date"
                value={filters.startDate}
                onChange={(e) => setFilters({ ...filters, startDate: e.target.value, dateRange: 'custom' })}
                className="px-2 py-1.5 text-sm rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              />
              <span className="text-gray-500 dark:text-gray-400">to</span>
              <input
                type="date"
                value={filters.endDate}
                onChange={(e) => setFilters({ ...filters, endDate: e.target.value, dateRange: 'custom' })}
                className="px-2 py-1.5 text-sm rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              />
            </div>
          )}

          {/* Timezone indicator */}
          <div className="flex items-center gap-1 ml-4 text-xs text-gray-500 dark:text-gray-400">
            <span>Times in {getTimezoneAbbr()}</span>
          </div>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-4">
          <select
            value={filters.strategy}
            onChange={(e) =>
              setFilters({ ...filters, strategy: e.target.value })
            }
            className="block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
          >
            <option value="">All Strategies</option>
            <option value="iron_condor">Iron Condor</option>
            <option value="credit_spread">Credit Spread</option>
            <option value="covered_call">Covered Call</option>
            <option value="naked_put">Naked Put</option>
            <option value="long_call">Long Call</option>
            <option value="long_put">Long Put</option>
          </select>

          <input
            type="text"
            value={underlyingInput}
            onChange={(e) => setUnderlyingInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                setFilters({ ...filters, underlying_symbol: underlyingInput });
              }
            }}
            onBlur={() => setFilters({ ...filters, underlying_symbol: underlyingInput })}
            placeholder="Underlying (press Enter)"
            className="block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm placeholder-gray-400 dark:placeholder-gray-500"
          />

          <select
            value={filters.status}
            onChange={(e) =>
              setFilters({ ...filters, status: e.target.value })
            }
            className="block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
          >
            <option value="">All Status</option>
            <option value="OPEN">Open</option>
            <option value="CLOSED">Closed</option>
          </select>

          {/* Merge Button */}
          <button
            onClick={handleMergeTrades}
            disabled={selectedTradeIds.size < 2 || merging}
            className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
          >
            <Merge className="h-4 w-4" />
            {merging ? 'Merging...' : `Merge${selectedTradeIds.size > 0 ? ` (${selectedTradeIds.size})` : ''}`}
          </button>

          {/* Column Configuration */}
          <TableColumnConfig
            columns={columns}
            onChange={setColumns}
            storageKey="trades-table-columns"
          />
        </div>

        {/* Merge Error */}
        {mergeError && (
          <div className="flex items-center gap-2 p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg text-red-800 dark:text-red-200 text-sm">
            <AlertCircle className="h-5 w-5 flex-shrink-0" />
            {mergeError}
          </div>
        )}

        {/* Selection Info */}
        {selectedTradeIds.size > 0 && (
          <div className="flex items-center gap-4 p-3 bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800 rounded-lg text-blue-800 dark:text-blue-200 text-sm">
            <span>{selectedTradeIds.size} trade{selectedTradeIds.size !== 1 ? 's' : ''} selected</span>
            <button
              onClick={() => setSelectedTradeIds(new Set())}
              className="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 underline"
            >
              Clear selection
            </button>
          </div>
        )}

        {/* Summary Cards */}
        <div className="grid gap-6 md:grid-cols-4">
          <div className="rounded-lg bg-white dark:bg-gray-800 p-6 shadow transition-colors">
            <h3 className="text-sm font-medium text-gray-600 dark:text-gray-400">Total Trades</h3>
            <p className="mt-2 text-3xl font-bold text-gray-900 dark:text-white">
              {trades.length}
            </p>
          </div>
          <div className="rounded-lg bg-white dark:bg-gray-800 p-6 shadow transition-colors">
            <h3 className="text-sm font-medium text-gray-600 dark:text-gray-400">Open Trades</h3>
            <p className="mt-2 text-3xl font-bold text-blue-600 dark:text-blue-400">
              {openTrades}
            </p>
          </div>
          <div className="rounded-lg bg-white dark:bg-gray-800 p-6 shadow transition-colors">
            <h3 className="text-sm font-medium text-gray-600 dark:text-gray-400">Closed Trades</h3>
            <p className="mt-2 text-3xl font-bold text-gray-600 dark:text-gray-400">
              {closedTrades}
            </p>
          </div>
          <div className="rounded-lg bg-white dark:bg-gray-800 p-6 shadow transition-colors">
            <h3 className="text-sm font-medium text-gray-600 dark:text-gray-400">Total P&L</h3>
            <p className={`mt-2 text-3xl font-bold ${getPnlColor(totalPnl)}`}>
              {formatCurrency(totalPnl)}
            </p>
          </div>
        </div>

        {/* Trades Table */}
        <div className="rounded-lg bg-white dark:bg-gray-800 shadow overflow-hidden transition-colors">
          <div className="overflow-x-auto max-h-[calc(100vh-300px)] relative">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700" style={{ tableLayout: 'fixed' }}>
              <thead className="bg-gray-50 dark:bg-gray-700 sticky top-0 z-10">
                <tr>
                  {columns.map(renderColumnHeader)}
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                {trades.length === 0 ? (
                  <tr>
                    <td colSpan={columns.filter(c => c.visible).length} className="px-6 py-12 text-center text-gray-500 dark:text-gray-400">
                      No trades found matching your filters.
                    </td>
                  </tr>
                ) : (
                  getSortedTrades().map((trade: any) => {
                    const executions = tradeExecutions[trade.id];
                    const aggregated = executions ? aggregateExecutions(executions) : [];

                    // Calculate strikes for display (e.g., "250/270" or "12.5/15") - only when executions loaded
                    const strikes = aggregated.length > 0
                      ? [...new Set(aggregated.map(g => parseFloat(g.strike)))]
                          .sort((a, b) => a - b)
                          .map(s => formatNumberSmart(s))
                          .join('/')
                      : '-';

                    // Get expiration - only when executions loaded
                    const expiration = aggregated.length > 0 && aggregated[0].expiration
                      ? new Date(aggregated[0].expiration)
                      : null;

                    // Calculate DTE (Days to Expiration)
                    const dte = expiration
                      ? Math.ceil((expiration.getTime() - new Date().getTime()) / (1000 * 60 * 60 * 24))
                      : null;

                    // Calculate quantity from executions
                    const qty = getTotalQuantity(executions) || trade.num_legs || '-';
                    // Stock trades don't have a 100x multiplier
                    const isStockTrade = trade.strategy_type?.toLowerCase().includes('stock');
                    const multiplier = isStockTrade ? 1 : 100;
                    const totalCommission = parseFloat(trade.total_commission) || 0;

                    // Computed values for dynamic column rendering
                    const computed = { executions, strikes, expiration, dte, qty, multiplier, totalCommission };

                    return (
                    <React.Fragment key={trade.id}>
                      <tr className={`hover:bg-gray-50 dark:hover:bg-gray-700 ${selectedTradeIds.has(trade.id) ? 'bg-blue-50 dark:bg-blue-900/30' : ''}`}>
                        {columns.map(col => renderColumnCell(col, trade, computed))}
                      </tr>
                      {expandedTrades.has(trade.id) && (
                        <tr key={`${trade.id}-executions`}>
                          <td colSpan={columns.filter(c => c.visible).length} className="px-6 py-4 bg-gray-50 dark:bg-gray-700/50">
                            {/* Data Source Indicator */}
                            <div className="flex items-center gap-2 mb-3">
                              <span className="px-2 py-0.5 text-xs font-medium bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300 rounded">
                                Source: IBKR
                              </span>
                              {tradeExecutions[trade.id]?.[0]?.exec_id && (
                                <span className="text-xs text-gray-500 dark:text-gray-400">
                                  Exec ID: {tradeExecutions[trade.id][0].exec_id.substring(0, 20)}...
                                </span>
                              )}
                            </div>
                            {tradeExecutions[trade.id] ? (
                              <table className="min-w-full">
                                <thead>
                                  <tr className="border-b border-gray-300 dark:border-gray-600">
                                    <th className="px-3 py-2 text-left text-xs font-semibold text-gray-700 dark:text-gray-300">Date Opened</th>
                                    <th className="px-3 py-2 text-left text-xs font-semibold text-gray-700 dark:text-gray-300">Date Closed</th>
                                    <th className="px-3 py-2 text-left text-xs font-semibold text-gray-700 dark:text-gray-300">Action</th>
                                    <th className="px-3 py-2 text-left text-xs font-semibold text-gray-700 dark:text-gray-300">Qty</th>
                                    <th className="px-3 py-2 text-left text-xs font-semibold text-gray-700 dark:text-gray-300">Type</th>
                                    <th className="px-3 py-2 text-left text-xs font-semibold text-gray-700 dark:text-gray-300">Strike</th>
                                    <th className="px-3 py-2 text-left text-xs font-semibold text-gray-700 dark:text-gray-300">Expiration</th>
                                    <th className="px-3 py-2 text-right text-xs font-semibold text-gray-700 dark:text-gray-300">Open Price</th>
                                    <th className="px-3 py-2 text-right text-xs font-semibold text-gray-700 dark:text-gray-300">Close Price</th>
                                    <th className="px-3 py-2 text-right text-xs font-semibold text-gray-700 dark:text-gray-300">Commission</th>
                                    <th className="px-3 py-2 text-right text-xs font-semibold text-gray-700 dark:text-gray-300">Net P&L</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {pairTransactions(tradeExecutions[trade.id]).map((pair: any, idx: number) => (
                                    <tr key={idx} className="border-b border-gray-200 dark:border-gray-600">
                                      <td className="px-3 py-2 text-sm text-gray-900 dark:text-white">
                                        {pair.dateOpened ? formatDate(pair.dateOpened.toISOString()) : '-'}
                                      </td>
                                      <td className="px-3 py-2 text-sm text-gray-900 dark:text-white">
                                        {pair.dateClosed ? formatDate(pair.dateClosed.toISOString()) :
                                          <span className="text-blue-600 dark:text-blue-400 font-semibold">OPEN</span>}
                                      </td>
                                      <td className="px-3 py-2 text-sm">
                                        <span className={`font-semibold ${pair.action.includes('Long') ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400'}`}>
                                          {pair.action.includes('Long') ? '+' : '-'} {pair.action}
                                        </span>
                                      </td>
                                      <td className="px-3 py-2 text-sm font-medium text-gray-900 dark:text-white">{pair.quantity}</td>
                                      <td className="px-3 py-2 text-sm text-gray-900 dark:text-white">{pair.type}</td>
                                      <td className="px-3 py-2 text-sm font-medium text-gray-900 dark:text-white">${formatNumberSmart(parseFloat(pair.strike))}</td>
                                      <td className="px-3 py-2 text-sm text-gray-900 dark:text-white">{formatDate(pair.expiration)}</td>
                                      <td className="px-3 py-2 text-sm font-medium text-gray-900 dark:text-white text-right">
                                        {pair.openPrice !== null ? formatPriceSmart(pair.openPrice) : '-'}
                                      </td>
                                      <td className="px-3 py-2 text-sm font-medium text-gray-900 dark:text-white text-right">
                                        {pair.closePrice !== null ? formatPriceSmart(pair.closePrice) : '-'}
                                      </td>
                                      <td className="px-3 py-2 text-sm text-gray-900 dark:text-white text-right">
                                        ${pair.totalCommission.toFixed(2)}
                                      </td>
                                      <td className="px-3 py-2 text-sm font-semibold text-right">
                                        {pair.netPnl !== null ? (
                                          <span className={getPnlColor(pair.netPnl)}>
                                            {formatCurrency(pair.netPnl)}
                                          </span>
                                        ) : '-'}
                                      </td>
                                    </tr>
                                  ))}
                                  <tr className="border-t-2 border-gray-400 dark:border-gray-500 bg-gray-100 dark:bg-gray-600">
                                    <td colSpan={9} className="px-3 py-2 text-sm font-bold text-gray-900 dark:text-white">
                                      TOTAL
                                    </td>
                                    <td className="px-3 py-2 text-sm font-bold text-gray-900 dark:text-white text-right">
                                      {(() => {
                                        const pairs = pairTransactions(tradeExecutions[trade.id]);
                                        const totalCommission = pairs.reduce((sum, p) => sum + p.totalCommission, 0);
                                        return `$${totalCommission.toFixed(2)}`;
                                      })()}
                                    </td>
                                    <td className="px-3 py-2 text-sm font-bold text-right">
                                      {(() => {
                                        const pairs = pairTransactions(tradeExecutions[trade.id]);
                                        const totalPnl = pairs.reduce((sum, p) => sum + (p.netPnl || 0), 0);
                                        return (
                                          <span className={getPnlColor(totalPnl)}>
                                            {formatCurrency(totalPnl)}
                                          </span>
                                        );
                                      })()}
                                    </td>
                                  </tr>
                                </tbody>
                              </table>
                            ) : (
                              <div className="text-sm text-gray-900 dark:text-white">Loading executions...</div>
                            )}

                            {/* Trade Analytics Section */}
                            <TradeAnalytics
                              tradeId={trade.id}
                              analytics={tradeAnalytics[trade.id] ?? null}
                              tradeStatus={trade.status}
                              onAnalyticsUpdate={(updatedAnalytics) => {
                                setTradeAnalytics(prev => ({ ...prev, [trade.id]: updatedAnalytics }));
                              }}
                            />

                            {/* Price Chart with Entry/Exit Markers */}
                            {trade.underlying && (
                              <div className="mt-4">
                                <LightweightChartWidget
                                  underlying={trade.underlying}
                                  openedAt={trade.opened_at}
                                  closedAt={trade.closed_at}
                                  entryPrice={trade.underlying_price_open}
                                  exitPrice={trade.underlying_price_close}
                                  height={250}
                                />
                              </div>
                            )}
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
