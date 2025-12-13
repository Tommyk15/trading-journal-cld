'use client';

import React, { useEffect, useState } from 'react';
import { Header } from '@/components/layout/Header';
import { api } from '@/lib/api/client';
import { formatCurrency, formatDate, getPnlColor } from '@/lib/utils';
import type { Trade } from '@/types';
import { ChevronDown, ChevronRight, Merge, AlertCircle } from 'lucide-react';

export default function TradesPage() {
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
  });
  const [underlyingInput, setUnderlyingInput] = useState('');

  async function fetchTrades() {
    try {
      setLoading(true);
      const params: any = { limit: 1000 };
      if (filters.strategy) params.strategy_type = filters.strategy;
      if (filters.underlying_symbol) params.underlying = filters.underlying_symbol.toUpperCase();
      if (filters.status) params.status = filters.status;

      const data: any = await api.trades.list(params);
      const fetchedTrades = data.trades || [];
      setTrades(fetchedTrades);

      // Fetch executions for all trades immediately
      const executionsMap: Record<number, any[]> = {};
      await Promise.all(
        fetchedTrades.map(async (trade: any) => {
          try {
            const response = await fetch(`http://localhost:8000/api/v1/trades/${trade.id}/executions`);
            const execData = await response.json();
            executionsMap[trade.id] = execData.executions;
          } catch (error) {
            console.error(`Error fetching executions for trade ${trade.id}:`, error);
          }
        })
      );
      setTradeExecutions(executionsMap);
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
    // Group by strike + option_type + expiration
    const groups: Record<string, any[]> = {};

    executions.forEach((exec) => {
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
      const openingExecs = execs.filter(e => e.open_close_indicator === 'O');
      const closingExecs = execs.filter(e => e.open_close_indicator === 'C');

      // Determine if this is a long or short position
      // Long: BTO (open with buy) + STC (close with sell)
      // Short: STO (open with sell) + BTC (close with buy)
      const isLongPosition = openingExecs.some(e => e.side === 'BOT');

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
      const multiplier = execs[0].multiplier || 100;

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
    // Group by strike/type/expiration/action (keep BTO and STO separate)
    const actionGroups: Record<string, any[]> = {};

    executions.forEach((exec) => {
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
      <div>
        <Header title="Trades" subtitle="View your complete trade history" />
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
      <Header title="Trades" subtitle="View your complete trade history" />

      <div className="p-6 space-y-6">
        {/* Filters */}
        <div className="flex items-center gap-4">
          <select
            value={filters.strategy}
            onChange={(e) =>
              setFilters({ ...filters, strategy: e.target.value })
            }
            className="block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
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
            className="block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
          />

          <select
            value={filters.status}
            onChange={(e) =>
              setFilters({ ...filters, status: e.target.value })
            }
            className="block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
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
        </div>

        {/* Merge Error */}
        {mergeError && (
          <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-red-800 text-sm">
            <AlertCircle className="h-5 w-5 flex-shrink-0" />
            {mergeError}
          </div>
        )}

        {/* Selection Info */}
        {selectedTradeIds.size > 0 && (
          <div className="flex items-center gap-4 p-3 bg-blue-50 border border-blue-200 rounded-lg text-blue-800 text-sm">
            <span>{selectedTradeIds.size} trade{selectedTradeIds.size !== 1 ? 's' : ''} selected</span>
            <button
              onClick={() => setSelectedTradeIds(new Set())}
              className="text-blue-600 hover:text-blue-800 underline"
            >
              Clear selection
            </button>
          </div>
        )}

        {/* Summary Cards */}
        <div className="grid gap-6 md:grid-cols-4">
          <div className="rounded-lg bg-white p-6 shadow">
            <h3 className="text-sm font-medium text-gray-600">Total Trades</h3>
            <p className="mt-2 text-3xl font-bold text-gray-900">
              {trades.length}
            </p>
          </div>
          <div className="rounded-lg bg-white p-6 shadow">
            <h3 className="text-sm font-medium text-gray-600">Open Trades</h3>
            <p className="mt-2 text-3xl font-bold text-blue-600">
              {openTrades}
            </p>
          </div>
          <div className="rounded-lg bg-white p-6 shadow">
            <h3 className="text-sm font-medium text-gray-600">Closed Trades</h3>
            <p className="mt-2 text-3xl font-bold text-gray-600">
              {closedTrades}
            </p>
          </div>
          <div className="rounded-lg bg-white p-6 shadow">
            <h3 className="text-sm font-medium text-gray-600">Total P&L</h3>
            <p className={`mt-2 text-3xl font-bold ${getPnlColor(totalPnl)}`}>
              {formatCurrency(totalPnl)}
            </p>
          </div>
        </div>

        {/* Trades Table */}
        <div className="rounded-lg bg-white shadow overflow-hidden">
          <div className="overflow-x-auto max-h-[calc(100vh-300px)] relative">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50 sticky top-0 z-10">
                <tr>
                  <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider w-12">
                    <input
                      type="checkbox"
                      checked={selectedTradeIds.size === trades.length && trades.length > 0}
                      onChange={toggleSelectAll}
                      className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                    />
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-12"></th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Date</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Ticker</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Qty</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Strategy</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Strike</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Expiration</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">DTE</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Price</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Value</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Commission</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">P&L</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {trades.length === 0 ? (
                  <tr>
                    <td colSpan={14} className="px-6 py-12 text-center text-gray-500">
                      No trades found matching your filters.
                    </td>
                  </tr>
                ) : (
                  trades.map((trade: any) => {
                    const executions = tradeExecutions[trade.id];
                    const aggregated = executions ? aggregateExecutions(executions) : [];

                    // Calculate strikes for display (e.g., "250/270")
                    const strikes = aggregated.length > 0
                      ? [...new Set(aggregated.map(g => parseFloat(g.strike)))]
                          .sort((a, b) => a - b)
                          .join('/')
                      : '-';

                    // Get expiration
                    const expiration = aggregated.length > 0 && aggregated[0].expiration
                      ? new Date(aggregated[0].expiration)
                      : null;

                    // Calculate DTE (Days to Expiration)
                    const dte = expiration
                      ? Math.ceil((expiration.getTime() - new Date().getTime()) / (1000 * 60 * 60 * 24))
                      : null;

                    // Calculate net price using backend's opening_cost (which accounts for net debit/credit)
                    // Quantity is the minimum of all legs (for spreads)
                    const qty = aggregated.length > 0
                      ? Math.min(...aggregated.map(g => g.totalQuantity))
                      : 0;

                    // Use opening_cost from backend (net debit for spreads) divided by quantity and multiplier
                    const netPrice = qty > 0
                      ? parseFloat(trade.opening_cost) / qty / 100
                      : 0;

                    const netValue = aggregated.reduce((sum, g) => sum + g.totalValue, 0);
                    const totalCommission = aggregated.reduce((sum, g) => sum + g.totalCommission, 0);

                    return (
                    <React.Fragment key={trade.id}>
                      <tr className={`hover:bg-gray-50 ${selectedTradeIds.has(trade.id) ? 'bg-blue-50' : ''}`}>
                        <td className="px-4 py-3 whitespace-nowrap text-center">
                          <input
                            type="checkbox"
                            checked={selectedTradeIds.has(trade.id)}
                            onChange={() => toggleTradeSelection(trade.id)}
                            className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                          />
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap">
                          <button
                            onClick={() => toggleTradeExpansion(trade.id)}
                            className="text-gray-400 hover:text-gray-600"
                          >
                            {expandedTrades.has(trade.id) ? (
                              <ChevronDown className="h-4 w-4" />
                            ) : (
                              <ChevronRight className="h-4 w-4" />
                            )}
                          </button>
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap">
                          <span className={`inline-flex rounded-full px-2 py-1 text-xs font-semibold ${
                            trade.status === 'CLOSED'
                              ? 'bg-gray-100 text-gray-800'
                              : 'bg-blue-100 text-blue-800'
                          }`}>
                            {trade.status}
                          </span>
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900">
                          {formatDate(trade.opened_at)}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-sm font-medium text-gray-900">
                          {trade.underlying}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900 text-right">
                          {qty}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900">
                          {formatStrategyName(trade, executions)}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900">
                          {strikes}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900">
                          {expiration ? formatDate(expiration.toISOString()) : '-'}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900 text-right">
                          {dte !== null ? dte : '-'}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900 text-right">
                          {formatCurrency(netPrice)}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900 text-right">
                          {formatCurrency(netValue)}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900 text-right">
                          ${totalCommission.toFixed(2)}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-sm text-right">
                          <span className={getPnlColor(parseFloat(trade.realized_pnl) || 0)}>
                            {trade.realized_pnl ? formatCurrency(parseFloat(trade.realized_pnl)) : '-'}
                          </span>
                        </td>
                      </tr>
                      {expandedTrades.has(trade.id) && (
                        <tr key={`${trade.id}-executions`}>
                          <td colSpan={14} className="px-6 py-4 bg-gray-50">
                            {tradeExecutions[trade.id] ? (
                              <table className="min-w-full">
                                <thead>
                                  <tr className="border-b border-gray-300">
                                    <th className="px-3 py-2 text-left text-xs font-semibold text-gray-700">Date Opened</th>
                                    <th className="px-3 py-2 text-left text-xs font-semibold text-gray-700">Date Closed</th>
                                    <th className="px-3 py-2 text-left text-xs font-semibold text-gray-700">Action</th>
                                    <th className="px-3 py-2 text-left text-xs font-semibold text-gray-700">Qty</th>
                                    <th className="px-3 py-2 text-left text-xs font-semibold text-gray-700">Type</th>
                                    <th className="px-3 py-2 text-left text-xs font-semibold text-gray-700">Strike</th>
                                    <th className="px-3 py-2 text-left text-xs font-semibold text-gray-700">Expiration</th>
                                    <th className="px-3 py-2 text-right text-xs font-semibold text-gray-700">Open Price</th>
                                    <th className="px-3 py-2 text-right text-xs font-semibold text-gray-700">Close Price</th>
                                    <th className="px-3 py-2 text-right text-xs font-semibold text-gray-700">Commission</th>
                                    <th className="px-3 py-2 text-right text-xs font-semibold text-gray-700">Net P&L</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {pairTransactions(tradeExecutions[trade.id]).map((pair: any, idx: number) => (
                                    <tr key={idx} className="border-b border-gray-200">
                                      <td className="px-3 py-2 text-sm text-gray-900">
                                        {pair.dateOpened ? formatDate(pair.dateOpened.toISOString()) : '-'}
                                      </td>
                                      <td className="px-3 py-2 text-sm text-gray-900">
                                        {pair.dateClosed ? formatDate(pair.dateClosed.toISOString()) :
                                          <span className="text-blue-600 font-semibold">OPEN</span>}
                                      </td>
                                      <td className="px-3 py-2 text-sm">
                                        <span className={`font-semibold ${pair.action.includes('Long') ? 'text-green-700' : 'text-red-700'}`}>
                                          {pair.action.includes('Long') ? '🟢' : '🔴'} {pair.action}
                                        </span>
                                      </td>
                                      <td className="px-3 py-2 text-sm font-medium text-gray-900">{pair.quantity}</td>
                                      <td className="px-3 py-2 text-sm text-gray-900">{pair.type}</td>
                                      <td className="px-3 py-2 text-sm font-medium text-gray-900">${pair.strike}</td>
                                      <td className="px-3 py-2 text-sm text-gray-900">{formatDate(pair.expiration)}</td>
                                      <td className="px-3 py-2 text-sm font-medium text-gray-900 text-right">
                                        {pair.openPrice !== null ? `$${pair.openPrice.toFixed(2)}` : '-'}
                                      </td>
                                      <td className="px-3 py-2 text-sm font-medium text-gray-900 text-right">
                                        {pair.closePrice !== null ? `$${pair.closePrice.toFixed(2)}` : '-'}
                                      </td>
                                      <td className="px-3 py-2 text-sm text-gray-900 text-right">
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
                                  <tr className="border-t-2 border-gray-400 bg-gray-100">
                                    <td colSpan={9} className="px-3 py-2 text-sm font-bold text-gray-900">
                                      TOTAL
                                    </td>
                                    <td className="px-3 py-2 text-sm font-bold text-gray-900 text-right">
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
                              <div className="text-sm text-gray-900">Loading executions...</div>
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
