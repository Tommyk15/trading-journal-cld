'use client';

import { useEffect, useState } from 'react';
import { Header, ActionButton } from '@/components/layout/Header';
import { api } from '@/lib/api/client';
import { formatCurrency, formatDate, getPnlColor } from '@/lib/utils';
import { RefreshCw, ChevronDown, ChevronRight, TrendingUp, TrendingDown, Briefcase } from 'lucide-react';

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
}

interface PortfolioGroup {
  underlying: string;
  trades: OpenTrade[];
  totalCost: number;
  tradeCount: number;
}

export default function PositionsPage() {
  const [trades, setTrades] = useState<OpenTrade[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedUnderlyings, setExpandedUnderlyings] = useState<Set<string>>(new Set());
  const [expandedTrades, setExpandedTrades] = useState<Set<number>>(new Set());
  const [tradeExecutions, setTradeExecutions] = useState<Record<number, TradeExecution[]>>({});
  const [viewMode, setViewMode] = useState<'underlying' | 'all'>('underlying');

  async function fetchOpenTrades() {
    try {
      setLoading(true);
      const data: any = await api.trades.list({ status: 'OPEN', limit: 1000 });
      const openTrades = data.trades || [];
      setTrades(openTrades);
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

  // Group trades by underlying
  const portfolioGroups: PortfolioGroup[] = Object.values(
    trades.reduce((acc: Record<string, PortfolioGroup>, trade) => {
      const underlying = trade.underlying;
      if (!acc[underlying]) {
        acc[underlying] = {
          underlying,
          trades: [],
          totalCost: 0,
          tradeCount: 0,
        };
      }
      acc[underlying].trades.push(trade);
      acc[underlying].totalCost += parseFloat(trade.opening_cost || '0');
      acc[underlying].tradeCount += 1;
      return acc;
    }, {})
  ).sort((a, b) => Math.abs(b.totalCost) - Math.abs(a.totalCost));

  const totalPortfolioCost = trades.reduce(
    (sum, trade) => sum + parseFloat(trade.opening_cost || '0'),
    0
  );

  const totalCommission = trades.reduce(
    (sum, trade) => sum + parseFloat(trade.total_commission || '0'),
    0
  );

  const toggleUnderlying = (underlying: string) => {
    const newExpanded = new Set(expandedUnderlyings);
    if (newExpanded.has(underlying)) {
      newExpanded.delete(underlying);
    } else {
      newExpanded.add(underlying);
    }
    setExpandedUnderlyings(newExpanded);
  };

  const toggleTrade = async (tradeId: number) => {
    const newExpanded = new Set(expandedTrades);
    if (newExpanded.has(tradeId)) {
      newExpanded.delete(tradeId);
    } else {
      newExpanded.add(tradeId);
      // Fetch executions if not loaded
      if (!tradeExecutions[tradeId]) {
        try {
          const data = await api.trades.getExecutions(tradeId);
          setTradeExecutions(prev => ({
            ...prev,
            [tradeId]: (data as any).executions || [],
          }));
        } catch (error) {
          console.error('Error fetching executions:', error);
        }
      }
    }
    setExpandedTrades(newExpanded);
  };

  // Helper to get action label
  function getActionLabel(exec: TradeExecution) {
    const isBuy = exec.side === 'BOT';
    const isOpen = exec.open_close_indicator === 'O';

    if (isBuy && isOpen) return 'BTO';
    if (isBuy && !isOpen) return 'BTC';
    if (!isBuy && isOpen) return 'STO';
    return 'STC';
  }

  if (loading) {
    return (
      <div>
        <Header
          title="Portfolio"
          subtitle="View and manage your open positions"
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
              <Briefcase className="h-5 w-5 text-blue-600" />
              <h3 className="text-sm font-medium text-gray-600">Open Trades</h3>
            </div>
            <p className="mt-2 text-3xl font-bold text-gray-900">
              {trades.length}
            </p>
            <p className="mt-1 text-sm text-gray-500">
              across {portfolioGroups.length} symbols
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
            <h3 className="text-sm font-medium text-gray-600">Total Commission</h3>
            <p className="mt-2 text-3xl font-bold text-gray-900">
              {formatCurrency(totalCommission)}
            </p>
          </div>
          <div className="rounded-lg bg-white p-6 shadow">
            <h3 className="text-sm font-medium text-gray-600">View Mode</h3>
            <div className="mt-2 flex gap-2">
              <button
                onClick={() => setViewMode('underlying')}
                className={`px-3 py-1 text-sm rounded ${
                  viewMode === 'underlying'
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-200 text-gray-700'
                }`}
              >
                By Symbol
              </button>
              <button
                onClick={() => setViewMode('all')}
                className={`px-3 py-1 text-sm rounded ${
                  viewMode === 'all'
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-200 text-gray-700'
                }`}
              >
                All Trades
              </button>
            </div>
          </div>
        </div>

        {/* Portfolio View */}
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
        ) : viewMode === 'underlying' ? (
          /* Grouped by Underlying View */
          <div className="space-y-4">
            {portfolioGroups.map((group) => (
              <div key={group.underlying} className="rounded-lg bg-white shadow overflow-hidden">
                {/* Group Header */}
                <div
                  className="px-6 py-4 bg-gray-50 border-b border-gray-200 cursor-pointer hover:bg-gray-100"
                  onClick={() => toggleUnderlying(group.underlying)}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      {expandedUnderlyings.has(group.underlying) ? (
                        <ChevronDown className="h-5 w-5 text-gray-500" />
                      ) : (
                        <ChevronRight className="h-5 w-5 text-gray-500" />
                      )}
                      <div>
                        <h3 className="text-lg font-bold text-gray-900">
                          {group.underlying}
                        </h3>
                        <p className="text-sm text-gray-500">
                          {group.tradeCount} {group.tradeCount === 1 ? 'trade' : 'trades'}
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className={`text-lg font-bold ${group.totalCost >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        {formatCurrency(group.totalCost)}
                      </p>
                      <p className="text-sm text-gray-500">
                        {group.totalCost < 0 ? 'credit' : 'debit'}
                      </p>
                    </div>
                  </div>
                </div>

                {/* Expanded Trades */}
                {expandedUnderlyings.has(group.underlying) && (
                  <div className="divide-y divide-gray-200">
                    {group.trades.map((trade) => (
                      <div key={trade.id}>
                        {/* Trade Row */}
                        <div
                          className="px-6 py-4 cursor-pointer hover:bg-gray-50"
                          onClick={() => toggleTrade(trade.id)}
                        >
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                              {expandedTrades.has(trade.id) ? (
                                <ChevronDown className="h-4 w-4 text-gray-400" />
                              ) : (
                                <ChevronRight className="h-4 w-4 text-gray-400" />
                              )}
                              <div>
                                <div className="flex items-center gap-2">
                                  <span className="text-sm font-medium text-gray-900">
                                    {trade.strategy_type}
                                  </span>
                                  {trade.is_roll && (
                                    <span className="px-2 py-0.5 text-xs bg-purple-100 text-purple-700 rounded">
                                      ROLL
                                    </span>
                                  )}
                                </div>
                                <p className="text-xs text-gray-500">
                                  Opened {formatDate(trade.opened_at)} · {trade.num_legs} leg{trade.num_legs !== 1 ? 's' : ''} · {trade.num_executions} exec{trade.num_executions !== 1 ? 's' : ''}
                                </p>
                              </div>
                            </div>
                            <div className="text-right">
                              <p className={`text-sm font-medium ${parseFloat(trade.opening_cost) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                                {formatCurrency(parseFloat(trade.opening_cost))}
                              </p>
                              <p className="text-xs text-gray-500">
                                comm: {formatCurrency(parseFloat(trade.total_commission))}
                              </p>
                            </div>
                          </div>
                        </div>

                        {/* Trade Executions */}
                        {expandedTrades.has(trade.id) && tradeExecutions[trade.id] && (
                          <div className="px-6 pb-4 bg-gray-50">
                            <table className="min-w-full text-sm">
                              <thead>
                                <tr className="text-xs text-gray-500 uppercase">
                                  <th className="py-2 text-left">Date</th>
                                  <th className="py-2 text-left">Action</th>
                                  <th className="py-2 text-right">Qty</th>
                                  <th className="py-2 text-right">Strike</th>
                                  <th className="py-2 text-left">Type</th>
                                  <th className="py-2 text-left">Exp</th>
                                  <th className="py-2 text-right">Price</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-gray-200">
                                {tradeExecutions[trade.id].map((exec) => (
                                  <tr key={exec.id}>
                                    <td className="py-2 text-gray-600">
                                      {formatDate(exec.execution_time)}
                                    </td>
                                    <td className="py-2">
                                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                                        exec.side === 'BOT' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                                      }`}>
                                        {getActionLabel(exec)}
                                      </span>
                                    </td>
                                    <td className="py-2 text-right text-gray-900">{exec.quantity}</td>
                                    <td className="py-2 text-right text-gray-900">${exec.strike}</td>
                                    <td className="py-2 text-gray-600">{exec.option_type === 'C' ? 'Call' : 'Put'}</td>
                                    <td className="py-2 text-gray-600">
                                      {exec.expiration ? formatDate(exec.expiration) : '-'}
                                    </td>
                                    <td className="py-2 text-right text-gray-900">${parseFloat(exec.price).toFixed(2)}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          /* All Trades View */
          <div className="rounded-lg bg-white shadow overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Symbol
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Strategy
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Opened
                    </th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                      Legs
                    </th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                      Cost Basis
                    </th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                      Commission
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {trades.map((trade) => (
                    <tr key={trade.id} className="hover:bg-gray-50">
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className="text-sm font-medium text-gray-900">
                          {trade.underlying}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-gray-900">
                            {trade.strategy_type}
                          </span>
                          {trade.is_roll && (
                            <span className="px-2 py-0.5 text-xs bg-purple-100 text-purple-700 rounded">
                              ROLL
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {formatDate(trade.opened_at)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 text-right">
                        {trade.num_legs}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-right">
                        <span className={`text-sm font-medium ${parseFloat(trade.opening_cost) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                          {formatCurrency(parseFloat(trade.opening_cost))}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 text-right">
                        {formatCurrency(parseFloat(trade.total_commission))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
