'use client';

import React, { useEffect, useState } from 'react';
import { Header, ActionButton } from '@/components/layout/Header';
import { api } from '@/lib/api/client';
import { formatCurrency, formatDate, getPnlColor } from '@/lib/utils';
import { RefreshCw, ChevronDown, ChevronRight, TrendingUp, TrendingDown, Briefcase, Layers, BarChart3, Box } from 'lucide-react';

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

export default function PositionsPage() {
  const [trades, setTrades] = useState<OpenTrade[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedTrades, setExpandedTrades] = useState<Set<number>>(new Set());
  const [tradeExecutions, setTradeExecutions] = useState<Record<number, TradeExecution[]>>({});
  const [collapsedSections, setCollapsedSections] = useState<Set<PositionCategory>>(new Set());

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
    } catch (error) {
      console.error('Error fetching open trades:', error);
      setTrades([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
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

  // Get categorized trades
  const categorizedTrades = {
    stocks: trades.filter(t => categorizePosition(t, tradeExecutions[t.id]) === 'stocks'),
    options: trades.filter(t => categorizePosition(t, tradeExecutions[t.id]) === 'options'),
    combos: trades.filter(t => categorizePosition(t, tradeExecutions[t.id]) === 'combos'),
  };

  // Toggle section collapse
  function toggleSection(section: PositionCategory) {
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
    const actionGroups: Record<string, TradeExecution[]> = {};

    executions.forEach((exec) => {
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
    const groups: Record<string, TradeExecution[]> = {};

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
      const multiplier = execs[0].multiplier || 100;

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

  // Section component
  function PositionSection({
    title,
    icon,
    category,
    positions,
    color
  }: {
    title: string;
    icon: React.ReactNode;
    category: PositionCategory;
    positions: OpenTrade[];
    color: string;
  }) {
    const isCollapsed = collapsedSections.has(category);
    const sectionCost = positions.reduce((sum, t) => sum + parseFloat(t.opening_cost || '0'), 0);

    return (
      <div className="rounded-lg bg-white shadow overflow-hidden">
        {/* Section Header */}
        <div
          className={`px-4 py-3 ${color} flex items-center justify-between cursor-pointer`}
          onClick={() => toggleSection(category)}
        >
          <div className="flex items-center gap-3">
            {icon}
            <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
            <span className="px-2 py-0.5 rounded-full bg-white/50 text-sm font-medium">
              {positions.length}
            </span>
          </div>
          <div className="flex items-center gap-4">
            <span className={`text-sm font-medium ${sectionCost >= 0 ? 'text-green-700' : 'text-red-700'}`}>
              {formatCurrency(sectionCost)}
            </span>
            {isCollapsed ? (
              <ChevronRight className="h-5 w-5 text-gray-600" />
            ) : (
              <ChevronDown className="h-5 w-5 text-gray-600" />
            )}
          </div>
        </div>

        {/* Section Content */}
        {!isCollapsed && (
          <div className="overflow-x-auto">
            {positions.length === 0 ? (
              <div className="px-6 py-8 text-center text-gray-500">
                No {title.toLowerCase()} positions
              </div>
            ) : (
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-12"></th>
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
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {positions.map((trade) => {
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

                    const qty = aggregated.length > 0
                      ? Math.min(...aggregated.map(g => g.totalQuantity))
                      : 0;

                    const netPrice = qty > 0
                      ? parseFloat(trade.opening_cost) / qty / 100
                      : 0;

                    const netValue = aggregated.reduce((sum, g) => sum + g.totalValue, 0);
                    const totalComm = aggregated.reduce((sum, g) => sum + g.totalCommission, 0);

                    return (
                      <React.Fragment key={trade.id}>
                        <tr className="hover:bg-gray-50">
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
                            {trade.strategy_type}
                            {trade.is_assignment && (
                              <span className="ml-2 px-1.5 py-0.5 text-xs bg-orange-100 text-orange-700 rounded">
                                ASSIGN
                              </span>
                            )}
                            {trade.is_roll && !trade.is_assignment && (
                              <span className="ml-2 px-1.5 py-0.5 text-xs bg-purple-100 text-purple-700 rounded">
                                ROLL
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900">
                            {strikes}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900">
                            {expiration ? formatDate(expiration.toISOString()) : '-'}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900 text-right">
                            {dte !== null ? (
                              <span className={dte <= 7 ? 'text-red-600 font-semibold' : ''}>
                                {dte}
                              </span>
                            ) : '-'}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900 text-right">
                            {formatCurrency(netPrice)}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap text-sm text-right">
                            <span className={netValue >= 0 ? 'text-green-600' : 'text-red-600'}>
                              {formatCurrency(netValue)}
                            </span>
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900 text-right">
                            ${totalComm.toFixed(2)}
                          </td>
                        </tr>

                        {/* Expanded execution details */}
                        {expandedTrades.has(trade.id) && executions.length > 0 && (
                          <tr>
                            <td colSpan={11} className="px-6 py-4 bg-gray-50">
                              <table className="min-w-full">
                                <thead>
                                  <tr className="border-b border-gray-300">
                                    <th className="px-3 py-2 text-left text-xs font-semibold text-gray-700">Date Opened</th>
                                    <th className="px-3 py-2 text-left text-xs font-semibold text-gray-700">Action</th>
                                    <th className="px-3 py-2 text-left text-xs font-semibold text-gray-700">Qty</th>
                                    <th className="px-3 py-2 text-left text-xs font-semibold text-gray-700">Type</th>
                                    <th className="px-3 py-2 text-left text-xs font-semibold text-gray-700">Strike</th>
                                    <th className="px-3 py-2 text-left text-xs font-semibold text-gray-700">Expiration</th>
                                    <th className="px-3 py-2 text-right text-xs font-semibold text-gray-700">Open Price</th>
                                    <th className="px-3 py-2 text-right text-xs font-semibold text-gray-700">Commission</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {pairTransactions(executions).map((pair: any, idx: number) => (
                                    <tr key={idx} className="border-b border-gray-200">
                                      <td className="px-3 py-2 text-sm text-gray-900">
                                        {pair.dateOpened ? formatDate(pair.dateOpened.toISOString()) : '-'}
                                      </td>
                                      <td className="px-3 py-2 text-sm">
                                        <span className={`font-semibold ${pair.action.includes('Long') ? 'text-green-700' : 'text-red-700'}`}>
                                          {pair.action.includes('Long') ? '+' : '-'} {pair.action}
                                        </span>
                                      </td>
                                      <td className="px-3 py-2 text-sm font-medium text-gray-900">{pair.quantity}</td>
                                      <td className="px-3 py-2 text-sm text-gray-900">{pair.type}</td>
                                      <td className="px-3 py-2 text-sm font-medium text-gray-900">
                                        {pair.strike ? `$${pair.strike}` : '-'}
                                      </td>
                                      <td className="px-3 py-2 text-sm text-gray-900">
                                        {pair.expiration ? formatDate(pair.expiration) : '-'}
                                      </td>
                                      <td className="px-3 py-2 text-sm font-medium text-gray-900 text-right">
                                        {pair.openPrice !== null ? `$${Math.abs(pair.openPrice).toFixed(2)}` : '-'}
                                      </td>
                                      <td className="px-3 py-2 text-sm text-gray-900 text-right">
                                        ${pair.totalCommission.toFixed(2)}
                                      </td>
                                    </tr>
                                  ))}
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
            )}
          </div>
        )}
      </div>
    );
  }

  if (loading) {
    return (
      <div>
        <Header
          title="Portfolio"
          subtitle="View and manage your open positions"
        />
        <div className="p-6">
          <div className="animate-pulse space-y-4">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-32 rounded-lg bg-gray-200" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div>
      <Header
        title="Portfolio"
        subtitle="View and manage your open positions"
        actions={
          <ActionButton
            onClick={fetchOpenTrades}
            icon={<RefreshCw className="h-4 w-4" />}
            label="Refresh"
            loading={loading}
          />
        }
      />

      <div className="p-6 space-y-6">
        {/* Summary Cards */}
        <div className="grid gap-6 md:grid-cols-4">
          <div className="rounded-lg bg-white p-6 shadow">
            <div className="flex items-center gap-2">
              <Layers className="h-5 w-5 text-blue-600" />
              <h3 className="text-sm font-medium text-gray-600">Open Positions</h3>
            </div>
            <p className="mt-2 text-3xl font-bold text-gray-900">
              {trades.length}
            </p>
            <p className="mt-1 text-sm text-gray-500">
              {uniqueUnderlyings} underlying{uniqueUnderlyings !== 1 ? 's' : ''}
            </p>
          </div>
          <div className="rounded-lg bg-white p-6 shadow">
            <div className="flex items-center gap-2">
              {totalPortfolioCost >= 0 ? (
                <TrendingUp className="h-5 w-5 text-green-600" />
              ) : (
                <TrendingDown className="h-5 w-5 text-red-600" />
              )}
              <h3 className="text-sm font-medium text-gray-600">Net Cost Basis</h3>
            </div>
            <p className={`mt-2 text-3xl font-bold ${totalPortfolioCost >= 0 ? 'text-green-600' : 'text-red-600'}`}>
              {formatCurrency(totalPortfolioCost)}
            </p>
            <p className="mt-1 text-sm text-gray-500">
              {totalPortfolioCost < 0 ? 'Net credit received' : 'Net debit paid'}
            </p>
          </div>
          <div className="rounded-lg bg-white p-6 shadow">
            <div className="flex items-center gap-2">
              <Briefcase className="h-5 w-5 text-gray-600" />
              <h3 className="text-sm font-medium text-gray-600">Total Commission</h3>
            </div>
            <p className="mt-2 text-3xl font-bold text-gray-900">
              {formatCurrency(totalCommission)}
            </p>
          </div>
          <div className="rounded-lg bg-white p-6 shadow">
            <h3 className="text-sm font-medium text-gray-600">Breakdown</h3>
            <div className="mt-2 space-y-1 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500">Stocks:</span>
                <span className="font-medium">{categorizedTrades.stocks.length}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Options:</span>
                <span className="font-medium">{categorizedTrades.options.length}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Combos:</span>
                <span className="font-medium">{categorizedTrades.combos.length}</span>
              </div>
            </div>
          </div>
        </div>

        {/* No positions message */}
        {trades.length === 0 ? (
          <div className="rounded-lg bg-white p-12 text-center shadow">
            <Briefcase className="mx-auto h-12 w-12 text-gray-400" />
            <h3 className="mt-4 text-lg font-medium text-gray-900">
              No Open Positions
            </h3>
            <p className="mt-2 text-sm text-gray-500">
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
              positions={categorizedTrades.stocks}
              color="bg-blue-50 border-b border-blue-100"
            />

            {/* Options Section */}
            <PositionSection
              title="Options"
              icon={<BarChart3 className="h-5 w-5 text-green-600" />}
              category="options"
              positions={categorizedTrades.options}
              color="bg-green-50 border-b border-green-100"
            />

            {/* Combos Section */}
            <PositionSection
              title="Combos"
              icon={<Layers className="h-5 w-5 text-purple-600" />}
              category="combos"
              positions={categorizedTrades.combos}
              color="bg-purple-50 border-b border-purple-100"
            />
          </div>
        )}
      </div>
    </div>
  );
}
