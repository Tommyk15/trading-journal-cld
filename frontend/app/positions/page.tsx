'use client';

import React, { useEffect, useState, useRef, useCallback } from 'react';
import { Header, ActionButton } from '@/components/layout/Header';
import { api, PositionsMarketDataResponse, PositionMarketDataResponse } from '@/lib/api/client';
import { formatCurrency, formatDate, getPnlColor } from '@/lib/utils';
import { RefreshCw, ChevronDown, ChevronRight, TrendingUp, TrendingDown, Briefcase, Layers, BarChart3, Box, ArrowUpDown, ArrowUp, ArrowDown, Search, X, Settings2, GripVertical, Eye, EyeOff } from 'lucide-react';

// Stock split type for adjustment calculations
interface StockSplit {
  id: number;
  symbol: string;
  split_date: string;
  ratio_from: number;
  ratio_to: number;
  adjustment_factor: number;
  price_factor: number;
}

interface OpenTrade {
  id: number;
  underlying: string;
  strategy_type: string;
  status: string;
  opened_at: string;
  num_legs: number;
  num_executions: number;
  opening_cost: string;
  total_commission: string;
  is_roll: boolean;
  is_assignment: boolean;
}

interface TradeExecution {
  id: number;
  exec_id: string;
  symbol: string;
  underlying: string;
  side: string;
  quantity: number;
  price: string;
  strike: number;
  option_type: string;
  expiration: string;
  open_close_indicator: string;
  execution_time: string;
  security_type: string;
  multiplier: number;
  commission: string;
  net_amount: string;
}

type PositionCategory = 'stocks' | 'options' | 'combos';
type PositionDirection = 'long' | 'short';
type SubsectionKey = `${PositionCategory}_${PositionDirection}`;

// Column configuration
interface ColumnConfig {
  id: string;
  label: string;
  visible: boolean;
  width: number;
  minWidth: number;
  sortable: boolean;
  align: 'left' | 'right';
}

const DEFAULT_COLUMNS: ColumnConfig[] = [
  { id: 'expand', label: '', visible: true, width: 48, minWidth: 48, sortable: false, align: 'left' },
  { id: 'date', label: 'Date', visible: true, width: 100, minWidth: 80, sortable: true, align: 'left' },
  { id: 'ticker', label: 'Ticker', visible: true, width: 80, minWidth: 60, sortable: true, align: 'left' },
  { id: 'qty', label: 'Qty', visible: true, width: 70, minWidth: 50, sortable: true, align: 'right' },
  { id: 'strategy', label: 'Strategy', visible: true, width: 140, minWidth: 100, sortable: true, align: 'left' },
  { id: 'strike', label: 'Strike', visible: true, width: 80, minWidth: 60, sortable: false, align: 'left' },
  { id: 'expiration', label: 'Expiration', visible: true, width: 100, minWidth: 80, sortable: false, align: 'left' },
  { id: 'dte', label: 'DTE', visible: true, width: 60, minWidth: 50, sortable: true, align: 'right' },
  { id: 'underlying', label: 'Underlying', visible: true, width: 100, minWidth: 80, sortable: false, align: 'right' },
  { id: 'avgPrice', label: 'Avg Price', visible: true, width: 100, minWidth: 80, sortable: false, align: 'right' },
  { id: 'cost', label: 'Cost', visible: true, width: 110, minWidth: 80, sortable: true, align: 'right' },
  { id: 'marketValue', label: 'Market Value', visible: true, width: 110, minWidth: 80, sortable: false, align: 'right' },
  { id: 'unrealizedPnl', label: 'Unrealized P&L', visible: true, width: 120, minWidth: 100, sortable: false, align: 'right' },
  { id: 'commission', label: 'Commission', visible: true, width: 100, minWidth: 80, sortable: false, align: 'right' },
];

