'use client';

import { useState } from 'react';
import { Header } from '@/components/layout/Header';
import { Settings as SettingsIcon, Database, Bell, User, Upload, Check, X } from 'lucide-react';
import { api } from '@/lib/api/client';

export default function SettingsPage() {
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<{
    success: boolean;
    message: string;
  } | null>(null);

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
