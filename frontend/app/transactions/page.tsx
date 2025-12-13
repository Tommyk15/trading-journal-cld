'use client';

import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { RefreshCw, Plus, Sparkles, Layers, Download, ChevronLeft, ChevronRight, Filter, X, Check, ChevronDown, ChevronUp, Cog } from 'lucide-react';
import { api } from '@/lib/api/client';
import { formatCurrency, formatDate, formatDateTime } from '@/lib/utils';
import type { Execution, SuggestedGroup, SuggestGroupingResponse } from '@/types';
import { CreateTradeModal } from '@/components/transactions/CreateTradeModal';
import { SuggestGroupingModal } from '@/components/transactions/SuggestGroupingModal';

interface ExecutionListResponse {
  executions: Execution[];
  total: number;
  limit: number;
  offset: number;
}

// Grouped execution type - combines multiple executions with same characteristics
interface GroupedExecution {
  key: string;
  executions: Execution[];
  underlying: string;
  security_type: string;
  option_type?: string;
  side: string;
  open_close_indicator?: string;
  strike?: number;
  expiration?: string;
  execution_time: string;
  totalQuantity: number;
  avgPrice: number;
  totalCommission: number;
  totalNetAmount: number;
  trade_id?: number | null;
  allSameTradeId: boolean;
}

// Helper to get BTC/BTO/STO/STC label
function getActionLabel(side: string, openClose?: string): string {
  // BOT = Buy, SLD = Sell
  // O = Open, C = Close
  if (side === 'BOT') {
    return openClose === 'C' ? 'BTC' : 'BTO';
  } else {
    return openClose === 'C' ? 'STC' : 'STO';
  }
}

