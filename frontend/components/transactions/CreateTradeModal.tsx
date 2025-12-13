'use client';

import React, { useState, useMemo, useEffect } from 'react';
import { X, AlertCircle, AlertTriangle, RefreshCw, Sparkles } from 'lucide-react';
import { api } from '@/lib/api/client';
import { STRATEGY_OPTIONS, type Execution, type StrategyType } from '@/types';
import { formatCurrency, formatDate } from '@/lib/utils';

interface Props {
  executionIds: number[];
  executions: Execution[];
  onClose: () => void;
  onCreated: () => void;
}

// Leg analysis for strategy detection
interface LegInfo {
  optionType: 'C' | 'P';
  strike: number;
  expiration: string;
  side: 'BOT' | 'SLD';
  quantity: number;
  isLong: boolean;
}

// Detect strategy based on execution legs
function detectStrategy(executions: Execution[]): { strategy: StrategyType; confidence: 'high' | 'medium' | 'low'; reason: string } {
  // Filter to options only
  const optionExecs = executions.filter((e) => e.security_type === 'OPT');
  const stockExecs = executions.filter((e) => e.security_type === 'STK');

  // No options - can't detect
  if (optionExecs.length === 0 && stockExecs.length > 0) {
    return { strategy: 'Custom', confidence: 'low', reason: 'Stock position only' };
  }

  if (optionExecs.length === 0) {
    return { strategy: 'Custom', confidence: 'low', reason: 'No options detected' };
  }

  // Build leg map - group by unique contract
  const legMap = new Map<string, LegInfo>();
  optionExecs.forEach((exec) => {
    const key = `${exec.option_type}_${exec.strike}_${exec.expiration}`;
    if (legMap.has(key)) {
      const leg = legMap.get(key)!;
      // Aggregate quantity based on side
      if (exec.side === 'BOT') {
        leg.quantity += exec.quantity;
      } else {
        leg.quantity -= exec.quantity;
      }
    } else {
      legMap.set(key, {
        optionType: exec.option_type as 'C' | 'P',
        strike: exec.strike || 0,
        expiration: exec.expiration || '',
        side: exec.side as 'BOT' | 'SLD',
        quantity: exec.side === 'BOT' ? exec.quantity : -exec.quantity,
        isLong: exec.side === 'BOT',
      });
    }
  });

  // Get non-zero legs (net position)
  const legs = Array.from(legMap.values()).filter((l) => l.quantity !== 0);

  // Update isLong based on net quantity
  legs.forEach((leg) => {
    leg.isLong = leg.quantity > 0;
  });

  // Check for covered call: long stock + short call
  if (stockExecs.length > 0 && legs.length === 1) {
    const stockIsLong = stockExecs.some((e) => e.side === 'BOT');
    const leg = legs[0];
    if (stockIsLong && leg.optionType === 'C' && !leg.isLong) {
      return { strategy: 'Covered Call', confidence: 'high', reason: 'Long stock + short call' };
    }
  }

  // Single leg strategies
  if (legs.length === 1) {
    const leg = legs[0];
    if (leg.optionType === 'C') {
      return leg.isLong
        ? { strategy: 'Long Call', confidence: 'high', reason: 'Single long call' }
        : { strategy: 'Short Call', confidence: 'high', reason: 'Single short call' };
    } else {
      if (!leg.isLong && stockExecs.length === 0) {
        // Check if it could be a cash secured put
        return { strategy: 'Cash Secured Put', confidence: 'medium', reason: 'Short put (assuming cash secured)' };
      }
      return leg.isLong
        ? { strategy: 'Long Put', confidence: 'high', reason: 'Single long put' }
        : { strategy: 'Short Put', confidence: 'high', reason: 'Single short put' };
    }
  }

  // Two leg strategies
  if (legs.length === 2) {
    const sortedLegs = [...legs].sort((a, b) => a.strike - b.strike);
    const [lowerLeg, upperLeg] = sortedLegs;
    const sameExpiration = lowerLeg.expiration === upperLeg.expiration;
    const sameType = lowerLeg.optionType === upperLeg.optionType;

    // Vertical spreads (same expiration, same type, different strikes)
    if (sameExpiration && sameType) {
      if (lowerLeg.optionType === 'C') {
        // Call spread
        if (lowerLeg.isLong && !upperLeg.isLong) {
          return { strategy: 'Bull Call Spread', confidence: 'high', reason: 'Long lower call + short higher call' };
        } else if (!lowerLeg.isLong && upperLeg.isLong) {
          return { strategy: 'Bear Call Spread', confidence: 'high', reason: 'Short lower call + long higher call' };
        }
      } else {
        // Put spread
        // Bull Put Spread: Short higher strike put + Long lower strike put (credit spread)
        // Bear Put Spread: Long higher strike put + Short lower strike put (debit spread)
        if (lowerLeg.isLong && !upperLeg.isLong) {
          return { strategy: 'Bull Put Spread', confidence: 'high', reason: 'Long lower put + short higher put (credit spread)' };
        } else if (!lowerLeg.isLong && upperLeg.isLong) {
          return { strategy: 'Bear Put Spread', confidence: 'high', reason: 'Short lower put + long higher put (debit spread)' };
        }
      }
    }

    // Different expirations
    if (!sameExpiration && sameType) {
      return { strategy: 'Calendar Spread', confidence: 'medium', reason: 'Same type, different expirations' };
    }

    // Straddle (same strike, same expiration, one call one put)
    if (sameExpiration && !sameType && lowerLeg.strike === upperLeg.strike) {
      if (lowerLeg.isLong && upperLeg.isLong) {
        return { strategy: 'Straddle', confidence: 'high', reason: 'Long call + long put at same strike' };
      }
    }

    // Strangle (different strikes, same expiration, one call one put)
    if (sameExpiration && !sameType && lowerLeg.strike !== upperLeg.strike) {
      if (lowerLeg.isLong && upperLeg.isLong) {
        return { strategy: 'Strangle', confidence: 'high', reason: 'Long put + long call at different strikes' };
      }
    }
  }

  // Four leg strategies
  if (legs.length === 4) {
    const calls = legs.filter((l) => l.optionType === 'C');
    const puts = legs.filter((l) => l.optionType === 'P');

    // Iron Condor: 2 calls + 2 puts, all same expiration
    if (calls.length === 2 && puts.length === 2) {
      const allSameExp = legs.every((l) => l.expiration === legs[0].expiration);
      if (allSameExp) {
        return { strategy: 'Iron Condor', confidence: 'high', reason: '2 calls + 2 puts at same expiration' };
      }
    }
  }

  // Three leg strategies (butterfly)
  if (legs.length === 3) {
    const allCalls = legs.every((l) => l.optionType === 'C');
    const allPuts = legs.every((l) => l.optionType === 'P');
    const allSameExp = legs.every((l) => l.expiration === legs[0].expiration);

    if ((allCalls || allPuts) && allSameExp) {
      return { strategy: 'Butterfly', confidence: 'high', reason: '3 legs of same type at same expiration' };
    }
  }

  // Default fallback
  return { strategy: 'Custom', confidence: 'low', reason: `${legs.length}-leg position` };
}