export default function PositionsPage() {
  const [trades, setTrades] = useState<OpenTrade[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedTrades, setExpandedTrades] = useState<Set<number>>(new Set());
  const [tradeExecutions, setTradeExecutions] = useState<Record<number, TradeExecution[]>>({});
  const [collapsedSections, setCollapsedSections] = useState<Set<string>>(new Set());
  const [stockSplits, setStockSplits] = useState<Record<string, StockSplit[]>>({});

  // Market data state
  const [marketData, setMarketData] = useState<PositionsMarketDataResponse | null>(null);
  const [marketDataLoading, setMarketDataLoading] = useState(false);
  const [marketDataByTradeId, setMarketDataByTradeId] = useState<Record<number, PositionMarketDataResponse>>({});

  // Sorting and filtering state
  type SortColumn = 'date' | 'ticker' | 'qty' | 'strategy' | 'dte' | 'value' | null;
  type SortDirection = 'asc' | 'desc';
  const [sortColumn, setSortColumn] = useState<SortColumn>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc');
  const [filterTicker, setFilterTicker] = useState('');
  const [filterStrategy, setFilterStrategy] = useState('');

  // Column configuration state
  const [columns, setColumns] = useState<ColumnConfig[]>(() => {
    // Try to load from localStorage
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('positionsColumnConfig');
      if (saved) {
        try {
          const savedColumns = JSON.parse(saved) as ColumnConfig[];
          // Merge any new columns from DEFAULT_COLUMNS that don't exist in saved config
          const savedIds = new Set(savedColumns.map(c => c.id));
          const newColumns = DEFAULT_COLUMNS.filter(c => !savedIds.has(c.id));
          if (newColumns.length > 0) {
            // Add new columns at the end
            return [...savedColumns, ...newColumns];
          }
          return savedColumns;
        } catch (e) {
          // Ignore parse errors
        }
      }
    }
    return DEFAULT_COLUMNS;
  });
  const [showColumnSettings, setShowColumnSettings] = useState(false);
  const [resizingColumn, setResizingColumn] = useState<string | null>(null);
  const [draggedColumn, setDraggedColumn] = useState<string | null>(null);
  const resizeStartX = useRef<number>(0);
  const resizeStartWidth = useRef<number>(0);

  // Save column config to localStorage
  useEffect(() => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('positionsColumnConfig', JSON.stringify(columns));
    }
  }, [columns]);

  // Column resize handlers
  const handleResizeStart = useCallback((columnId: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const column = columns.find(c => c.id === columnId);
    if (column) {
      setResizingColumn(columnId);
      resizeStartX.current = e.clientX;
      resizeStartWidth.current = column.width;
    }
  }, [columns]);

  const handleResizeMove = useCallback((e: MouseEvent) => {
    if (resizingColumn) {
      const diff = e.clientX - resizeStartX.current;
      const column = columns.find(c => c.id === resizingColumn);
      if (column) {
        const newWidth = Math.max(column.minWidth, resizeStartWidth.current + diff);
        setColumns(cols => cols.map(c =>
          c.id === resizingColumn ? { ...c, width: newWidth } : c
        ));
      }
    }
  }, [resizingColumn, columns]);

  const handleResizeEnd = useCallback(() => {
    setResizingColumn(null);
  }, []);

  useEffect(() => {
    if (resizingColumn) {
      document.addEventListener('mousemove', handleResizeMove);
      document.addEventListener('mouseup', handleResizeEnd);
      return () => {
        document.removeEventListener('mousemove', handleResizeMove);
        document.removeEventListener('mouseup', handleResizeEnd);
      };
    }
  }, [resizingColumn, handleResizeMove, handleResizeEnd]);

  // Column visibility toggle
  const toggleColumnVisibility = (columnId: string) => {
    setColumns(cols => cols.map(c =>
      c.id === columnId ? { ...c, visible: !c.visible } : c
    ));
  };

  // Column reorder via drag and drop
  const handleDragStart = (columnId: string) => {
    setDraggedColumn(columnId);
  };

  const handleDragOver = (e: React.DragEvent, targetColumnId: string) => {
    e.preventDefault();
    if (draggedColumn && draggedColumn !== targetColumnId) {
      setColumns(cols => {
        const draggedIndex = cols.findIndex(c => c.id === draggedColumn);
        const targetIndex = cols.findIndex(c => c.id === targetColumnId);
        if (draggedIndex === -1 || targetIndex === -1) return cols;

        const newCols = [...cols];
        const [removed] = newCols.splice(draggedIndex, 1);
        newCols.splice(targetIndex, 0, removed);
        return newCols;
      });
    }
  };

  const handleDragEnd = () => {
    setDraggedColumn(null);
  };

  // Reset columns to default
  const resetColumns = () => {
    setColumns(DEFAULT_COLUMNS);
  };

  // Get visible columns
  const visibleColumns = columns.filter(c => c.visible);

  // Apply split adjustments to quantity based on execution date
  function applyQuantitySplitAdjustment(symbol: string, quantity: number, executionDate: string): number {
    const splits = stockSplits[symbol] || [];
    let adjustedQty = quantity;
    const execDate = new Date(executionDate);

    for (const split of splits) {
      const splitDate = new Date(split.split_date);
      // Only apply splits that occurred AFTER the execution date
      if (splitDate > execDate) {
        adjustedQty *= split.adjustment_factor;
      }
    }

    return Math.round(adjustedQty * 1000) / 1000; // Round to avoid floating point issues
  }

  // Apply split adjustments to price based on execution date
  function applyPriceSplitAdjustment(symbol: string, price: number, executionDate: string): number {
    const splits = stockSplits[symbol] || [];
    let adjustedPrice = price;
    const execDate = new Date(executionDate);

    for (const split of splits) {
      const splitDate = new Date(split.split_date);
      // Only apply splits that occurred AFTER the execution date
      if (splitDate > execDate) {
        adjustedPrice *= split.price_factor;
      }
    }

    return adjustedPrice;
  }

  async function fetchStockSplits() {
    try {
      const response = await fetch('http://localhost:8000/api/v1/stock-splits/by-symbol');
      const data = await response.json();
      setStockSplits(data);
    } catch (error) {
      console.error('Error fetching stock splits:', error);
    }
  }

  async function fetchMarketData(forceRefresh: boolean = false) {
    try {
      setMarketDataLoading(true);
      const data = await api.marketData.getPositionsMarketData(forceRefresh);
      setMarketData(data);

      // Build lookup map by trade_id
      const byTradeId: Record<number, PositionMarketDataResponse> = {};
      for (const pos of data.positions) {
        byTradeId[pos.trade_id] = pos;
      }
      setMarketDataByTradeId(byTradeId);
    } catch (error) {
      console.error('Error fetching market data:', error);
    } finally {
      setMarketDataLoading(false);
    }
  }

  async function fetchOpenTrades() {
    try {
      setLoading(true);
      const data: any = await api.trades.list({ status: 'OPEN', limit: 1000 });
      const openTrades = data.trades || [];
      setTrades(openTrades);

      // Fetch executions for all trades
      const executionsMap: Record<number, TradeExecution[]> = {};
      await Promise.all(
        openTrades.map(async (trade: OpenTrade) => {
          try {
            const response = await fetch(`http://localhost:8000/api/v1/trades/${trade.id}/executions`);
            const execData = await response.json();
            executionsMap[trade.id] = execData.executions || [];
          } catch (error) {
            console.error(`Error fetching executions for trade ${trade.id}:`, error);
          }
        })
      );
      setTradeExecutions(executionsMap);

      // Fetch market data after trades are loaded
      fetchMarketData();
    } catch (error) {
      console.error('Error fetching open trades:', error);
      setTrades([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchStockSplits();
    fetchOpenTrades();
  }, []);

  // Categorize trades into stocks, options (single leg), and combos (multi-leg)
  function categorizePosition(trade: OpenTrade, executions?: TradeExecution[]): PositionCategory {
    // Check if it's a stock position
    if (executions && executions.length > 0) {
      const hasOnlyStocks = executions.every(e => e.security_type === 'STK');
      if (hasOnlyStocks) return 'stocks';
    }

    // Check strategy type for single vs multi-leg
    const strategy = trade.strategy_type?.toLowerCase() || '';
    const singleLegStrategies = ['single', 'long call', 'long put', 'short call', 'short put', 'naked call', 'naked put'];

    if (singleLegStrategies.some(s => strategy.includes(s)) || trade.num_legs === 1) {
      return 'options';
    }

    return 'combos';
  }

  // Determine if a position is long or short
  function getPositionDirection(trade: OpenTrade, executions?: TradeExecution[]): PositionDirection {
    const strategy = trade.strategy_type?.toLowerCase() || '';

    // Check strategy type for explicit long/short indicators
    if (strategy.includes('long') || strategy.includes('bull')) return 'long';
    if (strategy.includes('short') || strategy.includes('bear') || strategy.includes('naked')) return 'short';

    // For stocks, check if net quantity is positive (long) or negative (short)
    if (executions && executions.length > 0) {
      const openingExecs = executions.filter(e => e.open_close_indicator === 'O');
      if (openingExecs.length > 0) {
        // Check if opening was a buy (long) or sell (short)
        const firstOpen = openingExecs[0];
        if (firstOpen.side === 'BOT') return 'long';
        if (firstOpen.side === 'SLD') return 'short';
      }
    }

    // Default based on opening cost (debit = long, credit = short)
    const openingCost = parseFloat(trade.opening_cost || '0');
    return openingCost > 0 ? 'long' : 'short';
  }

  // Compute trade data for sorting
  function getTradeDataForSort(trade: OpenTrade) {
    const executions = tradeExecutions[trade.id] || [];
    const aggregated = aggregateExecutionsSimple(executions);

    const isStockTrade = trade.strategy_type?.toLowerCase().includes('stock');

    // For stocks, calculate net position (buys - sells)
    // For options/combos, use min across legs
    let rawQty = 0;
    if (isStockTrade && aggregated.length > 0) {
      rawQty = aggregated.reduce((net, g) => {
        const isBuy = g.action === 'BUY';
        return net + (isBuy ? g.totalQuantity : -g.totalQuantity);
      }, 0);
      rawQty = Math.abs(rawQty);
    } else if (aggregated.length > 0) {
      rawQty = Math.min(...aggregated.map(g => g.totalQuantity));
    }

    const qty = isStockTrade
      ? applyQuantitySplitAdjustment(trade.underlying, rawQty, trade.opened_at)
      : rawQty;

    const expiration = aggregated.length > 0 && aggregated[0].expiration
      ? new Date(aggregated[0].expiration)
      : null;

    const dte = expiration
      ? Math.ceil((expiration.getTime() - new Date().getTime()) / (1000 * 60 * 60 * 24))
      : 9999; // Put no-expiration at end when sorting

    const totalComm = aggregated.reduce((sum, g) => sum + g.totalCommission, 0);
    const priceMultiplier = isStockTrade ? 1 : 100;

    // Cost includes commission (Avg Price * Qty)
    const rawAvgPrice = rawQty > 0
      ? (parseFloat(trade.opening_cost) + totalComm) / rawQty / priceMultiplier
      : 0;
    const avgPrice = isStockTrade
      ? applyPriceSplitAdjustment(trade.underlying, rawAvgPrice, trade.opened_at)
      : rawAvgPrice;
    const cost = avgPrice * qty * priceMultiplier;

    return { qty, dte, cost };
  }

  // Simple aggregation for sorting (without full display logic)
  function aggregateExecutionsSimple(executions: TradeExecution[]) {
    const displayExecutions = executions.filter((exec) => {
      const qty = typeof exec.quantity === 'number' ? exec.quantity : parseFloat(String(exec.quantity));
      return qty >= 1;
    });

    const actionGroups: Record<string, TradeExecution[]> = {};
    displayExecutions.forEach((exec) => {
      const expDate = exec.expiration ? new Date(exec.expiration).toISOString().split('T')[0] : 'no-exp';
      const action = exec.side === 'BOT' ? 'BUY' : 'SELL';
      const key = `${exec.strike}_${exec.option_type}_${expDate}_${action}`;
      if (!actionGroups[key]) actionGroups[key] = [];
      actionGroups[key].push(exec);
    });

    return Object.entries(actionGroups).map(([, execs]) => {
      const isBuy = execs[0].side === 'BOT';
      const action = isBuy ? 'BUY' : 'SELL';
      const totalQty = execs.reduce((sum, e) => sum + e.quantity, 0);
      const totalValue = isBuy
        ? execs.reduce((sum, e) => sum + Math.abs(parseFloat(e.net_amount)), 0)
        : execs.reduce((sum, e) => sum + (-Math.abs(parseFloat(e.net_amount))), 0);
      const totalCommission = execs.reduce((sum, e) => sum + parseFloat(e.commission), 0);
      return {
        action,
        expiration: execs[0].expiration,
        totalQuantity: totalQty,
        totalValue,
        totalCommission,
      };
    });
  }

  // Handle sort column click
  function handleSort(column: SortColumn) {
    if (sortColumn === column) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortColumn(column);
      setSortDirection('asc');
    }
  }

  // Filter trades based on current filters
  function filterTrades(tradeList: OpenTrade[]): OpenTrade[] {
    return tradeList.filter(trade => {
      const tickerMatch = !filterTicker ||
        trade.underlying.toLowerCase().includes(filterTicker.toLowerCase());
      const strategyMatch = !filterStrategy ||
        trade.strategy_type.toLowerCase().includes(filterStrategy.toLowerCase());
      return tickerMatch && strategyMatch;
    });
  }

  // Sort trades based on current sort settings
  function sortTrades(tradeList: OpenTrade[]): OpenTrade[] {
    if (!sortColumn) return tradeList;

    return [...tradeList].sort((a, b) => {
      let aVal: number | string = 0;
      let bVal: number | string = 0;

      switch (sortColumn) {
        case 'date':
          aVal = new Date(a.opened_at).getTime();
          bVal = new Date(b.opened_at).getTime();
          break;
        case 'ticker':
          aVal = a.underlying.toLowerCase();
          bVal = b.underlying.toLowerCase();
          break;
        case 'strategy':
          aVal = a.strategy_type.toLowerCase();
          bVal = b.strategy_type.toLowerCase();
          break;
        case 'qty':
          aVal = getTradeDataForSort(a).qty;
          bVal = getTradeDataForSort(b).qty;
          break;
        case 'dte':
          aVal = getTradeDataForSort(a).dte;
          bVal = getTradeDataForSort(b).dte;
          break;
        case 'value':
          aVal = getTradeDataForSort(a).cost;
          bVal = getTradeDataForSort(b).cost;
          break;
      }

      if (typeof aVal === 'string' && typeof bVal === 'string') {
        return sortDirection === 'asc'
          ? aVal.localeCompare(bVal)
          : bVal.localeCompare(aVal);
      }

      return sortDirection === 'asc'
        ? (aVal as number) - (bVal as number)
        : (bVal as number) - (aVal as number);
    });
  }

  // Get unique strategies for filter dropdown
  const uniqueStrategies = [...new Set(trades.map(t => t.strategy_type))].sort();

  // Sortable header component
  function SortableHeader({
    column,
    label,
    align = 'left'
  }: {
    column: SortColumn;
    label: string;
    align?: 'left' | 'right';
  }) {
    const isActive = sortColumn === column;
    const alignClass = align === 'right' ? 'text-right justify-end' : 'text-left';

    return (
      <th
        className={`px-4 py-2 ${alignClass} text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-600 transition-colors select-none`}
        onClick={() => handleSort(column)}
      >
        <div className={`flex items-center gap-1 ${align === 'right' ? 'justify-end' : ''}`}>
          <span>{label}</span>
          {isActive ? (
            sortDirection === 'asc' ? (
              <ArrowUp className="h-3 w-3 text-blue-500" />
            ) : (
              <ArrowDown className="h-3 w-3 text-blue-500" />
            )
          ) : (
            <ArrowUpDown className="h-3 w-3 text-gray-400 opacity-0 group-hover:opacity-100" />
          )}
        </div>
      </th>
    );
  }

  // Get filtered trades first
  const filteredTrades = filterTrades(trades);

  // Get categorized trades with long/short split (using filtered trades)
  const categorizedTrades = {
    stocks: {
      long: filteredTrades.filter(t => categorizePosition(t, tradeExecutions[t.id]) === 'stocks' && getPositionDirection(t, tradeExecutions[t.id]) === 'long'),
      short: filteredTrades.filter(t => categorizePosition(t, tradeExecutions[t.id]) === 'stocks' && getPositionDirection(t, tradeExecutions[t.id]) === 'short'),
    },
    options: {
      long: filteredTrades.filter(t => categorizePosition(t, tradeExecutions[t.id]) === 'options' && getPositionDirection(t, tradeExecutions[t.id]) === 'long'),
      short: filteredTrades.filter(t => categorizePosition(t, tradeExecutions[t.id]) === 'options' && getPositionDirection(t, tradeExecutions[t.id]) === 'short'),
    },
    combos: {
      long: filteredTrades.filter(t => categorizePosition(t, tradeExecutions[t.id]) === 'combos' && getPositionDirection(t, tradeExecutions[t.id]) === 'long'),
      short: filteredTrades.filter(t => categorizePosition(t, tradeExecutions[t.id]) === 'combos' && getPositionDirection(t, tradeExecutions[t.id]) === 'short'),
    },
  };

  // Toggle section collapse
  function toggleSection(section: string) {
    const newCollapsed = new Set(collapsedSections);
    if (newCollapsed.has(section)) {
      newCollapsed.delete(section);
    } else {
      newCollapsed.add(section);
    }
    setCollapsedSections(newCollapsed);
  }

  // Toggle trade expansion
  function toggleTradeExpansion(tradeId: number) {
    const newExpanded = new Set(expandedTrades);
    if (newExpanded.has(tradeId)) {
      newExpanded.delete(tradeId);
    } else {
      newExpanded.add(tradeId);
    }
    setExpandedTrades(newExpanded);
  }

  // Helper function to determine action label
  function getActionLabel(exec: TradeExecution) {
    const isBuy = exec.side === 'BOT';
    const isOpen = exec.open_close_indicator === 'O';

    if (isBuy && isOpen) return 'BTO';
    if (isBuy && !isOpen) return 'BTC';
    if (!isBuy && isOpen) return 'STO';
    return 'STC';
  }

  // Aggregate executions for display
  function aggregateExecutions(executions: TradeExecution[]) {
    // Filter out fractional quantity executions (< 1 share) for display
    // These are typically IBKR price improvement rebates
    const displayExecutions = executions.filter((exec) => {
      const qty = typeof exec.quantity === 'number' ? exec.quantity : parseFloat(String(exec.quantity));
      return qty >= 1;
    });

    const actionGroups: Record<string, TradeExecution[]> = {};

    displayExecutions.forEach((exec) => {
      const expDate = exec.expiration ? new Date(exec.expiration).toISOString().split('T')[0] : 'no-exp';
      const action = getActionLabel(exec);
      const key = `${exec.strike}_${exec.option_type}_${expDate}_${action}`;
      if (!actionGroups[key]) {
        actionGroups[key] = [];
      }
      actionGroups[key].push(exec);
    });

    return Object.entries(actionGroups)
      .map(([key, execs]) => {
        const action = getActionLabel(execs[0]);
        const isBuy = action.includes('BTO') || action.includes('BTC');

        const totalQty = execs.reduce((sum, e) => sum + e.quantity, 0);
        const avgPrice = execs.reduce((sum, e) => sum + parseFloat(e.price) * e.quantity, 0) / totalQty;
        const totalValue = isBuy
          ? execs.reduce((sum, e) => sum + Math.abs(parseFloat(e.net_amount)), 0)
          : execs.reduce((sum, e) => sum + (-Math.abs(parseFloat(e.net_amount))), 0);
        const totalCommission = execs.reduce((sum, e) => sum + parseFloat(e.commission), 0);

        return {
          action,
          strike: execs[0].strike,
          option_type: execs[0].option_type,
          expiration: execs[0].expiration,
          security_type: execs[0].security_type,
          totalQuantity: totalQty,
          avgPrice,
          totalValue,
          totalCommission,
        };
      })
      .sort((a, b) => {
        const strikeDiff = (a.strike || 0) - (b.strike || 0);
        if (strikeDiff !== 0) return strikeDiff;
        const aIsBuy = a.action.includes('BTO') || a.action.includes('BTC');
        const bIsBuy = b.action.includes('BTO') || b.action.includes('BTC');
        if (aIsBuy && !bIsBuy) return -1;
        if (!aIsBuy && bIsBuy) return 1;
        return 0;
      });
  }

  // Pair transactions for expanded view
  function pairTransactions(executions: TradeExecution[]) {
    // Filter out fractional quantity executions (< 1 share) for display
    // These are typically IBKR price improvement rebates
    const displayExecutions = executions.filter((exec) => {
      const qty = typeof exec.quantity === 'number' ? exec.quantity : parseFloat(String(exec.quantity));
      return qty >= 1;
    });

    const groups: Record<string, TradeExecution[]> = {};

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
      const openingExecs = execs.filter(e => e.open_close_indicator === 'O');
      const closingExecs = execs.filter(e => e.open_close_indicator === 'C');
      const isLongPosition = openingExecs.some(e => e.side === 'BOT');

      const openingQty = openingExecs.reduce((sum, e) => sum + e.quantity, 0);
      const openingWeightedPrice = openingQty > 0
        ? openingExecs.reduce((sum, e) => sum + parseFloat(e.price) * e.quantity, 0) / openingQty
        : 0;

      const closingQty = closingExecs.reduce((sum, e) => sum + e.quantity, 0);
      const closingWeightedPrice = closingQty > 0
        ? closingExecs.reduce((sum, e) => sum + parseFloat(e.price) * e.quantity, 0) / closingQty
        : 0;

      const openDate = openingExecs.length > 0
        ? new Date(Math.min(...openingExecs.map(e => new Date(e.execution_time).getTime())))
        : null;
      const closeDate = closingExecs.length > 0
        ? new Date(Math.min(...closingExecs.map(e => new Date(e.execution_time).getTime())))
        : null;

      const openCommission = openingExecs.reduce((sum, e) => sum + parseFloat(e.commission), 0);
      const closeCommission = closingExecs.reduce((sum, e) => sum + parseFloat(e.commission), 0);
      // Stock trades have multiplier=1 (no 100x), even if stored incorrectly as 100
      const isStock = execs[0].security_type === 'STK';
      const multiplier = isStock ? 1 : (execs[0].multiplier || 100);

      const netPnl = closingQty > 0
        ? (isLongPosition
            ? (closingWeightedPrice - openingWeightedPrice) * Math.min(openingQty, closingQty) * multiplier - openCommission - closeCommission
            : (openingWeightedPrice - closingWeightedPrice) * Math.min(openingQty, closingQty) * multiplier - openCommission - closeCommission)
        : 0;

      let action = '';
      if (execs[0].security_type === 'STK') {
        action = isLongPosition ? 'Long Stock' : 'Short Stock';
      } else if (isLongPosition) {
        action = execs[0].option_type === 'C' ? 'Long Call' : 'Long Put';
      } else {
        action = execs[0].option_type === 'C' ? 'Short Call' : 'Short Put';
      }

      pairedResults.push({
        dateOpened: openDate,
        dateClosed: closeDate,
        action,
        quantity: Math.max(openingQty, closingQty),
        type: execs[0].security_type === 'STK' ? 'Stock' : (execs[0].option_type === 'C' ? 'Call' : 'Put'),
        strike: execs[0].strike,
        expiration: execs[0].expiration,
        openPrice: openingWeightedPrice ? (isLongPosition ? openingWeightedPrice : -openingWeightedPrice) : null,
        closePrice: closingQty > 0 ? closingWeightedPrice : null,
        totalCommission: openCommission + closeCommission,
        netPnl: closingQty > 0 ? netPnl : null,
        isOpen: closingQty === 0,
      });
    });

    return pairedResults.sort((a, b) => (a.strike || 0) - (b.strike || 0));
  }

  // Calculate summary stats
  const totalPortfolioCost = trades.reduce(
    (sum, trade) => sum + parseFloat(trade.opening_cost || '0'),
    0
  );
  const totalCommission = trades.reduce(
    (sum, trade) => sum + parseFloat(trade.total_commission || '0'),
    0
  );
  const uniqueUnderlyings = new Set(trades.map(t => t.underlying)).size;

  // Subsection component for Long/Short within each category
  function PositionSubsection({
    title,
    sectionKey,
    positions,
    direction,
  }: {
    title: string;
    sectionKey: string;
    positions: OpenTrade[];
    direction: PositionDirection;
  }) {
    const isCollapsed = collapsedSections.has(sectionKey);
    const sectionCost = positions.reduce((sum, t) => sum + parseFloat(t.opening_cost || '0'), 0);
    const bgColor = direction === 'long' ? 'bg-green-50/50 dark:bg-green-900/20' : 'bg-red-50/50 dark:bg-red-900/20';
    const textColor = direction === 'long' ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400';
    const iconColor = direction === 'long' ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400';

    if (positions.length === 0) return null;

    return (
      <div className="border-t border-gray-100 dark:border-gray-700 first:border-t-0">
        {/* Subsection Header */}
        <div
          className={`px-4 py-2 ${bgColor} flex items-center justify-between cursor-pointer`}
          onClick={() => toggleSection(sectionKey)}
        >
          <div className="flex items-center gap-3">
            {direction === 'long' ? (
              <TrendingUp className={`h-4 w-4 ${iconColor}`} />
            ) : (
              <TrendingDown className={`h-4 w-4 ${iconColor}`} />
            )}
            <h3 className={`text-sm font-medium ${textColor}`}>{title}</h3>
            <span className={`px-2 py-0.5 rounded-full bg-white/70 dark:bg-gray-800/70 text-xs font-medium ${textColor}`}>
              {positions.length}
            </span>
          </div>
          <div className="flex items-center gap-4">
            <span className={`text-sm font-medium ${sectionCost >= 0 ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400'}`}>
              {formatCurrency(sectionCost)}
            </span>
            {isCollapsed ? (
              <ChevronRight className="h-4 w-4 text-gray-500 dark:text-gray-400" />
            ) : (
              <ChevronDown className="h-4 w-4 text-gray-500 dark:text-gray-400" />
            )}
          </div>
        </div>

        {/* Subsection Content */}
        {!isCollapsed && (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700" style={{ tableLayout: 'fixed' }}>
              <thead className="bg-gray-50 dark:bg-gray-700">
                <tr className="group">
                  {visibleColumns.map((col) => {
                    const sortColumnMap: Record<string, SortColumn> = {
                      date: 'date',
                      ticker: 'ticker',
                      qty: 'qty',
                      strategy: 'strategy',
                      dte: 'dte',
                      cost: 'value',
                    };
                    const mappedSortColumn = sortColumnMap[col.id] || null;

                    if (col.id === 'expand') {
                      return (
                        <th
                          key={col.id}
                          className="px-2 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider relative"
                          style={{ width: col.width }}
                        />
                      );
                    }

                    return (
                      <th
                        key={col.id}
                        className={`px-4 py-2 text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider relative ${
                          col.align === 'right' ? 'text-right' : 'text-left'
                        } ${col.sortable ? 'cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-600' : ''}`}
                        style={{ width: col.width }}
                        onClick={() => col.sortable && mappedSortColumn && handleSort(mappedSortColumn)}
                      >
                        <div className={`flex items-center gap-1 ${col.align === 'right' ? 'justify-end' : ''}`}>
                          <span>{col.label}</span>
                          {col.sortable && mappedSortColumn && sortColumn === mappedSortColumn && (
                            sortDirection === 'asc' ? (
                              <ArrowUp className="h-3 w-3 text-blue-500" />
                            ) : (
                              <ArrowDown className="h-3 w-3 text-blue-500" />
                            )
                          )}
                        </div>
                        {/* Resize handle */}
                        <div
                          className="absolute right-0 top-0 h-full w-1 cursor-col-resize hover:bg-blue-500 opacity-0 hover:opacity-100"
                          onMouseDown={(e) => handleResizeStart(col.id, e)}
                        />
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                {sortTrades(positions).map((trade) => {
                  const executions = tradeExecutions[trade.id] || [];
                  const aggregated = aggregateExecutions(executions);

                  const strikes = aggregated.length > 0
                    ? [...new Set(aggregated.map(g => g.strike).filter(s => s))]
                        .sort((a, b) => a - b)
                        .join('/')
                    : '-';

                  const expiration = aggregated.length > 0 && aggregated[0].expiration
                    ? new Date(aggregated[0].expiration)
                    : null;

                  const dte = expiration
                    ? Math.ceil((expiration.getTime() - new Date().getTime()) / (1000 * 60 * 60 * 24))
                    : null;

                  // Stock trades don't have a 100x multiplier
                  const isStockTrade = trade.strategy_type?.toLowerCase().includes('stock');

                  // For stocks, calculate net position (buys - sells)
                  // For options/combos, use min across legs (for spread size)
                  let rawQty = 0;
                  if (isStockTrade && aggregated.length > 0) {
                    // Net position for stocks: sum of buys minus sum of sells
                    rawQty = aggregated.reduce((net, g) => {
                      const isBuy = g.action.includes('BTO') || g.action.includes('BTC') || g.action === 'BUY';
                      return net + (isBuy ? g.totalQuantity : -g.totalQuantity);
                    }, 0);
                    rawQty = Math.abs(rawQty); // Show absolute value
                  } else if (aggregated.length > 0) {
                    rawQty = Math.min(...aggregated.map(g => g.totalQuantity));
                  }
                  const priceMultiplier = isStockTrade ? 1 : 100;

                  // Apply split adjustments for stock trades
                  const qty = isStockTrade
                    ? applyQuantitySplitAdjustment(trade.underlying, rawQty, trade.opened_at)
                    : rawQty;

                  const totalComm = aggregated.reduce((sum, g) => sum + g.totalCommission, 0);

                  // Avg Price includes commission per share/contract
                  const rawAvgPrice = rawQty > 0
                    ? (parseFloat(trade.opening_cost) + totalComm) / rawQty / priceMultiplier
                    : 0;

                  const avgPrice = isStockTrade
                    ? applyPriceSplitAdjustment(trade.underlying, rawAvgPrice, trade.opened_at)
                    : rawAvgPrice;

                  // Cost = Avg Price * Qty (includes commission)
                  const cost = avgPrice * qty * priceMultiplier;

                  // Get market data for this trade
                  const tradeMarketData = marketDataByTradeId[trade.id];
                  const marketValue = tradeMarketData?.total_market_value ?? null;
                  const unrealizedPnl = tradeMarketData?.unrealized_pnl ?? null;
                  const unrealizedPnlPercent = tradeMarketData?.unrealized_pnl_percent ?? null;
                  const isMarketDataStale = tradeMarketData?.is_stale ?? false;
                  const marketDataSource = tradeMarketData?.source ?? null;

                  // Helper to render cell content based on column id
                  const renderCellContent = (columnId: string) => {
                    switch (columnId) {
                      case 'expand':
                        return (
                          <button
                            onClick={() => toggleTradeExpansion(trade.id)}
                            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                          >
                            {expandedTrades.has(trade.id) ? (
                              <ChevronDown className="h-4 w-4" />
                            ) : (
                              <ChevronRight className="h-4 w-4" />
                            )}
                          </button>
                        );
                      case 'date':
                        return formatDate(trade.opened_at);
                      case 'ticker':
                        return <span className="font-medium">{trade.underlying}</span>;
                      case 'qty':
                        return qty;
                      case 'strategy':
                        return (
                          <>
                            {trade.strategy_type}
                            {trade.is_assignment && (
                              <span className="ml-2 px-1.5 py-0.5 text-xs bg-orange-100 dark:bg-orange-900/50 text-orange-700 dark:text-orange-300 rounded">
                                ASSIGN
                              </span>
                            )}
                            {trade.is_roll && !trade.is_assignment && (
                              <span className="ml-2 px-1.5 py-0.5 text-xs bg-purple-100 dark:bg-purple-900/50 text-purple-700 dark:text-purple-300 rounded">
                                ROLL
                              </span>
                            )}
                          </>
                        );
                      case 'strike':
                        return strikes;
                      case 'expiration':
                        return expiration ? formatDate(expiration.toISOString()) : '-';
                      case 'dte':
                        return dte !== null ? (
                          <span className={dte <= 7 ? 'text-red-600 dark:text-red-400 font-semibold' : ''}>
                            {dte}
                          </span>
                        ) : '-';
                      case 'underlying':
                        if (marketDataLoading) {
                          return <span className="text-gray-400 dark:text-gray-500 animate-pulse">...</span>;
                        }
                        const underlyingPrice = tradeMarketData?.underlying_price ?? null;
                        return underlyingPrice !== null ? (
                          <span className={isMarketDataStale ? 'text-gray-500 dark:text-gray-400' : 'font-medium'}>
                            {formatCurrency(underlyingPrice)}
                          </span>
                        ) : (
                          <span className="text-gray-400 dark:text-gray-500">-</span>
                        );
                      case 'avgPrice':
                        return formatCurrency(avgPrice);
                      case 'cost':
                        return (
                          <span className={cost >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}>
                            {formatCurrency(cost)}
                          </span>
                        );
                      case 'marketValue':
                        if (marketDataLoading) {
                          return <span className="text-gray-400 dark:text-gray-500 animate-pulse">...</span>;
                        }
                        return marketValue !== null ? (
                          <span className={isMarketDataStale ? 'text-gray-500 dark:text-gray-400' : ''}>
                            {formatCurrency(marketValue)}
                          </span>
                        ) : (
                          <span className="text-gray-400 dark:text-gray-500">-</span>
                        );
                      case 'unrealizedPnl':
                        if (marketDataLoading) {
                          return <span className="text-gray-400 dark:text-gray-500 animate-pulse">...</span>;
                        }
                        return unrealizedPnl !== null ? (
                          <div className="flex flex-col items-end">
                            <span className={`${unrealizedPnl >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'} ${isMarketDataStale ? 'opacity-60' : ''}`}>
                              {formatCurrency(unrealizedPnl)}
                            </span>
                            <span className={`text-xs ${unrealizedPnlPercent !== null && unrealizedPnlPercent >= 0 ? 'text-green-500 dark:text-green-500' : 'text-red-500 dark:text-red-500'}`}>
                              {unrealizedPnlPercent !== null ? `(${unrealizedPnlPercent >= 0 ? '+' : ''}${unrealizedPnlPercent.toFixed(2)}%)` : ''}
                            </span>
                          </div>
                        ) : (
                          <span className="text-gray-400 dark:text-gray-500">-</span>
                        );
                      case 'commission':
                        return `$${totalComm.toFixed(2)}`;
                      default:
                        return '-';
                    }
                  };

                  return (
                    <React.Fragment key={trade.id}>
                      <tr className="hover:bg-gray-50 dark:hover:bg-gray-700">
                        {visibleColumns.map((col) => (
                          <td
                            key={col.id}
                            className={`px-4 py-2 whitespace-nowrap text-sm text-gray-900 dark:text-white ${
                              col.align === 'right' ? 'text-right' : 'text-left'
                            }`}
                            style={{ width: col.width }}
                          >
                            {renderCellContent(col.id)}
                          </td>
                        ))}
                      </tr>

                      {/* Expanded execution details */}
                      {expandedTrades.has(trade.id) && executions.length > 0 && (
                        <tr>
                          <td colSpan={visibleColumns.length} className="px-6 py-4 bg-gray-50 dark:bg-gray-700/50">
                            {/* Data Source Indicator */}
                            <div className="flex items-center gap-2 mb-3">
                              <span className="px-2 py-0.5 text-xs font-medium bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300 rounded">
                                Source: IBKR
                              </span>
                              {executions[0]?.exec_id && (
                                <span className="text-xs text-gray-500 dark:text-gray-400">
                                  Exec ID: {executions[0].exec_id.substring(0, 20)}...
                                </span>
                              )}
                            </div>
                            <table className="min-w-full">
                              <thead>
                                <tr className="border-b border-gray-300 dark:border-gray-600">
                                  <th className="px-3 py-2 text-left text-xs font-semibold text-gray-700 dark:text-gray-300">Date Opened</th>
                                  <th className="px-3 py-2 text-left text-xs font-semibold text-gray-700 dark:text-gray-300">Action</th>
                                  <th className="px-3 py-2 text-left text-xs font-semibold text-gray-700 dark:text-gray-300">Qty</th>
                                  <th className="px-3 py-2 text-left text-xs font-semibold text-gray-700 dark:text-gray-300">Type</th>
                                  <th className="px-3 py-2 text-left text-xs font-semibold text-gray-700 dark:text-gray-300">Strike</th>
                                  <th className="px-3 py-2 text-left text-xs font-semibold text-gray-700 dark:text-gray-300">Expiration</th>
                                  <th className="px-3 py-2 text-right text-xs font-semibold text-gray-700 dark:text-gray-300">Open Price</th>
                                  <th className="px-3 py-2 text-right text-xs font-semibold text-gray-700 dark:text-gray-300">Commission</th>
                                </tr>
                              </thead>
                              <tbody>
                                {pairTransactions(executions).map((pair: any, idx: number) => {
                                  // Apply split adjustments for stock positions
                                  const isStockPosition = pair.type === 'Stock';
                                  const execDate = pair.dateOpened ? pair.dateOpened.toISOString() : trade.opened_at;
                                  const displayQty = isStockPosition
                                    ? applyQuantitySplitAdjustment(trade.underlying, pair.quantity, execDate)
                                    : pair.quantity;
                                  const displayPrice = isStockPosition && pair.openPrice !== null
                                    ? applyPriceSplitAdjustment(trade.underlying, Math.abs(pair.openPrice), execDate)
                                    : pair.openPrice !== null ? Math.abs(pair.openPrice) : null;

                                  return (
                                    <tr key={idx} className="border-b border-gray-200 dark:border-gray-600">
                                      <td className="px-3 py-2 text-sm text-gray-900 dark:text-white">
                                        {pair.dateOpened ? formatDate(pair.dateOpened.toISOString()) : '-'}
                                      </td>
                                      <td className="px-3 py-2 text-sm">
                                        <span className={`font-semibold ${pair.action.includes('Long') ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400'}`}>
                                          {pair.action.includes('Long') ? '+' : '-'} {pair.action}
                                        </span>
                                      </td>
                                      <td className="px-3 py-2 text-sm font-medium text-gray-900 dark:text-white">{displayQty}</td>
                                      <td className="px-3 py-2 text-sm text-gray-900 dark:text-white">{pair.type}</td>
                                      <td className="px-3 py-2 text-sm font-medium text-gray-900 dark:text-white">
                                        {pair.strike ? `$${pair.strike}` : '-'}
                                      </td>
                                      <td className="px-3 py-2 text-sm text-gray-900 dark:text-white">
                                        {pair.expiration ? formatDate(pair.expiration) : '-'}
                                      </td>
                                      <td className="px-3 py-2 text-sm font-medium text-gray-900 dark:text-white text-right">
                                        {displayPrice !== null ? `$${displayPrice.toFixed(2)}` : '-'}
                                      </td>
                                      <td className="px-3 py-2 text-sm text-gray-900 dark:text-white text-right">
                                        ${pair.totalCommission.toFixed(2)}
                                      </td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  }

  // Main section component with Long/Short subsections
  function PositionSection({
    title,
    icon,
    category,
    longPositions,
    shortPositions,
    color
  }: {
    title: string;
    icon: React.ReactNode;
    category: PositionCategory;
    longPositions: OpenTrade[];
    shortPositions: OpenTrade[];
    color: string;
  }) {
    const totalCount = longPositions.length + shortPositions.length;
    const sectionCost = [...longPositions, ...shortPositions].reduce((sum, t) => sum + parseFloat(t.opening_cost || '0'), 0);
    const isSectionCollapsed = collapsedSections.has(category);

    return (
      <div className="rounded-lg bg-white dark:bg-gray-800 shadow overflow-hidden transition-colors">
        {/* Main Section Header */}
        <div
          className={`px-4 py-3 ${color} flex items-center justify-between cursor-pointer`}
          onClick={() => toggleSection(category)}
        >
          <div className="flex items-center gap-3">
            {icon}
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{title}</h2>
            <span className="px-2 py-0.5 rounded-full bg-white/50 dark:bg-gray-800/50 text-sm font-medium text-gray-900 dark:text-white">
              {totalCount}
            </span>
          </div>
          <div className="flex items-center gap-4">
            <span className={`text-sm font-medium ${sectionCost >= 0 ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400'}`}>
              {formatCurrency(sectionCost)}
            </span>
            {isSectionCollapsed ? (
              <ChevronRight className="h-5 w-5 text-gray-600 dark:text-gray-400" />
            ) : (
              <ChevronDown className="h-5 w-5 text-gray-600 dark:text-gray-400" />
            )}
          </div>
        </div>

        {/* Section Content with Long/Short Subsections */}
        {!isSectionCollapsed && (
          <div>
            {totalCount === 0 ? (
              <div className="px-6 py-8 text-center text-gray-500 dark:text-gray-400">
                No {title.toLowerCase()} positions
              </div>
            ) : (
              <>
                <PositionSubsection
                  title="Long"
                  sectionKey={`${category}_long`}
                  positions={longPositions}
                  direction="long"
                />
                <PositionSubsection
                  title="Short"
                  sectionKey={`${category}_short`}
                  positions={shortPositions}
                  direction="short"
                />
              </>
            )}
          </div>
        )}
      </div>
    );
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-100 dark:bg-gray-900 transition-colors">
        <Header
          title="Portfolio"
          subtitle="View and manage your open positions"
        />
        <div className="p-6">
          <div className="animate-pulse space-y-4">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-32 rounded-lg bg-gray-200 dark:bg-gray-700" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900 transition-colors">
      <Header
        title="Portfolio"
        subtitle="View and manage your open positions"
        actions={
          <div className="flex items-center gap-2">
            <ActionButton
              onClick={() => fetchMarketData(true)}
              icon={<BarChart3 className="h-4 w-4" />}
              label="Refresh Prices"
              loading={marketDataLoading}
            />
            <ActionButton
              onClick={fetchOpenTrades}
              icon={<RefreshCw className="h-4 w-4" />}
              label="Refresh All"
              loading={loading}
            />
          </div>
        }
      />

      <div className="p-6 space-y-6">
        {/* Summary Cards */}
        <div className="grid gap-6 md:grid-cols-3 lg:grid-cols-5">
          <div className="rounded-lg bg-white dark:bg-gray-800 p-6 shadow transition-colors">
            <div className="flex items-center gap-2">
              <Layers className="h-5 w-5 text-blue-600" />
              <h3 className="text-sm font-medium text-gray-600 dark:text-gray-400">Open Positions</h3>
            </div>
            <p className="mt-2 text-3xl font-bold text-gray-900 dark:text-white">
              {trades.length}
            </p>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              {uniqueUnderlyings} underlying{uniqueUnderlyings !== 1 ? 's' : ''}
            </p>
          </div>
          <div className="rounded-lg bg-white dark:bg-gray-800 p-6 shadow transition-colors">
            <div className="flex items-center gap-2">
              {totalPortfolioCost >= 0 ? (
                <TrendingUp className="h-5 w-5 text-green-600 dark:text-green-400" />
              ) : (
                <TrendingDown className="h-5 w-5 text-red-600 dark:text-red-400" />
              )}
              <h3 className="text-sm font-medium text-gray-600 dark:text-gray-400">Net Cost Basis</h3>
            </div>
            <p className={`mt-2 text-3xl font-bold ${totalPortfolioCost >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
              {formatCurrency(totalPortfolioCost)}
            </p>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              {totalPortfolioCost < 0 ? 'Net credit received' : 'Net debit paid'}
            </p>
          </div>
          <div className="rounded-lg bg-white dark:bg-gray-800 p-6 shadow transition-colors">
            <div className="flex items-center gap-2">
              {marketData?.net_unrealized_pnl !== null && marketData?.net_unrealized_pnl !== undefined ? (
                marketData.net_unrealized_pnl >= 0 ? (
                  <TrendingUp className="h-5 w-5 text-green-600 dark:text-green-400" />
                ) : (
                  <TrendingDown className="h-5 w-5 text-red-600 dark:text-red-400" />
                )
              ) : (
                <BarChart3 className="h-5 w-5 text-blue-600" />
              )}
              <h3 className="text-sm font-medium text-gray-600 dark:text-gray-400">Net Unrealized P&L</h3>
            </div>
            {marketDataLoading ? (
              <>
                <p className="mt-2 text-3xl font-bold text-gray-400 dark:text-gray-500 animate-pulse">
                  ...
                </p>
                <p className="mt-1 text-sm text-gray-400 dark:text-gray-500">
                  Loading market data
                </p>
              </>
            ) : marketData?.net_unrealized_pnl !== null && marketData?.net_unrealized_pnl !== undefined ? (
              <>
                <p className={`mt-2 text-3xl font-bold ${marketData.net_unrealized_pnl >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                  {formatCurrency(marketData.net_unrealized_pnl)}
                </p>
                <p className={`mt-1 text-sm ${marketData.net_unrealized_pnl_percent !== null && marketData.net_unrealized_pnl_percent >= 0 ? 'text-green-500 dark:text-green-400' : 'text-red-500 dark:text-red-400'}`}>
                  {marketData.net_unrealized_pnl_percent !== null
                    ? `${marketData.net_unrealized_pnl_percent >= 0 ? '+' : ''}${marketData.net_unrealized_pnl_percent.toFixed(2)}%`
                    : ''} · {marketData.source}
                </p>
              </>
            ) : (
              <>
                <p className="mt-2 text-3xl font-bold text-gray-400 dark:text-gray-500">
                  -
                </p>
                <p className="mt-1 text-sm text-gray-400 dark:text-gray-500">
                  {marketData?.ibkr_connected === false ? 'IBKR disconnected' : 'No market data'}
                </p>
              </>
            )}
          </div>
          <div className="rounded-lg bg-white dark:bg-gray-800 p-6 shadow transition-colors">
            <div className="flex items-center gap-2">
              <Briefcase className="h-5 w-5 text-gray-600 dark:text-gray-400" />
              <h3 className="text-sm font-medium text-gray-600 dark:text-gray-400">Total Commission</h3>
            </div>
            <p className="mt-2 text-3xl font-bold text-gray-900 dark:text-white">
              {formatCurrency(totalCommission)}
            </p>
          </div>
          <div className="rounded-lg bg-white dark:bg-gray-800 p-6 shadow transition-colors">
            <h3 className="text-sm font-medium text-gray-600 dark:text-gray-400">Breakdown</h3>
            <div className="mt-2 space-y-2 text-sm">
              <div className="flex justify-between items-center">
                <span className="text-gray-500 dark:text-gray-400">Stocks:</span>
                <div className="flex gap-2">
                  <span className="text-green-600 dark:text-green-400">{categorizedTrades.stocks.long.length}L</span>
                  <span className="text-red-600 dark:text-red-400">{categorizedTrades.stocks.short.length}S</span>
                </div>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-500 dark:text-gray-400">Options:</span>
                <div className="flex gap-2">
                  <span className="text-green-600 dark:text-green-400">{categorizedTrades.options.long.length}L</span>
                  <span className="text-red-600 dark:text-red-400">{categorizedTrades.options.short.length}S</span>
                </div>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-500 dark:text-gray-400">Combos:</span>
                <div className="flex gap-2">
                  <span className="text-green-600 dark:text-green-400">{categorizedTrades.combos.long.length}L</span>
                  <span className="text-red-600 dark:text-red-400">{categorizedTrades.combos.short.length}S</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Filter Bar */}
        <div className="rounded-lg bg-white dark:bg-gray-800 p-4 shadow transition-colors">
          <div className="flex flex-wrap items-center gap-4">
            {/* Ticker Search */}
            <div className="relative flex-1 min-w-[200px] max-w-[300px]">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
              <input
                type="text"
                placeholder="Search ticker..."
                value={filterTicker}
                onChange={(e) => setFilterTicker(e.target.value)}
                className="w-full pl-9 pr-8 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
              />
              {filterTicker && (
                <button
                  onClick={() => setFilterTicker('')}
                  className="absolute right-2 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>

            {/* Strategy Dropdown */}
            <div className="relative min-w-[180px]">
              <select
                value={filterStrategy}
                onChange={(e) => setFilterStrategy(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm appearance-none cursor-pointer"
              >
                <option value="">All Strategies</option>
                {uniqueStrategies.map((strategy) => (
                  <option key={strategy} value={strategy}>
                    {strategy}
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400 pointer-events-none" />
            </div>

            {/* Clear Filters */}
            {(filterTicker || filterStrategy) && (
              <button
                onClick={() => {
                  setFilterTicker('');
                  setFilterStrategy('');
                }}
                className="px-3 py-2 text-sm text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
              >
                Clear filters
              </button>
            )}

            {/* Column Settings Button */}
            <div className="relative">
              <button
                onClick={() => setShowColumnSettings(!showColumnSettings)}
                className={`p-2 rounded-lg transition-colors ${
                  showColumnSettings
                    ? 'bg-blue-100 dark:bg-blue-900/50 text-blue-600 dark:text-blue-400'
                    : 'text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'
                }`}
                title="Column Settings"
              >
                <Settings2 className="h-5 w-5" />
              </button>

              {/* Column Settings Panel */}
              {showColumnSettings && (
                <div className="absolute right-0 top-full mt-2 w-72 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 z-50">
                  <div className="p-3 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
                    <h4 className="font-medium text-gray-900 dark:text-white">Column Settings</h4>
                    <button
                      onClick={resetColumns}
                      className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                    >
                      Reset to Default
                    </button>
                  </div>
                  <div className="p-2 max-h-80 overflow-y-auto">
                    <p className="text-xs text-gray-500 dark:text-gray-400 mb-2 px-2">
                      Drag to reorder. Click eye to show/hide.
                    </p>
                    {columns.filter(c => c.id !== 'expand').map((col) => (
                      <div
                        key={col.id}
                        draggable
                        onDragStart={() => handleDragStart(col.id)}
                        onDragOver={(e) => handleDragOver(e, col.id)}
                        onDragEnd={handleDragEnd}
                        className={`flex items-center gap-2 px-2 py-1.5 rounded hover:bg-gray-100 dark:hover:bg-gray-700 cursor-move ${
                          draggedColumn === col.id ? 'opacity-50' : ''
                        }`}
                      >
                        <GripVertical className="h-4 w-4 text-gray-400 flex-shrink-0" />
                        <span className={`flex-1 text-sm ${col.visible ? 'text-gray-900 dark:text-white' : 'text-gray-400 dark:text-gray-500'}`}>
                          {col.label}
                        </span>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            toggleColumnVisibility(col.id);
                          }}
                          className="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-600"
                        >
                          {col.visible ? (
                            <Eye className="h-4 w-4 text-gray-600 dark:text-gray-400" />
                          ) : (
                            <EyeOff className="h-4 w-4 text-gray-400 dark:text-gray-500" />
                          )}
                        </button>
                      </div>
                    ))}
                  </div>
                  <div className="p-2 border-t border-gray-200 dark:border-gray-700">
                    <p className="text-xs text-gray-500 dark:text-gray-400 text-center">
                      Drag column borders to resize
                    </p>
                  </div>
                </div>
              )}
            </div>

            {/* Results count */}
            <div className="ml-auto text-sm text-gray-500 dark:text-gray-400">
              {filteredTrades.length} of {trades.length} positions
            </div>
          </div>
        </div>

        {/* No positions message */}
        {trades.length === 0 ? (
          <div className="rounded-lg bg-white dark:bg-gray-800 p-12 text-center shadow transition-colors">
            <Briefcase className="mx-auto h-12 w-12 text-gray-400" />
            <h3 className="mt-4 text-lg font-medium text-gray-900 dark:text-white">
              No Open Positions
            </h3>
            <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
              You don't have any open trades at the moment.
            </p>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Stocks Section */}
            <PositionSection
              title="Stocks"
              icon={<Box className="h-5 w-5 text-blue-600" />}
              category="stocks"
              longPositions={categorizedTrades.stocks.long}
              shortPositions={categorizedTrades.stocks.short}
              color="bg-blue-50 dark:bg-blue-900/30 border-b border-blue-100 dark:border-blue-800"
            />

            {/* Options Section */}
            <PositionSection
              title="Options"
              icon={<BarChart3 className="h-5 w-5 text-green-600" />}
              category="options"
              longPositions={categorizedTrades.options.long}
              shortPositions={categorizedTrades.options.short}
              color="bg-green-50 dark:bg-green-900/30 border-b border-green-100 dark:border-green-800"
            />

            {/* Combos Section */}
            <PositionSection
              title="Combos"
              icon={<Layers className="h-5 w-5 text-purple-600" />}
              category="combos"
              longPositions={categorizedTrades.combos.long}
              shortPositions={categorizedTrades.combos.short}
              color="bg-purple-50 dark:bg-purple-900/30 border-b border-purple-100 dark:border-purple-800"
            />
          </div>
        )}
      </div>
    </div>
  );
}