export default function TransactionsPage() {
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [showUnassignedOnly, setShowUnassignedOnly] = useState(false);
  const [showOpensOnly, setShowOpensOnly] = useState(true); // Default: only show BTO/STO
  const [underlyingFilter, setUnderlyingFilter] = useState('');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showSuggestModal, setShowSuggestModal] = useState(false);
  const [total, setTotal] = useState(0);
  const [groupSimilar, setGroupSimilar] = useState(true);

  // Suggested groupings state
  const [suggestions, setSuggestions] = useState<SuggestedGroup[]>([]);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(true);
  const [acceptingGroup, setAcceptingGroup] = useState<number | null>(null);
  const [expandedLegs, setExpandedLegs] = useState<Set<string>>(new Set());
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [syncProgress, setSyncProgress] = useState<{
    status: string;
    message: string;
    total?: number;
    current?: number;
  } | null>(null);

  // Reprocess state
  const [reprocessing, setReprocessing] = useState(false);
  const [reprocessMessage, setReprocessMessage] = useState<string | null>(null);

  // Pagination state
  const [usePagination, setUsePagination] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(100);

  // Advanced filters
  const [showFilters, setShowFilters] = useState(false);
  const [strikeFilter, setStrikeFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState<string>(''); // '' | 'C' | 'P' | 'STK'
  const [actionFilter, setActionFilter] = useState<string>(''); // '' | 'BTO' | 'BTC' | 'STO' | 'STC'
  const [expirationFilter, setExpirationFilter] = useState('');
  const [startDateFilter, setStartDateFilter] = useState('');
  const [endDateFilter, setEndDateFilter] = useState('');

  const fetchExecutions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // When not using pagination, fetch all (up to 1000, backend limit)
      const limit = usePagination ? pageSize : 1000;
      const offset = usePagination ? (currentPage - 1) * pageSize : 0;

      const params: {
        limit: number;
        skip?: number;
        unassigned_only?: boolean;
        opens_only?: boolean;
        underlying?: string;
      } = { limit, skip: offset };

      if (showUnassignedOnly) {
        params.unassigned_only = true;
      }
      if (showOpensOnly) {
        params.opens_only = true;
      }
      if (underlyingFilter.trim()) {
        params.underlying = underlyingFilter.trim().toUpperCase();
      }

      const data = (await api.executions.list(params)) as ExecutionListResponse;
      setExecutions(data.executions || []);
      setTotal(data.total || 0);
    } catch (err) {
      console.error('Error fetching executions:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch executions');
    } finally {
      setLoading(false);
    }
  }, [showUnassignedOnly, showOpensOnly, underlyingFilter, usePagination, currentPage, pageSize]);

  useEffect(() => {
    fetchExecutions();
  }, [fetchExecutions]);

  // Reset to page 1 when filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [showUnassignedOnly, showOpensOnly, underlyingFilter, strikeFilter, typeFilter, actionFilter, expirationFilter, startDateFilter, endDateFilter]);

  // Fetch suggested groupings
  const fetchSuggestions = useCallback(async () => {
    setLoadingSuggestions(true);
    try {
      const response = await api.trades.suggestGrouping() as SuggestGroupingResponse;
      setSuggestions(response.groups || []);
    } catch (err) {
      console.error('Error fetching suggestions:', err);
      setSuggestions([]);
    } finally {
      setLoadingSuggestions(false);
    }
  }, []);

  // Fetch suggestions on mount and after creating trades
  useEffect(() => {
    fetchSuggestions();
  }, [fetchSuggestions]);

  // Accept a suggested grouping and create trade
  const handleAcceptGroup = async (group: SuggestedGroup, index: number) => {
    setAcceptingGroup(index);
    try {
      await api.trades.createManual({
        execution_ids: group.execution_ids,
        strategy_type: group.suggested_strategy,
      });
      // Refresh both executions and suggestions
      await Promise.all([fetchExecutions(), fetchSuggestions()]);
    } catch (err) {
      console.error('Error creating trade from suggestion:', err);
      alert(err instanceof Error ? err.message : 'Failed to create trade');
    } finally {
      setAcceptingGroup(null);
    }
  };

  // Sync from IBKR Flex Query with progress
  const handleSyncFromIBKR = async () => {
    setSyncing(true);
    setSyncMessage(null);
    setSyncProgress(null);
    setError(null);
    try {
      await api.executions.syncFlexQueryWithProgress((data) => {
        setSyncProgress({
          status: data.status,
          message: data.message,
          total: data.total,
          current: data.current,
        });

        if (data.status === 'complete') {
          setSyncMessage(data.message);
          setSyncProgress(null);
          fetchExecutions();
        } else if (data.status === 'error') {
          setError(data.message);
          setSyncProgress(null);
        }
      });
    } catch (err) {
      console.error('Error syncing from IBKR:', err);
      setError(err instanceof Error ? err.message : 'Failed to sync from IBKR');
    } finally {
      setSyncing(false);
      setSyncProgress(null);
    }
  };

  // Reprocess all trades using the state machine algorithm
  const handleReprocessAll = async () => {
    if (!confirm('This will delete ALL existing trades and reprocess all executions. Are you sure?')) {
      return;
    }
    setReprocessing(true);
    setReprocessMessage(null);
    setError(null);
    try {
      const result = await api.trades.reprocessAll();
      setReprocessMessage(result.message);
      // Refresh executions and suggestions
      await Promise.all([fetchExecutions(), fetchSuggestions()]);
    } catch (err) {
      console.error('Error reprocessing trades:', err);
      setError(err instanceof Error ? err.message : 'Failed to reprocess trades');
    } finally {
      setReprocessing(false);
    }
  };

  // Apply client-side filters
  const filteredExecutions = useMemo(() => {
    return executions.filter((exec) => {
      // Strike filter
      if (strikeFilter) {
        const strikeNum = parseFloat(strikeFilter);
        if (!isNaN(strikeNum) && exec.strike !== strikeNum) {
          return false;
        }
      }

      // Type filter (Call/Put/Stock)
      if (typeFilter) {
        if (typeFilter === 'STK') {
          if (exec.security_type !== 'STK') return false;
        } else {
          if (exec.option_type !== typeFilter) return false;
        }
      }

      // Action filter (BTO/BTC/STO/STC)
      if (actionFilter) {
        const execAction = getActionLabel(exec.side, exec.open_close_indicator);
        if (execAction !== actionFilter) return false;
      }

      // Expiration filter
      if (expirationFilter && exec.expiration) {
        const expDate = new Date(exec.expiration).toISOString().split('T')[0];
        if (expDate !== expirationFilter) return false;
      } else if (expirationFilter && !exec.expiration) {
        return false;
      }

      // Date range filters
      if (startDateFilter) {
        const execDate = new Date(exec.execution_time).toISOString().split('T')[0];
        if (execDate < startDateFilter) return false;
      }
      if (endDateFilter) {
        const execDate = new Date(exec.execution_time).toISOString().split('T')[0];
        if (execDate > endDateFilter) return false;
      }

      return true;
    });
  }, [executions, strikeFilter, typeFilter, actionFilter, expirationFilter, startDateFilter, endDateFilter]);

  // Selection handlers
  const toggleSelection = (id: number) => {
    const newSelected = new Set(selectedIds);
    if (newSelected.has(id)) {
      newSelected.delete(id);
    } else {
      newSelected.add(id);
    }
    setSelectedIds(newSelected);
  };

  const selectAll = () => {
    if (selectedIds.size === filteredExecutions.length && filteredExecutions.length > 0) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filteredExecutions.map((e) => e.id)));
    }
  };

  const clearSelection = () => {
    setSelectedIds(new Set());
  };

  const clearFilters = () => {
    setStrikeFilter('');
    setTypeFilter('');
    setActionFilter('');
    setExpirationFilter('');
    setStartDateFilter('');
    setEndDateFilter('');
  };

  const hasActiveFilters = strikeFilter || typeFilter || actionFilter || expirationFilter || startDateFilter || endDateFilter;

  // After trade created, refresh and clear selection
  const handleTradeCreated = () => {
    setShowCreateModal(false);
    setShowSuggestModal(false);
    setSelectedIds(new Set());
    fetchExecutions();
  };

  // Get selected executions for modal
  const selectedExecutions = executions.filter((e) => selectedIds.has(e.id));

  // Summary stats from filtered data
  const unassignedCount = filteredExecutions.filter((e) => !e.trade_id).length;
  const assignedCount = filteredExecutions.filter((e) => e.trade_id).length;

  // Group executions by order_id (fills from the same order)
  const groupedExecutions = useMemo(() => {
    if (!groupSimilar) return null;

    const groups: Map<string, GroupedExecution> = new Map();

    // Sort executions by time first
    const sortedExecs = [...filteredExecutions].sort(
      (a, b) => new Date(a.execution_time).getTime() - new Date(b.execution_time).getTime()
    );

    sortedExecs.forEach((exec) => {
      // Use order_id as the primary grouping key (fills from same order)
      // Fall back to individual execution if no order_id
      const key = exec.order_id ? `order_${exec.order_id}` : `exec_${exec.id}`;

      if (groups.has(key)) {
        const group = groups.get(key)!;
        group.executions.push(exec);
        group.totalQuantity += exec.quantity;
        group.totalCommission += Number(exec.commission);
        group.totalNetAmount += Number(exec.net_amount);
        // Check if all executions have the same trade_id
        if (group.allSameTradeId && group.trade_id !== exec.trade_id) {
          group.allSameTradeId = false;
        }
      } else {
        groups.set(key, {
          key,
          executions: [exec],
          underlying: exec.underlying,
          security_type: exec.security_type,
          option_type: exec.option_type,
          side: exec.side,
          open_close_indicator: exec.open_close_indicator,
          strike: exec.strike,
          expiration: exec.expiration,
          execution_time: exec.execution_time,
          totalQuantity: exec.quantity,
          avgPrice: exec.price,
          totalCommission: Number(exec.commission),
          totalNetAmount: Number(exec.net_amount),
          trade_id: exec.trade_id,
          allSameTradeId: true,
        });
      }
    });

    // Calculate average price for groups with multiple executions
    groups.forEach((group) => {
      if (group.executions.length > 1) {
        const totalValue = group.executions.reduce(
          (sum, e) => sum + e.price * e.quantity,
          0
        );
        group.avgPrice = totalValue / group.totalQuantity;
      }
    });

    return Array.from(groups.values()).sort(
      (a, b) => new Date(b.execution_time).getTime() - new Date(a.execution_time).getTime()
    );
  }, [filteredExecutions, groupSimilar]);

  // Pagination calculations
  const displayData = groupSimilar ? groupedExecutions : filteredExecutions;
  const totalPages = usePagination ? Math.ceil(total / pageSize) : 1;

  // Toggle selection for a group (selects/deselects all executions in the group)
  const toggleGroupSelection = (group: GroupedExecution) => {
    const groupIds = group.executions.map((e) => e.id);
    const allSelected = groupIds.every((id) => selectedIds.has(id));

    const newSelected = new Set(selectedIds);
    if (allSelected) {
      // Deselect all in group
      groupIds.forEach((id) => newSelected.delete(id));
    } else {
      // Select all in group
      groupIds.forEach((id) => newSelected.add(id));
    }
    setSelectedIds(newSelected);
  };

  // Check if all executions in a group are selected
  const isGroupSelected = (group: GroupedExecution) => {
    return group.executions.every((e) => selectedIds.has(e.id));
  };

  // Check if some (but not all) executions in a group are selected
  const isGroupPartiallySelected = (group: GroupedExecution) => {
    const selectedCount = group.executions.filter((e) => selectedIds.has(e.id)).length;
    return selectedCount > 0 && selectedCount < group.executions.length;
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 transition-colors">
      {/* Header */}
      <div className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 transition-colors">
        <div className="px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Transactions</h1>
              <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
                View and group your executions into trades
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleSyncFromIBKR}
                disabled={syncing}
                className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed min-w-[180px]"
              >
                {syncing ? (
                  <RefreshCw className="h-4 w-4 animate-spin" />
                ) : (
                  <Download className="h-4 w-4" />
                )}
                {syncProgress && syncProgress.total && syncProgress.current !== undefined
                  ? `Syncing ${syncProgress.current}/${syncProgress.total}`
                  : syncing
                  ? syncProgress?.message || 'Syncing...'
                  : 'Sync from IBKR'}
              </button>
              <button
                onClick={handleReprocessAll}
                disabled={reprocessing}
                className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-purple-600 rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed"
                title="Reprocess all executions into trades using the state machine algorithm"
              >
                {reprocessing ? (
                  <RefreshCw className="h-4 w-4 animate-spin" />
                ) : (
                  <Cog className="h-4 w-4" />
                )}
                {reprocessing ? 'Reprocessing...' : 'Reprocess Trades'}
              </button>
              <button
                onClick={fetchExecutions}
                className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
              >
                <RefreshCw className="h-4 w-4" />
                Refresh
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="p-6 space-y-6">
        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 transition-colors">
            <div className="text-sm font-medium text-gray-700 dark:text-gray-300">
              Total Executions
            </div>
            <div className="mt-1 text-2xl font-semibold text-gray-900 dark:text-white">
              {total}
            </div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 transition-colors">
            <div className="text-sm font-medium text-gray-700 dark:text-gray-300">
              Showing
            </div>
            <div className="mt-1 text-2xl font-semibold text-purple-600 dark:text-purple-400">
              {filteredExecutions.length}
            </div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 transition-colors">
            <div className="text-sm font-medium text-gray-700 dark:text-gray-300">Unassigned</div>
            <div className="mt-1 text-2xl font-semibold text-orange-600 dark:text-orange-400">
              {unassignedCount}
            </div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 transition-colors">
            <div className="text-sm font-medium text-gray-700 dark:text-gray-300">
              Assigned to Trades
            </div>
            <div className="mt-1 text-2xl font-semibold text-green-600 dark:text-green-400">
              {assignedCount}
            </div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 transition-colors">
            <div className="text-sm font-medium text-gray-700 dark:text-gray-300">Selected</div>
            <div className="mt-1 text-2xl font-semibold text-blue-600 dark:text-blue-400">
              {selectedIds.size}
            </div>
          </div>
        </div>

        {/* Action Bar */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 transition-colors">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex flex-wrap items-center gap-4">
              {/* Group Similar Toggle */}
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={groupSimilar}
                  onChange={(e) => setGroupSimilar(e.target.checked)}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <Layers className="h-4 w-4 text-gray-600 dark:text-gray-400" />
                <span className="text-sm text-gray-800 dark:text-gray-200">Group fills</span>
              </label>

              {/* Pagination Toggle */}
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={usePagination}
                  onChange={(e) => setUsePagination(e.target.checked)}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-800 dark:text-gray-200">Use pagination</span>
              </label>

              {/* Opens Only Filter Toggle */}
              <label className="flex items-center gap-2 cursor-pointer" title="Show only opening transactions (BTO/STO). When creating a trade, closes are auto-matched.">
                <input
                  type="checkbox"
                  checked={showOpensOnly}
                  onChange={(e) => setShowOpensOnly(e.target.checked)}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-800 dark:text-gray-200">Opens only</span>
              </label>

              {/* Unassigned Filter Toggle */}
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={showUnassignedOnly}
                  onChange={(e) => setShowUnassignedOnly(e.target.checked)}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-800 dark:text-gray-200">Unassigned only</span>
              </label>

              {/* Underlying Filter */}
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  placeholder="Filter by underlying..."
                  value={underlyingFilter}
                  onChange={(e) => setUnderlyingFilter(e.target.value)}
                  className="rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white text-sm px-3 py-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>

              {/* Toggle Advanced Filters */}
              <button
                onClick={() => setShowFilters(!showFilters)}
                className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  showFilters || hasActiveFilters
                    ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300'
                    : 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                }`}
              >
                <Filter className="h-4 w-4" />
                Filters
                {hasActiveFilters && (
                  <span className="bg-blue-600 text-white rounded-full px-2 py-0.5 text-xs">
                    Active
                  </span>
                )}
              </button>

              {selectedIds.size > 0 && (
                <button
                  onClick={clearSelection}
                  className="text-sm text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 underline"
                >
                  Clear selection
                </button>
              )}
            </div>

            <div className="flex items-center gap-2">
              {selectedIds.size > 0 && (
                <button
                  onClick={() => setShowCreateModal(true)}
                  className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
                >
                  <Plus className="h-4 w-4" />
                  Create Trade ({selectedIds.size})
                </button>
              )}
              <button
                onClick={() => setShowSuggestModal(true)}
                className="flex items-center gap-2 px-4 py-2 bg-gray-600 text-white rounded-lg text-sm font-medium hover:bg-gray-700 transition-colors"
              >
                <Sparkles className="h-4 w-4" />
                Suggest Grouping
              </button>
            </div>
          </div>

          {/* Advanced Filters Panel */}
          {showFilters && (
            <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
              <div className="flex flex-wrap items-end gap-4">
                {/* Strike Filter */}
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-gray-600 dark:text-gray-400">Strike</label>
                  <input
                    type="number"
                    placeholder="e.g. 400"
                    value={strikeFilter}
                    onChange={(e) => setStrikeFilter(e.target.value)}
                    className="w-24 rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white text-sm px-3 py-2 focus:ring-blue-500 focus:border-blue-500"
                  />
                </div>

                {/* Type Filter */}
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-gray-600 dark:text-gray-400">Type</label>
                  <select
                    value={typeFilter}
                    onChange={(e) => setTypeFilter(e.target.value)}
                    className="rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white text-sm px-3 py-2 focus:ring-blue-500 focus:border-blue-500"
                  >
                    <option value="">All</option>
                    <option value="C">Call</option>
                    <option value="P">Put</option>
                    <option value="STK">Stock</option>
                  </select>
                </div>

                {/* Action Filter */}
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-gray-600 dark:text-gray-400">Action</label>
                  <select
                    value={actionFilter}
                    onChange={(e) => setActionFilter(e.target.value)}
                    className="rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white text-sm px-3 py-2 focus:ring-blue-500 focus:border-blue-500"
                  >
                    <option value="">All</option>
                    <option value="BTO">BTO</option>
                    <option value="BTC">BTC</option>
                    <option value="STO">STO</option>
                    <option value="STC">STC</option>
                  </select>
                </div>

                {/* Expiration Filter */}
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-gray-600 dark:text-gray-400">Expiration</label>
                  <input
                    type="date"
                    value={expirationFilter}
                    onChange={(e) => setExpirationFilter(e.target.value)}
                    className="rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white text-sm px-3 py-2 focus:ring-blue-500 focus:border-blue-500"
                  />
                </div>

                {/* Start Date Filter */}
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-gray-600 dark:text-gray-400">From Date</label>
                  <input
                    type="date"
                    value={startDateFilter}
                    onChange={(e) => setStartDateFilter(e.target.value)}
                    className="rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white text-sm px-3 py-2 focus:ring-blue-500 focus:border-blue-500"
                  />
                </div>

                {/* End Date Filter */}
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-gray-600 dark:text-gray-400">To Date</label>
                  <input
                    type="date"
                    value={endDateFilter}
                    onChange={(e) => setEndDateFilter(e.target.value)}
                    className="rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white text-sm px-3 py-2 focus:ring-blue-500 focus:border-blue-500"
                  />
                </div>

                {/* Clear Filters */}
                {hasActiveFilters && (
                  <button
                    onClick={clearFilters}
                    className="flex items-center gap-1 px-3 py-2 text-sm text-red-600 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300"
                  >
                    <X className="h-4 w-4" />
                    Clear Filters
                  </button>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Suggested Groupings Section */}
        {suggestions.length > 0 && (
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden transition-colors">
            <button
              onClick={() => setShowSuggestions(!showSuggestions)}
              className="w-full px-4 py-3 flex items-center justify-between bg-gradient-to-r from-purple-50 to-indigo-50 dark:from-purple-900/30 dark:to-indigo-900/30 hover:from-purple-100 hover:to-indigo-100 dark:hover:from-purple-900/40 dark:hover:to-indigo-900/40 transition-colors"
            >
              <div className="flex items-center gap-3">
                <Sparkles className="h-5 w-5 text-purple-600 dark:text-purple-400" />
                <span className="font-medium text-gray-900 dark:text-white">
                  Suggested Groupings
                </span>
                <span className="bg-purple-100 dark:bg-purple-900/50 text-purple-700 dark:text-purple-300 px-2 py-0.5 rounded-full text-xs font-medium">
                  {suggestions.length} suggestion{suggestions.length !== 1 ? 's' : ''}
                </span>
              </div>
              {showSuggestions ? (
                <ChevronUp className="h-5 w-5 text-gray-500 dark:text-gray-400" />
              ) : (
                <ChevronDown className="h-5 w-5 text-gray-500 dark:text-gray-400" />
              )}
            </button>

            {showSuggestions && (
              <div className="p-4 space-y-3 max-h-96 overflow-y-auto">
                {loadingSuggestions ? (
                  <div className="flex items-center justify-center py-4 text-gray-500 dark:text-gray-400">
                    <RefreshCw className="h-5 w-5 animate-spin mr-2" />
                    Loading suggestions...
                  </div>
                ) : (
                  suggestions.map((group, index) => {
                    const toggleLegExpanded = (legKey: string) => {
                      const newExpanded = new Set(expandedLegs);
                      if (newExpanded.has(legKey)) {
                        newExpanded.delete(legKey);
                      } else {
                        newExpanded.add(legKey);
                      }
                      setExpandedLegs(newExpanded);
                    };

                    return (
                      <div
                        key={index}
                        className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 hover:border-purple-300 dark:hover:border-purple-600 transition-colors"
                      >
                        <div className="flex items-start gap-4">
                          {/* Left: Underlying, Strategy, Status, and Info */}
                          <div className="w-48 flex-shrink-0">
                            <span className="font-semibold text-lg text-gray-900 dark:text-white">
                              {group.underlying}
                            </span>
                            <div className="mt-1">
                              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-800 dark:bg-indigo-900/50 dark:text-indigo-200">
                                {group.suggested_strategy}
                              </span>
                            </div>
                            <div className="mt-1">
                              <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                                group.status === 'CLOSED'
                                  ? 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300'
                                  : 'bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300'
                              }`}>
                                {group.status}
                              </span>
                            </div>
                            <div className="mt-2 text-xs text-gray-600 dark:text-gray-400 space-y-1">
                              <div>{group.num_executions} execution{group.num_executions !== 1 ? 's' : ''}</div>
                              {group.open_date && (
                                <div>Opened: {formatDate(group.open_date)}</div>
                              )}
                              {group.status === 'CLOSED' && group.total_pnl !== undefined && (
                                <div className={group.total_pnl >= 0 ? 'text-green-600 dark:text-green-400 font-medium' : 'text-red-600 dark:text-red-400 font-medium'}>
                                  P/L: {formatCurrency(group.total_pnl)}
                                </div>
                              )}
                            </div>
                          </div>

                          {/* Middle: Legs displayed vertically with expandable fills */}
                          <div className="flex-1 space-y-2">
                            {group.legs.map((leg, legIndex) => {
                              const legKey = `${index}-${legIndex}`;
                              const isExpanded = expandedLegs.has(legKey);
                              const hasFills = leg.fills && leg.fills.length > 0;

                              return (
                                <div key={legIndex} className="border border-gray-100 dark:border-gray-700 rounded-lg overflow-hidden">
                                  {/* Leg header - clickable to expand */}
                                  <button
                                    onClick={() => hasFills && toggleLegExpanded(legKey)}
                                    disabled={!hasFills}
                                    className={`w-full px-3 py-2 flex items-center justify-between text-left ${
                                      leg.option_type === 'P'
                                        ? 'bg-red-50 dark:bg-red-900/20'
                                        : leg.option_type === 'C'
                                        ? 'bg-green-50 dark:bg-green-900/20'
                                        : 'bg-gray-50 dark:bg-gray-800'
                                    } ${hasFills ? 'cursor-pointer hover:opacity-80' : 'cursor-default'}`}
                                  >
                                    <div className="flex items-center gap-2">
                                      <span className={`font-medium text-sm ${
                                        leg.option_type === 'P'
                                          ? 'text-red-700 dark:text-red-300'
                                          : leg.option_type === 'C'
                                          ? 'text-green-700 dark:text-green-300'
                                          : 'text-gray-700 dark:text-gray-300'
                                      }`}>
                                        {leg.total_quantity > 0 ? '+' : ''}{leg.total_quantity}x {leg.option_type === 'C' ? 'Call' : leg.option_type === 'P' ? 'Put' : 'Stock'}
                                      </span>
                                      {leg.strike && (
                                        <span className="text-sm text-gray-600 dark:text-gray-400">
                                          ${leg.strike}
                                        </span>
                                      )}
                                      {leg.expiration && (
                                        <span className="text-sm text-gray-500 dark:text-gray-500">
                                          {formatDate(leg.expiration)}
                                        </span>
                                      )}
                                      {hasFills && (
                                        <span className="text-xs text-gray-500 dark:text-gray-500">
                                          ({leg.fills.length} fill{leg.fills.length !== 1 ? 's' : ''})
                                        </span>
                                      )}
                                    </div>
                                    {hasFills && (
                                      isExpanded ? (
                                        <ChevronUp className="h-4 w-4 text-gray-400" />
                                      ) : (
                                        <ChevronDown className="h-4 w-4 text-gray-400" />
                                      )
                                    )}
                                  </button>

                                  {/* Expanded fills */}
                                  {isExpanded && hasFills && (
                                    <div className="border-t border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800">
                                      <table className="w-full text-xs">
                                        <thead className="bg-gray-50 dark:bg-gray-900">
                                          <tr>
                                            <th className="px-2 py-1 text-left text-gray-600 dark:text-gray-400">Action</th>
                                            <th className="px-2 py-1 text-right text-gray-600 dark:text-gray-400">Qty</th>
                                            <th className="px-2 py-1 text-right text-gray-600 dark:text-gray-400">Price</th>
                                            <th className="px-2 py-1 text-right text-gray-600 dark:text-gray-400">Net</th>
                                            <th className="px-2 py-1 text-left text-gray-600 dark:text-gray-400">Time</th>
                                          </tr>
                                        </thead>
                                        <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                                          {leg.fills.map((fill, fillIndex) => (
                                            <tr key={fillIndex} className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                                              <td className="px-2 py-1">
                                                <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${
                                                  fill.action.startsWith('B')
                                                    ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300'
                                                    : 'bg-orange-100 text-orange-700 dark:bg-orange-900/50 dark:text-orange-300'
                                                }`}>
                                                  {fill.action}
                                                </span>
                                              </td>
                                              <td className="px-2 py-1 text-right text-gray-700 dark:text-gray-300">
                                                {fill.quantity}
                                              </td>
                                              <td className="px-2 py-1 text-right text-gray-700 dark:text-gray-300">
                                                {formatCurrency(fill.price)}
                                              </td>
                                              <td className="px-2 py-1 text-right text-gray-700 dark:text-gray-300">
                                                {formatCurrency(fill.net_amount)}
                                              </td>
                                              <td className="px-2 py-1 text-gray-500 dark:text-gray-500 whitespace-nowrap">
                                                {fill.execution_time.split(' ')[0]}
                                              </td>
                                            </tr>
                                          ))}
                                        </tbody>
                                      </table>
                                    </div>
                                  )}
                                </div>
                              );
                            })}
                          </div>

                          {/* Right: Accept button */}
                          <div className="flex-shrink-0">
                            <button
                              onClick={() => handleAcceptGroup(group, index)}
                              disabled={acceptingGroup === index}
                              className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
                            >
                              {acceptingGroup === index ? (
                                <>
                                  <RefreshCw className="h-4 w-4 animate-spin" />
                                  Creating...
                                </>
                              ) : (
                                <>
                                  <Check className="h-4 w-4" />
                                  Accept
                                </>
                              )}
                            </button>
                          </div>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            )}
          </div>
        )}

        {/* Pagination Controls (when enabled) */}
        {usePagination && (
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 transition-colors">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <span className="text-sm text-gray-700 dark:text-gray-300">
                  Page {currentPage} of {totalPages} ({total} total executions)
                </span>
                <select
                  value={pageSize}
                  onChange={(e) => {
                    setPageSize(Number(e.target.value));
                    setCurrentPage(1);
                  }}
                  className="rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white text-sm px-3 py-1 focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value={50}>50 per page</option>
                  <option value={100}>100 per page</option>
                  <option value={250}>250 per page</option>
                  <option value={500}>500 per page</option>
                </select>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setCurrentPage(1)}
                  disabled={currentPage === 1}
                  className="px-3 py-1 text-sm rounded-lg border border-gray-300 dark:border-gray-600 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50 dark:hover:bg-gray-700"
                >
                  First
                </button>
                <button
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className="p-1 rounded-lg border border-gray-300 dark:border-gray-600 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50 dark:hover:bg-gray-700"
                >
                  <ChevronLeft className="h-5 w-5" />
                </button>
                <span className="px-4 py-1 text-sm font-medium text-gray-900 dark:text-white">
                  {currentPage}
                </span>
                <button
                  onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                  className="p-1 rounded-lg border border-gray-300 dark:border-gray-600 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50 dark:hover:bg-gray-700"
                >
                  <ChevronRight className="h-5 w-5" />
                </button>
                <button
                  onClick={() => setCurrentPage(totalPages)}
                  disabled={currentPage === totalPages}
                  className="px-3 py-1 text-sm rounded-lg border border-gray-300 dark:border-gray-600 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50 dark:hover:bg-gray-700"
                >
                  Last
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Sync Progress Bar */}
        {syncing && syncProgress && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-blue-700">
                {syncProgress.message}
              </span>
              {syncProgress.total && syncProgress.current !== undefined && (
                <span className="text-sm text-blue-600">
                  {syncProgress.current}/{syncProgress.total}
                </span>
              )}
            </div>
            {syncProgress.total && syncProgress.current !== undefined && (
              <div className="w-full bg-blue-200 rounded-full h-2">
                <div
                  className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                  style={{
                    width: `${(syncProgress.current / syncProgress.total) * 100}%`,
                  }}
                />
              </div>
            )}
          </div>
        )}

        {/* Error Display */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
            {error}
          </div>
        )}

        {/* Sync Success Message */}
        {syncMessage && (
          <div className="bg-green-50 border border-green-200 rounded-lg p-4 text-green-700 flex items-center justify-between">
            <span>{syncMessage}</span>
            <button
              onClick={() => setSyncMessage(null)}
              className="text-green-600 hover:text-green-800"
            >
              &times;
            </button>
          </div>
        )}

        {/* Reprocess Success Message */}
        {reprocessMessage && (
          <div className="bg-purple-50 border border-purple-200 rounded-lg p-4 text-purple-700 flex items-center justify-between">
            <span>{reprocessMessage}</span>
            <button
              onClick={() => setReprocessMessage(null)}
              className="text-purple-600 hover:text-purple-800"
            >
              &times;
            </button>
          </div>
        )}

        {/* Executions Table */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden transition-colors">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead className="bg-gray-50 dark:bg-gray-900">
                <tr>
                  <th className="px-4 py-3 w-12">
                    <input
                      type="checkbox"
                      checked={
                        selectedIds.size === filteredExecutions.length &&
                        filteredExecutions.length > 0
                      }
                      onChange={selectAll}
                      className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                    />
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider">
                    Date
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider">
                    Underlying
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider">
                    Type
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider">
                    Action
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider">
                    Qty
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider">
                    Strike
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider">
                    Expiration
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider">
                    Price
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider">
                    Commission
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider">
                    Net Amount
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider">
                    Trade
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                {loading ? (
                  <tr>
                    <td colSpan={12} className="px-4 py-8 text-center">
                      <div className="flex items-center justify-center gap-2 text-gray-600 dark:text-gray-400">
                        <RefreshCw className="h-5 w-5 animate-spin" />
                        Loading executions...
                      </div>
                    </td>
                  </tr>
                ) : filteredExecutions.length === 0 ? (
                  <tr>
                    <td
                      colSpan={12}
                      className="px-4 py-8 text-center text-gray-600 dark:text-gray-400"
                    >
                      {executions.length === 0
                        ? 'No executions found. Import data via Settings page.'
                        : 'No executions match the current filters.'}
                    </td>
                  </tr>
                ) : groupSimilar && groupedExecutions ? (
                  // Grouped view
                  groupedExecutions.map((group) => (
                    <tr
                      key={group.key}
                      className={`cursor-pointer transition-colors hover:bg-gray-50 dark:hover:bg-gray-700 ${
                        isGroupSelected(group)
                          ? 'bg-blue-50 dark:bg-blue-900/30'
                          : isGroupPartiallySelected(group)
                          ? 'bg-blue-25 dark:bg-blue-900/15'
                          : ''
                      }`}
                      onClick={() => toggleGroupSelection(group)}
                    >
                      <td
                        className="px-4 py-3"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <input
                          type="checkbox"
                          checked={isGroupSelected(group)}
                          ref={(el) => {
                            if (el) {
                              el.indeterminate = isGroupPartiallySelected(group);
                            }
                          }}
                          onChange={() => toggleGroupSelection(group)}
                          className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                        />
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-900 dark:text-gray-100 whitespace-nowrap">
                        {formatDateTime(group.execution_time)}
                      </td>
                      <td className="px-4 py-3 text-sm font-medium text-gray-900 dark:text-white">
                        {group.underlying}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                        {group.security_type === 'OPT' ? (
                          <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                            group.option_type === 'P'
                              ? 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-200'
                              : 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-200'
                          }`}>
                            {group.option_type === 'C' ? 'Call' : 'Put'}
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200">
                            Stock
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                            group.open_close_indicator === 'C'
                              ? 'bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-200'
                              : 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-200'
                          }`}
                        >
                          {getActionLabel(group.side, group.open_close_indicator)}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-900 dark:text-gray-100 text-right">
                        <span className="font-medium">{group.totalQuantity}</span>
                        {group.executions.length > 1 && (
                          <span className="ml-1 text-xs text-gray-600 dark:text-gray-400">
                            ({group.executions.length} fills)
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-900 dark:text-gray-100 text-right">
                        {group.strike ? `$${group.strike}` : '-'}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300 whitespace-nowrap">
                        {group.expiration ? formatDate(group.expiration) : '-'}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-900 dark:text-gray-100 text-right">
                        {group.executions.length > 1 ? (
                          <span title="Average price across fills">
                            ~{formatCurrency(group.avgPrice)}
                          </span>
                        ) : (
                          formatCurrency(group.avgPrice)
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300 text-right">
                        ${group.totalCommission.toFixed(2)}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-900 dark:text-gray-100 text-right font-medium">
                        {formatCurrency(group.totalNetAmount)}
                      </td>
                      <td
                        className="px-4 py-3 text-sm"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {group.allSameTradeId && group.trade_id ? (
                          <a
                            href={`/trades?id=${group.trade_id}`}
                            className="text-blue-600 hover:text-blue-800 hover:underline"
                          >
                            Trade #{group.trade_id}
                          </a>
                        ) : group.allSameTradeId ? (
                          <span className="text-gray-500 dark:text-gray-400">Unassigned</span>
                        ) : (
                          <span className="text-yellow-700 dark:text-yellow-400 text-xs">Mixed</span>
                        )}
                      </td>
                    </tr>
                  ))
                ) : (
                  // Individual view
                  filteredExecutions.map((exec) => (
                    <tr
                      key={exec.id}
                      className={`cursor-pointer transition-colors hover:bg-gray-50 dark:hover:bg-gray-700 ${
                        selectedIds.has(exec.id) ? 'bg-blue-50 dark:bg-blue-900/30' : ''
                      }`}
                      onClick={() => toggleSelection(exec.id)}
                    >
                      <td
                        className="px-4 py-3"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <input
                          type="checkbox"
                          checked={selectedIds.has(exec.id)}
                          onChange={() => toggleSelection(exec.id)}
                          className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                        />
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-900 dark:text-gray-100 whitespace-nowrap">
                        {formatDateTime(exec.execution_time)}
                      </td>
                      <td className="px-4 py-3 text-sm font-medium text-gray-900 dark:text-white">
                        {exec.underlying}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                        {exec.security_type === 'OPT' ? (
                          <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                            exec.option_type === 'P'
                              ? 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-200'
                              : 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-200'
                          }`}>
                            {exec.option_type === 'C' ? 'Call' : 'Put'}
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200">
                            Stock
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                            exec.open_close_indicator === 'C'
                              ? 'bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-200'
                              : 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-200'
                          }`}
                        >
                          {getActionLabel(exec.side, exec.open_close_indicator)}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-900 dark:text-gray-100 text-right">
                        {exec.quantity}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-900 dark:text-gray-100 text-right">
                        {exec.strike ? `$${exec.strike}` : '-'}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300 whitespace-nowrap">
                        {exec.expiration ? formatDate(exec.expiration) : '-'}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-900 dark:text-gray-100 text-right">
                        {formatCurrency(exec.price)}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300 text-right">
                        ${Number(exec.commission).toFixed(2)}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-900 dark:text-gray-100 text-right font-medium">
                        {formatCurrency(exec.net_amount)}
                      </td>
                      <td
                        className="px-4 py-3 text-sm"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {exec.trade_id ? (
                          <a
                            href={`/trades?id=${exec.trade_id}`}
                            className="text-blue-600 hover:text-blue-800 hover:underline"
                          >
                            Trade #{exec.trade_id}
                          </a>
                        ) : (
                          <span className="text-gray-500 dark:text-gray-400">Unassigned</span>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Bottom pagination (when enabled and showing all) */}
        {usePagination && totalPages > 1 && (
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 transition-colors">
            <div className="flex items-center justify-center gap-2">
              <button
                onClick={() => setCurrentPage(1)}
                disabled={currentPage === 1}
                className="px-3 py-1 text-sm rounded-lg border border-gray-300 dark:border-gray-600 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50 dark:hover:bg-gray-700"
              >
                First
              </button>
              <button
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="p-1 rounded-lg border border-gray-300 dark:border-gray-600 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50 dark:hover:bg-gray-700"
              >
                <ChevronLeft className="h-5 w-5" />
              </button>
              <span className="px-4 py-1 text-sm font-medium text-gray-900 dark:text-white">
                Page {currentPage} of {totalPages}
              </span>
              <button
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                className="p-1 rounded-lg border border-gray-300 dark:border-gray-600 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50 dark:hover:bg-gray-700"
              >
                <ChevronRight className="h-5 w-5" />
              </button>
              <button
                onClick={() => setCurrentPage(totalPages)}
                disabled={currentPage === totalPages}
                className="px-3 py-1 text-sm rounded-lg border border-gray-300 dark:border-gray-600 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50 dark:hover:bg-gray-700"
              >
                Last
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Create Trade Modal */}
      {showCreateModal && (
        <CreateTradeModal
          executionIds={Array.from(selectedIds)}
          executions={selectedExecutions}
          onClose={() => setShowCreateModal(false)}
          onCreated={handleTradeCreated}
        />
      )}

      {/* Suggest Grouping Modal */}
      {showSuggestModal && (
        <SuggestGroupingModal
          onClose={() => setShowSuggestModal(false)}
          onApply={handleTradeCreated}
        />
      )}
    </div>
  );
}