export function CreateTradeModal({
  executionIds,
  executions: initialExecutions,
  onClose,
  onCreated,
}: Props) {
  const [strategyType, setStrategyType] = useState<StrategyType>('Long Call');
  const [customStrategy, setCustomStrategy] = useState('');
  const [notes, setNotes] = useState('');
  const [tags, setTags] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [executions, setExecutions] = useState<Execution[]>(initialExecutions);
  const [refreshing, setRefreshing] = useState(true);
  const [detectedStrategy, setDetectedStrategy] = useState<{ strategy: StrategyType; confidence: 'high' | 'medium' | 'low'; reason: string } | null>(null);

  // Refresh execution data when modal opens to get latest trade_id assignments
  useEffect(() => {
    async function refreshExecutions() {
      try {
        // Fetch fresh data for the selected execution IDs
        const response = await api.executions.list({ limit: 1000, opens_only: false });
        const freshExecutions = (response as { executions: Execution[] }).executions;

        // Filter to only the executions we care about
        const selectedFresh = freshExecutions.filter((e) => executionIds.includes(e.id));
        setExecutions(selectedFresh);
      } catch (err) {
        console.error('Failed to refresh executions:', err);
        // Fall back to initial executions if refresh fails
      } finally {
        setRefreshing(false);
      }
    }
    refreshExecutions();
  }, [executionIds]);

  // Run strategy detection after executions are loaded
  useEffect(() => {
    if (!refreshing && executions.length > 0) {
      const unassigned = executions.filter((e) => !e.trade_id);
      if (unassigned.length > 0) {
        const detected = detectStrategy(unassigned);
        setDetectedStrategy(detected);
        // Auto-set the strategy type if confidence is high or medium
        if (detected.confidence !== 'low') {
          setStrategyType(detected.strategy);
        }
      }
    }
  }, [refreshing, executions]);

  // Separate unassigned and already-assigned executions
  const { unassignedExecutions, assignedExecutions } = useMemo(() => {
    const unassigned = executions.filter((e) => !e.trade_id);
    const assigned = executions.filter((e) => e.trade_id);
    return { unassignedExecutions: unassigned, assignedExecutions: assigned };
  }, [executions]);

  // Only use unassigned executions for the trade
  const validExecutionIds = unassignedExecutions.map((e) => e.id);

  // Calculate summary info from UNASSIGNED executions only
  const underlyings = [...new Set(unassignedExecutions.map((e) => e.underlying))];
  const totalQuantity = unassignedExecutions.reduce((sum, e) => sum + e.quantity, 0);
  const totalCommission = unassignedExecutions.reduce(
    (sum, e) => sum + Number(e.commission),
    0
  );
  const hasMultipleUnderlyings = underlyings.length > 1;
  const hasNoValidExecutions = unassignedExecutions.length === 0;

  // Group executions into legs for display
  const tradeLegs = useMemo(() => {
    // Only show legs for option executions
    const optionExecs = unassignedExecutions.filter((e) => e.security_type === 'OPT');

    // Group by strike + option_type + expiration
    const legMap = new Map<string, {
      optionType: string;
      strike: number;
      expiration: string;
      side: string;
      quantity: number;
      executions: typeof optionExecs;
    }>();

    optionExecs.forEach((exec) => {
      const key = `${exec.option_type}_${exec.strike}_${exec.expiration}`;
      if (legMap.has(key)) {
        const leg = legMap.get(key)!;
        leg.quantity += exec.quantity;
        leg.executions.push(exec);
      } else {
        legMap.set(key, {
          optionType: exec.option_type || '',
          strike: exec.strike || 0,
          expiration: exec.expiration || '',
          side: exec.side,
          quantity: exec.quantity,
          executions: [exec],
        });
      }
    });

    return Array.from(legMap.values()).sort((a, b) => b.strike - a.strike);
  }, [unassignedExecutions]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    if (hasNoValidExecutions) {
      setError('No unassigned executions to create a trade from.');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      await api.trades.createManual({
        execution_ids: validExecutionIds,
        strategy_type: strategyType,
        custom_strategy:
          strategyType === 'Custom' ? customStrategy : undefined,
        notes: notes || undefined,
        tags: tags || undefined,
      });
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create trade');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-md max-h-[90vh] overflow-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Create Trade</h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-4">
          {/* Loading state while refreshing execution data */}
          {refreshing && (
            <div className="mb-4 p-4 flex items-center justify-center gap-2 text-gray-600 dark:text-gray-400">
              <RefreshCw className="h-5 w-5 animate-spin" />
              Checking execution status...
            </div>
          )}

          {/* Error: All executions already assigned */}
          {!refreshing && hasNoValidExecutions && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg flex items-start gap-2">
              <AlertCircle className="h-5 w-5 text-red-600 flex-shrink-0 mt-0.5" />
              <div className="text-sm text-red-800">
                <strong>Cannot create trade:</strong> All {assignedExecutions.length} selected
                execution{assignedExecutions.length !== 1 ? 's are' : ' is'} already assigned to existing trades.
                Please select unassigned executions.
              </div>
            </div>
          )}

          {/* Warning: Some executions already assigned */}
          {!refreshing && assignedExecutions.length > 0 && !hasNoValidExecutions && (
            <div className="mb-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg flex items-start gap-2">
              <AlertTriangle className="h-5 w-5 text-yellow-600 flex-shrink-0 mt-0.5" />
              <div className="text-sm text-yellow-800">
                <strong>Note:</strong> {assignedExecutions.length} of {executions.length} selected
                execution{assignedExecutions.length !== 1 ? 's are' : ' is'} already assigned to trades
                and will be skipped. Only {unassignedExecutions.length} unassigned
                execution{unassignedExecutions.length !== 1 ? 's' : ''} will be included.
              </div>
            </div>
          )}

          {/* Warning for multiple underlyings */}
          {!refreshing && hasMultipleUnderlyings && !hasNoValidExecutions && (
            <div className="mb-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg flex items-start gap-2">
              <AlertCircle className="h-5 w-5 text-yellow-600 flex-shrink-0 mt-0.5" />
              <div className="text-sm text-yellow-800">
                <strong>Warning:</strong> Selected executions have multiple
                underlyings ({underlyings.join(', ')}). Trades typically contain
                a single underlying.
              </div>
            </div>
          )}

          {/* Summary */}
          {!refreshing && (
          <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 mb-4">
            <h3 className="text-sm font-medium text-gray-800 dark:text-gray-200 mb-2">Summary</h3>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div className="text-gray-600 dark:text-gray-400">Underlying:</div>
              <div className="font-medium text-gray-900 dark:text-white">
                {underlyings.length > 0 ? underlyings.join(', ') : '-'}
              </div>
              <div className="text-gray-600 dark:text-gray-400">Executions:</div>
              <div className="font-medium text-gray-900 dark:text-white">
                {unassignedExecutions.length}
                {assignedExecutions.length > 0 && (
                  <span className="text-gray-500 dark:text-gray-400 font-normal">
                    {' '}(of {executions.length} selected)
                  </span>
                )}
              </div>
              <div className="text-gray-600 dark:text-gray-400">Total Quantity:</div>
              <div className="font-medium text-gray-900 dark:text-white">{totalQuantity}</div>
              <div className="text-gray-600 dark:text-gray-400">Total Commission:</div>
              <div className="font-medium text-gray-900 dark:text-white">
                {formatCurrency(totalCommission)}
              </div>
            </div>
          </div>
          )}

          {/* Trade Legs */}
          {!refreshing && tradeLegs.length > 0 && (
            <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 mb-4">
              <h3 className="text-sm font-medium text-gray-800 dark:text-gray-200 mb-3">Trade Legs</h3>
              <div className="space-y-2">
                {tradeLegs.map((leg, index) => (
                  <div
                    key={index}
                    className={`flex items-center justify-between p-2 rounded-md ${
                      leg.optionType === 'P'
                        ? 'bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800'
                        : 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <span
                        className={`px-2 py-0.5 rounded text-xs font-semibold ${
                          leg.side === 'BOT'
                            ? 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200'
                            : 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200'
                        }`}
                      >
                        {leg.side === 'BOT' ? 'LONG' : 'SHORT'}
                      </span>
                      <span
                        className={`px-2 py-0.5 rounded text-xs font-semibold ${
                          leg.optionType === 'P'
                            ? 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
                            : 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                        }`}
                      >
                        {leg.optionType === 'P' ? 'PUT' : 'CALL'}
                      </span>
                      <span className="font-medium text-gray-900 dark:text-white">
                        ${leg.strike}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-sm">
                      <span className="text-gray-600 dark:text-gray-400">
                        x{leg.quantity}
                      </span>
                      <span className="text-gray-500 dark:text-gray-400 text-xs">
                        {formatDate(leg.expiration)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {!refreshing && (
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Detected Strategy Banner */}
            {detectedStrategy && detectedStrategy.confidence !== 'low' && (
              <div className={`p-3 rounded-lg flex items-start gap-2 ${
                detectedStrategy.confidence === 'high'
                  ? 'bg-green-50 border border-green-200 dark:bg-green-900/20 dark:border-green-800'
                  : 'bg-blue-50 border border-blue-200 dark:bg-blue-900/20 dark:border-blue-800'
              }`}>
                <Sparkles className={`h-5 w-5 flex-shrink-0 mt-0.5 ${
                  detectedStrategy.confidence === 'high'
                    ? 'text-green-600 dark:text-green-400'
                    : 'text-blue-600 dark:text-blue-400'
                }`} />
                <div className="flex-1">
                  <div className={`text-sm font-medium ${
                    detectedStrategy.confidence === 'high'
                      ? 'text-green-800 dark:text-green-200'
                      : 'text-blue-800 dark:text-blue-200'
                  }`}>
                    Detected: <strong>{detectedStrategy.strategy}</strong>
                    <span className={`ml-2 px-1.5 py-0.5 rounded text-xs ${
                      detectedStrategy.confidence === 'high'
                        ? 'bg-green-200 text-green-800 dark:bg-green-800 dark:text-green-200'
                        : 'bg-blue-200 text-blue-800 dark:bg-blue-800 dark:text-blue-200'
                    }`}>
                      {detectedStrategy.confidence} confidence
                    </span>
                  </div>
                  <div className={`text-xs mt-0.5 ${
                    detectedStrategy.confidence === 'high'
                      ? 'text-green-700 dark:text-green-300'
                      : 'text-blue-700 dark:text-blue-300'
                  }`}>
                    {detectedStrategy.reason}
                  </div>
                </div>
                {strategyType !== detectedStrategy.strategy && (
                  <button
                    type="button"
                    onClick={() => setStrategyType(detectedStrategy.strategy)}
                    className={`text-xs px-2 py-1 rounded font-medium ${
                      detectedStrategy.confidence === 'high'
                        ? 'bg-green-200 text-green-800 hover:bg-green-300 dark:bg-green-800 dark:text-green-200 dark:hover:bg-green-700'
                        : 'bg-blue-200 text-blue-800 hover:bg-blue-300 dark:bg-blue-800 dark:text-blue-200 dark:hover:bg-blue-700'
                    }`}
                  >
                    Use this
                  </button>
                )}
              </div>
            )}

            {/* Strategy Type */}
            <div>
              <label className="block text-sm font-medium text-gray-800 dark:text-gray-200 mb-1">
                Strategy Type
                {detectedStrategy && strategyType === detectedStrategy.strategy && detectedStrategy.confidence !== 'low' && (
                  <span className="ml-2 text-xs text-green-600 dark:text-green-400">(auto-detected)</span>
                )}
              </label>
              <select
                value={strategyType}
                onChange={(e) =>
                  setStrategyType(e.target.value as StrategyType)
                }
                className="w-full rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white shadow-sm focus:border-blue-500 focus:ring-blue-500"
              >
                {STRATEGY_OPTIONS.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}{detectedStrategy && opt === detectedStrategy.strategy && detectedStrategy.confidence !== 'low' ? ' (recommended)' : ''}
                  </option>
                ))}
              </select>
            </div>

            {/* Custom Strategy Input */}
            {strategyType === 'Custom' && (
              <div>
                <label className="block text-sm font-medium text-gray-800 dark:text-gray-200 mb-1">
                  Custom Strategy Name
                </label>
                <input
                  type="text"
                  value={customStrategy}
                  onChange={(e) => setCustomStrategy(e.target.value)}
                  className="w-full rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white shadow-sm focus:border-blue-500 focus:ring-blue-500"
                  placeholder="Enter custom strategy name"
                  required
                />
              </div>
            )}

            {/* Notes */}
            <div>
              <label className="block text-sm font-medium text-gray-800 dark:text-gray-200 mb-1">
                Notes <span className="text-gray-500 dark:text-gray-400">(optional)</span>
              </label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="w-full rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white shadow-sm focus:border-blue-500 focus:ring-blue-500"
                rows={3}
                placeholder="Add notes about this trade..."
              />
            </div>

            {/* Tags */}
            <div>
              <label className="block text-sm font-medium text-gray-800 dark:text-gray-200 mb-1">
                Tags <span className="text-gray-500 dark:text-gray-400">(optional)</span>
              </label>
              <input
                type="text"
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                className="w-full rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white shadow-sm focus:border-blue-500 focus:ring-blue-500"
                placeholder="earnings, hedge, momentum"
              />
              <p className="mt-1 text-xs text-gray-600 dark:text-gray-400">
                Separate multiple tags with commas
              </p>
            </div>

            {/* Error */}
            {error && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
                {error}
              </div>
            )}

            {/* Actions */}
            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={
                  loading ||
                  hasNoValidExecutions ||
                  (strategyType === 'Custom' && !customStrategy.trim())
                }
                className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {loading ? 'Creating...' : 'Create Trade'}
              </button>
            </div>
          </form>
          )}
        </div>
      </div>
    </div>
  );
}
