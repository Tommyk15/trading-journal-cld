'use client';

import { useState, useEffect } from 'react';
import { Header } from '@/components/layout/Header';
import { Settings as SettingsIcon, Database, Bell, User, Upload, Check, X, TrendingDown, Plus, Trash2, Clock } from 'lucide-react';
import { api } from '@/lib/api/client';
import { useTimezone, TIMEZONE_OPTIONS } from '@/contexts/TimezoneContext';

interface StockSplit {
  id: number;
  symbol: string;
  split_date: string;
  ratio_from: number;
  ratio_to: number;
  description: string | null;
  adjustment_factor: string;
  price_factor: string;
  is_reverse_split: boolean;
}

export default function SettingsPage() {
  const { timezone, setTimezone, getTimezoneAbbr } = useTimezone();
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<{
    success: boolean;
    message: string;
  } | null>(null);

  // Stock splits state
  const [stockSplits, setStockSplits] = useState<StockSplit[]>([]);
  const [loadingSplits, setLoadingSplits] = useState(false);
  const [showAddSplit, setShowAddSplit] = useState(false);
  const [newSplit, setNewSplit] = useState({
    symbol: '',
    split_date: '',
    ratio_from: '',
    ratio_to: '',
    description: ''
  });
  const [savingSplit, setSavingSplit] = useState(false);
  const [splitError, setSplitError] = useState<string | null>(null);

  // Fetch stock splits on mount
  useEffect(() => {
    fetchStockSplits();
  }, []);

  async function fetchStockSplits() {
    try {
      setLoadingSplits(true);
      const response = await fetch('http://localhost:8000/api/v1/stock-splits');
      const data = await response.json();
      setStockSplits(data.splits || []);
    } catch (error) {
      console.error('Error fetching stock splits:', error);
    } finally {
      setLoadingSplits(false);
    }
  }

  async function handleAddSplit() {
    if (!newSplit.symbol || !newSplit.split_date || !newSplit.ratio_from || !newSplit.ratio_to) {
      setSplitError('Please fill in all required fields');
      return;
    }

    try {
      setSavingSplit(true);
      setSplitError(null);

      const response = await fetch('http://localhost:8000/api/v1/stock-splits', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: newSplit.symbol.toUpperCase(),
          split_date: new Date(newSplit.split_date).toISOString(),
          ratio_from: parseInt(newSplit.ratio_from),
          ratio_to: parseInt(newSplit.ratio_to),
          description: newSplit.description || null
        })
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to add stock split');
      }

      // Reset form and refresh list
      setNewSplit({ symbol: '', split_date: '', ratio_from: '', ratio_to: '', description: '' });
      setShowAddSplit(false);
      await fetchStockSplits();
    } catch (error) {
      setSplitError(error instanceof Error ? error.message : 'Failed to add stock split');
    } finally {
      setSavingSplit(false);
    }
  }

  async function handleDeleteSplit(splitId: number) {
    if (!confirm('Are you sure you want to delete this stock split?')) return;

    try {
      const response = await fetch(`http://localhost:8000/api/v1/stock-splits/${splitId}`, {
        method: 'DELETE'
      });

      if (!response.ok) {
        throw new Error('Failed to delete stock split');
      }

      await fetchStockSplits();
    } catch (error) {
      console.error('Error deleting stock split:', error);
    }
  }

  async function handleFileUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      setUploading(true);
      setUploadResult(null);

      const result = await api.executions.upload(file);

      setUploadResult({
        success: true,
        message: result.message || `Imported ${result.new} executions successfully!`
      });

      // Reset file input
      event.target.value = '';
    } catch (error) {
      setUploadResult({
        success: false,
        message: error instanceof Error ? error.message : 'Upload failed'
      });
    } finally {
      setUploading(false);
    }
  }
  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900 transition-colors">
      <Header
        title="Settings"
        subtitle="Configure your trading journal preferences"
      />

      <div className="p-6 space-y-6">
        {/* API Configuration */}
        <div className="rounded-lg bg-white dark:bg-gray-800 p-6 shadow transition-colors">
          <div className="flex items-center gap-2 mb-4">
            <Database className="h-5 w-5 text-blue-600" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              API Configuration
            </h2>
          </div>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                Backend API URL
              </label>
              <input
                type="text"
                defaultValue={process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}
                className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
                disabled
              />
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                Configure this in your .env.local file
              </p>
            </div>
          </div>
        </div>

        {/* IBKR Settings */}
        <div className="rounded-lg bg-white dark:bg-gray-800 p-6 shadow transition-colors">
          <div className="flex items-center gap-2 mb-4">
            <SettingsIcon className="h-5 w-5 text-blue-600" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              Interactive Brokers
            </h2>
          </div>
          <div className="space-y-4">
            <div className="rounded-lg bg-blue-50 dark:bg-blue-900/30 p-4">
              <h3 className="text-sm font-medium text-blue-900 dark:text-blue-200">
                IBKR Connection Status
              </h3>
              <p className="mt-2 text-sm text-blue-700 dark:text-blue-300">
                To sync data from Interactive Brokers, ensure:
              </p>
              <ul className="mt-2 list-disc list-inside text-sm text-blue-700 dark:text-blue-300 space-y-1">
                <li>TWS or IB Gateway is running</li>
                <li>API connections are enabled in TWS settings</li>
                <li>The backend service is configured with your credentials</li>
              </ul>
            </div>
          </div>
        </div>

        {/* Flex Query Upload */}
        <div className="rounded-lg bg-white dark:bg-gray-800 p-6 shadow transition-colors">
          <div className="flex items-center gap-2 mb-4">
            <Upload className="h-5 w-5 text-blue-600" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              Import Historical Data
            </h2>
          </div>
          <div className="space-y-4">
            <div>
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                Upload a Flex Query report from IBKR to import historical trades and executions.
              </p>
              <div className="rounded-lg bg-gray-50 dark:bg-gray-700 p-4 mb-4">
                <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-2">
                  How to download Flex Query:
                </h3>
                <ol className="list-decimal list-inside text-sm text-gray-700 dark:text-gray-300 space-y-1">
                  <li>Log in to IBKR Account Management</li>
                  <li>Go to Performance & Reports → Flex Queries</li>
                  <li>Run your Flex Query for executions/trades</li>
                  <li>Download the report (CSV or XML format)</li>
                  <li>Upload the file below</li>
                </ol>
              </div>

              <div className="flex items-center gap-4">
                <label className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 cursor-pointer transition-colors">
                  <Upload className="h-4 w-4" />
                  <span>{uploading ? 'Uploading...' : 'Choose File'}</span>
                  <input
                    type="file"
                    accept=".csv,.xml"
                    onChange={handleFileUpload}
                    disabled={uploading}
                    className="hidden"
                  />
                </label>
                {uploading && (
                  <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
                    <div className="animate-spin h-4 w-4 border-2 border-blue-600 border-t-transparent rounded-full" />
                    Importing executions...
                  </div>
                )}
              </div>

              {uploadResult && (
                <div
                  className={`mt-4 p-4 rounded-lg flex items-start gap-3 ${
                    uploadResult.success
                      ? 'bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800'
                      : 'bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800'
                  }`}
                >
                  {uploadResult.success ? (
                    <Check className="h-5 w-5 text-green-600 dark:text-green-400 flex-shrink-0 mt-0.5" />
                  ) : (
                    <X className="h-5 w-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
                  )}
                  <div className="flex-1">
                    <p
                      className={`text-sm font-medium ${
                        uploadResult.success ? 'text-green-900 dark:text-green-200' : 'text-red-900 dark:text-red-200'
                      }`}
                    >
                      {uploadResult.success ? 'Success!' : 'Upload Failed'}
                    </p>
                    <p
                      className={`text-sm mt-1 ${
                        uploadResult.success ? 'text-green-700 dark:text-green-300' : 'text-red-700 dark:text-red-300'
                      }`}
                    >
                      {uploadResult.message}
                    </p>
                    {uploadResult.success && (
                      <p className="text-sm text-green-600 dark:text-green-400 mt-2">
                        Go to the Trades page and click "Process Executions" to group them into trades.
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Stock Splits */}
        <div className="rounded-lg bg-white dark:bg-gray-800 p-6 shadow transition-colors">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <TrendingDown className="h-5 w-5 text-blue-600" />
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                Stock Splits
              </h2>
            </div>
            <button
              onClick={() => setShowAddSplit(!showAddSplit)}
              className="flex items-center gap-1 px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
            >
              <Plus className="h-4 w-4" />
              Add Split
            </button>
          </div>

          <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
            Stock splits adjust position quantities and prices for historical trades.
            Add splits here to ensure correct display of split-adjusted holdings.
          </p>

          {/* Add Split Form */}
          {showAddSplit && (
            <div className="mb-4 p-4 bg-gray-50 dark:bg-gray-700 rounded-lg">
              <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-3">
                Add New Stock Split
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Symbol *
                  </label>
                  <input
                    type="text"
                    placeholder="AAPL"
                    value={newSplit.symbol}
                    onChange={(e) => setNewSplit({ ...newSplit, symbol: e.target.value })}
                    className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Split Date *
                  </label>
                  <input
                    type="date"
                    value={newSplit.split_date}
                    onChange={(e) => setNewSplit({ ...newSplit, split_date: e.target.value })}
                    className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                    From (old) *
                  </label>
                  <input
                    type="number"
                    placeholder="4"
                    min="1"
                    value={newSplit.ratio_from}
                    onChange={(e) => setNewSplit({ ...newSplit, ratio_from: e.target.value })}
                    className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                    To (new) *
                  </label>
                  <input
                    type="number"
                    placeholder="1"
                    min="1"
                    value={newSplit.ratio_to}
                    onChange={(e) => setNewSplit({ ...newSplit, ratio_to: e.target.value })}
                    className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Description
                  </label>
                  <input
                    type="text"
                    placeholder="4:1 reverse split"
                    value={newSplit.description}
                    onChange={(e) => setNewSplit({ ...newSplit, description: e.target.value })}
                    className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                  />
                </div>
              </div>
              {splitError && (
                <p className="mt-2 text-sm text-red-600 dark:text-red-400">{splitError}</p>
              )}
              <div className="mt-3 flex gap-2">
                <button
                  onClick={handleAddSplit}
                  disabled={savingSplit}
                  className="px-4 py-2 text-sm bg-green-600 text-white rounded-md hover:bg-green-700 disabled:opacity-50 transition-colors"
                >
                  {savingSplit ? 'Saving...' : 'Save Split'}
                </button>
                <button
                  onClick={() => {
                    setShowAddSplit(false);
                    setSplitError(null);
                    setNewSplit({ symbol: '', split_date: '', ratio_from: '', ratio_to: '', description: '' });
                  }}
                  className="px-4 py-2 text-sm bg-gray-200 dark:bg-gray-600 text-gray-700 dark:text-gray-200 rounded-md hover:bg-gray-300 dark:hover:bg-gray-500 transition-colors"
                >
                  Cancel
                </button>
              </div>
              <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                For a 4:1 reverse split (4 shares become 1), enter From=4, To=1.
                For a 4:1 forward split (1 share becomes 4), enter From=1, To=4.
              </p>
            </div>
          )}

          {/* Stock Splits List */}
          {loadingSplits ? (
            <div className="text-center py-4 text-gray-500 dark:text-gray-400">
              Loading stock splits...
            </div>
          ) : stockSplits.length === 0 ? (
            <div className="text-center py-4 text-gray-500 dark:text-gray-400">
              No stock splits recorded yet.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                <thead className="bg-gray-50 dark:bg-gray-700">
                  <tr>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase">Symbol</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase">Date</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase">Ratio</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase">Type</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase">Description</th>
                    <th className="px-4 py-2 text-right text-xs font-medium text-gray-500 dark:text-gray-300 uppercase">Actions</th>
                  </tr>
                </thead>
                <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                  {stockSplits.map((split) => (
                    <tr key={split.id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                      <td className="px-4 py-2 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-white">
                        {split.symbol}
                      </td>
                      <td className="px-4 py-2 whitespace-nowrap text-sm text-gray-900 dark:text-white">
                        {new Date(split.split_date).toLocaleDateString()}
                      </td>
                      <td className="px-4 py-2 whitespace-nowrap text-sm text-gray-900 dark:text-white">
                        {split.ratio_from}:{split.ratio_to}
                      </td>
                      <td className="px-4 py-2 whitespace-nowrap text-sm">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                          split.is_reverse_split
                            ? 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400'
                            : 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400'
                        }`}>
                          {split.is_reverse_split ? 'Reverse' : 'Forward'}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-sm text-gray-500 dark:text-gray-400">
                        {split.description || '-'}
                      </td>
                      <td className="px-4 py-2 whitespace-nowrap text-right">
                        <button
                          onClick={() => handleDeleteSplit(split.id)}
                          className="text-red-600 dark:text-red-400 hover:text-red-800 dark:hover:text-red-300"
                          title="Delete split"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Display Preferences */}
        <div className="rounded-lg bg-white dark:bg-gray-800 p-6 shadow transition-colors">
          <div className="flex items-center gap-2 mb-4">
            <User className="h-5 w-5 text-blue-600" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              Display Preferences
            </h2>
          </div>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                <div className="flex items-center gap-2">
                  <Clock className="h-4 w-4" />
                  Timezone
                </div>
              </label>
              <select
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
              >
                {TIMEZONE_OPTIONS.map((tz) => (
                  <option key={tz.value} value={tz.value}>
                    {tz.label}
                  </option>
                ))}
              </select>
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                Current time: {new Date().toLocaleTimeString('en-US', { timeZone: timezone, hour: '2-digit', minute: '2-digit', timeZoneName: 'short' })}
              </p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                Currency Display
              </label>
              <select
                defaultValue="USD"
                className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
              >
                <option value="USD">USD ($)</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                Date Format
              </label>
              <select
                defaultValue="US"
                className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
              >
                <option value="US">MM/DD/YYYY</option>
                <option value="EU">DD/MM/YYYY</option>
                <option value="ISO">YYYY-MM-DD</option>
              </select>
            </div>
          </div>
        </div>

        {/* Notifications */}
        <div className="rounded-lg bg-white dark:bg-gray-800 p-6 shadow transition-colors">
          <div className="flex items-center gap-2 mb-4">
            <Bell className="h-5 w-5 text-blue-600" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              Notifications
            </h2>
          </div>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-900 dark:text-white">
                  Expiration Alerts
                </p>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Get notified about upcoming option expirations
                </p>
              </div>
              <input
                type="checkbox"
                defaultChecked
                className="h-4 w-4 rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-blue-500"
              />
            </div>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-900 dark:text-white">
                  Large P&L Moves
                </p>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Alert on significant profit or loss events
                </p>
              </div>
              <input
                type="checkbox"
                defaultChecked
                className="h-4 w-4 rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-blue-500"
              />
            </div>
          </div>
        </div>

        {/* About */}
        <div className="rounded-lg bg-white dark:bg-gray-800 p-6 shadow transition-colors">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">About</h2>
          <div className="space-y-2 text-sm text-gray-600 dark:text-gray-400">
            <p>
              <span className="font-medium">Version:</span> 1.0.0 (Phase 3)
            </p>
            <p>
              <span className="font-medium">Backend API:</span>{' '}
              {process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}
            </p>
            <p className="mt-4 text-xs text-gray-500 dark:text-gray-400">
              Trading Journal - Options Trading Analytics Platform
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
