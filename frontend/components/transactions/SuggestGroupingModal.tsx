'use client';

import React, { useEffect, useState, useMemo } from 'react';
import { X, Check, RefreshCw, AlertCircle, ChevronDown, ChevronRight, Filter } from 'lucide-react';
import { api } from '@/lib/api/client';
import type { SuggestedGroup, SuggestGroupingResponse, SuggestedGroupLeg } from '@/types';
import { formatCurrency } from '@/lib/utils';

function formatLegDescription(leg: SuggestedGroupLeg): string {
  if (leg.security_type === 'STK') {
    return `Stock (${leg.total_quantity >= 0 ? '+' : ''}${leg.total_quantity})`;
  }

  const typeLabel = leg.option_type === 'C' ? 'Call' : leg.option_type === 'P' ? 'Put' : leg.security_type;
  const strikeStr = leg.strike ? `$${leg.strike}` : '';
  const expStr = leg.expiration || '';
  const qtyStr = leg.total_quantity >= 0 ? `+${leg.total_quantity}` : `${leg.total_quantity}`;

  return `${strikeStr} ${typeLabel} ${expStr} (${qtyStr})`.trim();
}

function getActionBadgeColor(action: string): string {
  switch (action) {
    case 'BTO': return 'bg-green-100 text-green-700';
    case 'BTC': return 'bg-blue-100 text-blue-700';
    case 'STO': return 'bg-red-100 text-red-700';
    case 'STC': return 'bg-purple-100 text-purple-700';
    default: return 'bg-gray-100 text-gray-700';
  }
}

interface Props {
  onClose: () => void;
  onApply: () => void;
}

export function SuggestGroupingModal({ onClose, onApply }: Props) {
  const [suggestions, setSuggestions] = useState<SuggestedGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedGroups, setSelectedGroups] = useState<Set<number>>(new Set());
  const [expandedGroups, setExpandedGroups] = useState<Set<number>>(new Set());
  const [appliedCount, setAppliedCount] = useState(0);
  const [selectedStrategies, setSelectedStrategies] = useState<Set<string>>(new Set());
  const [showStrategyFilter, setShowStrategyFilter] = useState(false);

  // Get unique strategies from suggestions
  const availableStrategies = useMemo(() => {
    const strategies = new Set(suggestions.map(g => g.suggested_strategy));
    return Array.from(strategies).sort();
  }, [suggestions]);

  // Filter suggestions based on selected strategies
  const filteredSuggestions = useMemo(() => {
    if (selectedStrategies.size === 0) {
      return suggestions;
    }
    return suggestions.filter(g => selectedStrategies.has(g.suggested_strategy));
  }, [suggestions, selectedStrategies]);

  // Map filtered indices back to original indices for selection
  const filteredToOriginalIndex = useMemo(() => {
    const map = new Map<number, number>();
    let filteredIdx = 0;
    suggestions.forEach((group, originalIdx) => {
      if (selectedStrategies.size === 0 || selectedStrategies.has(group.suggested_strategy)) {
        map.set(filteredIdx, originalIdx);
        filteredIdx++;
      }
    });
    return map;
  }, [suggestions, selectedStrategies]);

  function toggleStrategyFilter(strategy: string) {
    const newSelected = new Set(selectedStrategies);
    if (newSelected.has(strategy)) {
      newSelected.delete(strategy);
    } else {
      newSelected.add(strategy);
    }
    setSelectedStrategies(newSelected);
  }

  function clearStrategyFilters() {
    setSelectedStrategies(new Set());
  }

  function toggleExpanded(index: number, e: React.MouseEvent) {
    e.stopPropagation();
    const newExpanded = new Set(expandedGroups);
    if (newExpanded.has(index)) {
      newExpanded.delete(index);
    } else {
      newExpanded.add(index);
    }
    setExpandedGroups(newExpanded);
  }

  useEffect(() => {
    fetchSuggestions();
  }, []);

  async function fetchSuggestions() {
    setLoading(true);
    setError(null);
    try {
      const data = (await api.trades.suggestGrouping()) as SuggestGroupingResponse;
      setSuggestions(data.groups || []);
      // Pre-select all groups by default
      setSelectedGroups(new Set(data.groups.map((_, i) => i)));
    } catch (err) {
      console.error('Error fetching suggestions:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch suggestions');
    } finally {
      setLoading(false);
    }
  }

  function toggleGroup(index: number) {
    const newSelected = new Set(selectedGroups);
    if (newSelected.has(index)) {
      newSelected.delete(index);
    } else {
      newSelected.add(index);
    }
    setSelectedGroups(newSelected);
  }

  function selectAll() {
    // Get original indices of filtered suggestions
    const filteredOriginalIndices = Array.from(filteredToOriginalIndex.values());

    // Check if all filtered suggestions are selected
    const allFilteredSelected = filteredOriginalIndices.every(idx => selectedGroups.has(idx));

    if (allFilteredSelected) {
      // Deselect all filtered suggestions
      const newSelected = new Set(selectedGroups);
      filteredOriginalIndices.forEach(idx => newSelected.delete(idx));
      setSelectedGroups(newSelected);
    } else {
      // Select all filtered suggestions
      const newSelected = new Set(selectedGroups);
      filteredOriginalIndices.forEach(idx => newSelected.add(idx));
      setSelectedGroups(newSelected);
    }
  }

  // Count how many filtered suggestions are selected
  const filteredSelectedCount = useMemo(() => {
    const filteredOriginalIndices = Array.from(filteredToOriginalIndex.values());
    return filteredOriginalIndices.filter(idx => selectedGroups.has(idx)).length;
  }, [filteredToOriginalIndex, selectedGroups]);

  async function applySelected() {
    if (selectedGroups.size === 0) return;

    setApplying(true);
    setError(null);
    setAppliedCount(0);

    const selectedIndices = Array.from(selectedGroups).sort((a, b) => a - b);
    const failedGroups: { index: number; error: string }[] = [];
    let successCount = 0;

    // Create trades for each selected group, continuing on errors
    for (const index of selectedIndices) {
      const group = suggestions[index];
      try {
        await api.trades.createManual({
          execution_ids: group.execution_ids,
          strategy_type: group.suggested_strategy,
        });
        successCount++;
        setAppliedCount(successCount);
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'Unknown error';
        failedGroups.push({ index, error: errorMessage });
        console.warn(`Failed to create trade for group ${index} (${group.underlying}): ${errorMessage}`);
      }
    }

    setApplying(false);

    if (failedGroups.length === 0) {
      // All succeeded
      onApply();
    } else if (successCount > 0) {
      // Partial success - show message and refresh
      setError(
        `Created ${successCount} trades. ${failedGroups.length} group(s) failed (executions may already be assigned). Refreshing suggestions...`
      );
      // Refresh to get updated suggestions
      setTimeout(() => {
        fetchSuggestions();
      }, 1500);
    } else {
      // All failed
      setError(
        `Failed to create trades: ${failedGroups[0].error}`
      );
    }
  }

  const totalPnl = suggestions
    .filter((_, i) => selectedGroups.has(i))
    .reduce((sum, g) => sum + g.total_pnl, 0);

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200 flex-shrink-0">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">
              Suggested Trade Groups
            </h2>
            <p className="text-sm text-gray-500">
              Auto-detected groupings based on execution patterns
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-4">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <RefreshCw className="h-6 w-6 animate-spin text-blue-600" />
              <span className="ml-2 text-gray-600">Analyzing executions...</span>
            </div>
          ) : error ? (
            <div className="p-4 bg-red-50 border border-red-200 rounded-lg flex items-start gap-2">
              <AlertCircle className="h-5 w-5 text-red-600 flex-shrink-0 mt-0.5" />
              <div className="text-sm text-red-700">{error}</div>
            </div>
          ) : suggestions.length === 0 ? (
            <div className="text-center py-12 text-gray-500">
              <p className="text-lg font-medium">No grouping suggestions</p>
              <p className="mt-1 text-sm">
                All executions may already be assigned to trades.
              </p>
            </div>
          ) : (
            <>
              {/* Strategy Filter */}
              <div className="mb-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setShowStrategyFilter(!showStrategyFilter)}
                      className={`flex items-center gap-2 px-3 py-1.5 text-sm font-medium rounded-lg border transition-colors ${
                        selectedStrategies.size > 0
                          ? 'bg-blue-50 border-blue-300 text-blue-700'
                          : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'
                      }`}
                    >
                      <Filter className="h-4 w-4" />
                      Filter by Strategy
                      {selectedStrategies.size > 0 && (
                        <span className="bg-blue-600 text-white text-xs px-1.5 py-0.5 rounded-full">
                          {selectedStrategies.size}
                        </span>
                      )}
                      <ChevronDown className={`h-4 w-4 transition-transform ${showStrategyFilter ? 'rotate-180' : ''}`} />
                    </button>
                    {selectedStrategies.size > 0 && (
                      <button
                        onClick={clearStrategyFilters}
                        className="text-sm text-gray-500 hover:text-gray-700 underline"
                      >
                        Clear filters
                      </button>
                    )}
                  </div>
                  <div className="text-sm text-gray-500">
                    Showing {filteredSuggestions.length} of {suggestions.length} groups
                  </div>
                </div>

                {/* Strategy Filter Dropdown */}
                {showStrategyFilter && (
                  <div className="mt-2 p-3 bg-gray-50 border border-gray-200 rounded-lg">
                    <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
                      Select strategies to show
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {availableStrategies.map((strategy) => {
                        const count = suggestions.filter(s => s.suggested_strategy === strategy).length;
                        const isSelected = selectedStrategies.has(strategy);
                        return (
                          <button
                            key={strategy}
                            onClick={() => toggleStrategyFilter(strategy)}
                            className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-full border transition-colors ${
                              isSelected
                                ? 'bg-blue-600 border-blue-600 text-white'
                                : 'bg-white border-gray-300 text-gray-700 hover:border-gray-400'
                            }`}
                          >
                            {isSelected && <Check className="h-3 w-3" />}
                            {strategy}
                            <span className={`text-xs ${isSelected ? 'text-blue-200' : 'text-gray-400'}`}>
                              ({count})
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>

              {/* Select All */}
              <div className="flex items-center justify-between mb-4">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={filteredSelectedCount === filteredSuggestions.length && filteredSuggestions.length > 0}
                    onChange={selectAll}
                    className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  />
                  <span className="text-sm text-gray-700">
                    Select All ({filteredSuggestions.length} groups)
                  </span>
                </label>
                {selectedGroups.size > 0 && (
                  <div className="text-sm text-gray-600">
                    Selected P&L:{' '}
                    <span
                      className={`font-medium ${
                        totalPnl >= 0 ? 'text-green-600' : 'text-red-600'
                      }`}
                    >
                      {formatCurrency(totalPnl)}
                    </span>
                  </div>
                )}
              </div>

              {/* Suggestions List */}
              <div className="space-y-2">
                {filteredSuggestions.map((group, filteredIndex) => {
                  const originalIndex = filteredToOriginalIndex.get(filteredIndex) ?? filteredIndex;
                  return (
                  <div
                    key={originalIndex}
                    className={`border rounded-lg transition-all ${
                      selectedGroups.has(originalIndex)
                        ? 'border-blue-500 bg-blue-50 ring-1 ring-blue-500'
                        : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    {/* Main Row */}
                    <div
                      onClick={() => toggleGroup(originalIndex)}
                      className="p-4 cursor-pointer"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <button
                            onClick={(e) => toggleExpanded(originalIndex, e)}
                            className="p-0.5 hover:bg-gray-200 rounded transition-colors"
                          >
                            {expandedGroups.has(originalIndex) ? (
                              <ChevronDown className="h-4 w-4 text-gray-500" />
                            ) : (
                              <ChevronRight className="h-4 w-4 text-gray-500" />
                            )}
                          </button>
                          <input
                            type="checkbox"
                            checked={selectedGroups.has(originalIndex)}
                            onChange={() => toggleGroup(originalIndex)}
                            onClick={(e) => e.stopPropagation()}
                            className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                          />
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="font-medium text-gray-900">
                                {group.underlying}
                              </span>
                              <span className="text-gray-400">|</span>
                              <span className="text-gray-600">
                                {group.suggested_strategy}
                              </span>
                              <span className={`text-xs px-2 py-0.5 rounded-full ${
                                group.status === 'CLOSED'
                                  ? 'bg-gray-100 text-gray-600'
                                  : 'bg-yellow-100 text-yellow-700'
                              }`}>
                                {group.status}
                              </span>
                            </div>
                            <div className="text-sm text-gray-500 flex items-center gap-2">
                              <span>{group.num_executions} execution{group.num_executions !== 1 ? 's' : ''}</span>
                              {group.open_date && (
                                <>
                                  <span className="text-gray-300">•</span>
                                  <span>{group.open_date}{group.close_date && group.close_date !== group.open_date ? ` → ${group.close_date}` : ''}</span>
                                </>
                              )}
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-4">
                          <span
                            className={`font-medium ${
                              group.total_pnl >= 0
                                ? 'text-green-600'
                                : 'text-red-600'
                            }`}
                          >
                            {formatCurrency(group.total_pnl)}
                          </span>
                          {selectedGroups.has(originalIndex) && (
                            <Check className="h-5 w-5 text-blue-600" />
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Expanded Legs Section */}
                    {expandedGroups.has(originalIndex) && group.legs && group.legs.length > 0 && (
                      <div className="px-4 pb-4 pt-0 border-t border-gray-200 ml-12">
                        <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mt-3 mb-2">
                          Trade Legs
                        </div>
                        <div className="space-y-2">
                          {group.legs.map((leg, legIndex) => (
                            <div
                              key={legIndex}
                              className="flex items-center justify-between text-sm bg-white rounded p-2 border border-gray-100"
                            >
                              <div className="flex items-center gap-2">
                                <span className={`font-medium ${
                                  leg.option_type === 'C' ? 'text-green-700' :
                                  leg.option_type === 'P' ? 'text-red-700' : 'text-gray-700'
                                }`}>
                                  {formatLegDescription(leg)}
                                </span>
                              </div>
                              <div className="flex items-center gap-1">
                                {leg.actions.map((action, actionIndex) => (
                                  <span
                                    key={actionIndex}
                                    className={`text-xs px-1.5 py-0.5 rounded font-medium ${getActionBadgeColor(action)}`}
                                  >
                                    {action}
                                  </span>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                  );
                })}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-4 border-t border-gray-200 bg-gray-50 flex-shrink-0">
          <div className="text-sm text-gray-500">
            {applying && (
              <span>
                Creating trades... ({appliedCount}/{selectedGroups.size})
              </span>
            )}
          </div>
          <div className="flex gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={applySelected}
              disabled={selectedGroups.size === 0 || applying || loading}
              className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {applying
                ? 'Applying...'
                : `Apply ${selectedGroups.size} Group${
                    selectedGroups.size !== 1 ? 's' : ''
                  }`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
