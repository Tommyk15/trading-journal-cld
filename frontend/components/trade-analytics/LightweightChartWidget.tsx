'use client';

import { useEffect, useRef, useState } from 'react';
import { createChart, IChartApi, ISeriesApi, Time, CandlestickSeries } from 'lightweight-charts';

interface CandleData {
  time: Time;
  open: number;
  high: number;
  low: number;
  close: number;
}

type TimeFrame = '1D' | '1W' | '1M' | '3M' | '6M' | '1Y';
type CandleInterval = '1m' | '5m' | '15m' | '1H' | '4H' | 'D';

interface LightweightChartWidgetProps {
  underlying: string;
  openedAt?: string;
  closedAt?: string;
  entryPrice?: number;
  exitPrice?: number;
  height?: number;
}

const TIMEFRAME_DAYS: Record<TimeFrame, number> = {
  '1D': 1,
  '1W': 7,
  '1M': 30,
  '3M': 90,
  '6M': 180,
  '1Y': 365,
};

const INTERVAL_CONFIG: Record<CandleInterval, { timespan: string; multiplier: number; label: string }> = {
  '1m': { timespan: 'minute', multiplier: 1, label: '1m' },
  '5m': { timespan: 'minute', multiplier: 5, label: '5m' },
  '15m': { timespan: 'minute', multiplier: 15, label: '15m' },
  '1H': { timespan: 'hour', multiplier: 1, label: '1H' },
  '4H': { timespan: 'hour', multiplier: 4, label: '4H' },
  'D': { timespan: 'day', multiplier: 1, label: 'D' },
};

export default function LightweightChartWidget({
  underlying,
  openedAt,
  closedAt,
  entryPrice,
  exitPrice,
  height = 300,
}: LightweightChartWidgetProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [timeframe, setTimeframe] = useState<TimeFrame>('3M');
  const [interval, setInterval] = useState<CandleInterval>('D');
  const [candles, setCandles] = useState<CandleData[]>([]);
  const [entryMarker, setEntryMarker] = useState<{ x: number; y: number } | null>(null);
  const [exitMarker, setExitMarker] = useState<{ x: number; y: number } | null>(null);

  // Fetch candle data from backend
  const fetchCandleData = async (tf: TimeFrame, intv: CandleInterval) => {
    setLoading(true);
    setError(null);

    try {
      const days = TIMEFRAME_DAYS[tf];
      const config = INTERVAL_CONFIG[intv];
      const response = await fetch(
        `http://localhost:8000/api/v1/market-data/${underlying}/candles?days=${days}&timespan=${config.timespan}&multiplier=${config.multiplier}`
      );

      if (!response.ok) {
        if (response.status === 404) {
          // No data for this period - likely weekend/holiday or too short range for intraday
          setError(`No market data available for ${tf} range. Try a longer time range.`);
          return;
        }
        throw new Error(`Failed to fetch candle data: ${response.status}`);
      }

      const data = await response.json();

      if (data.candles && data.candles.length > 0) {
        const formattedCandles: CandleData[] = data.candles.map((c: any) => ({
          time: Math.floor(new Date(c.timestamp).getTime() / 1000) as Time,
          open: Number(c.open),
          high: Number(c.high),
          low: Number(c.low),
          close: Number(c.close),
        }));
        setCandles(formattedCandles);
      } else {
        setError('No candle data available');
      }
    } catch (err) {
      console.error('Error fetching candles:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch chart data');
    } finally {
      setLoading(false);
    }
  };

  // Fetch data when timeframe, interval, or underlying changes
  useEffect(() => {
    if (underlying) {
      fetchCandleData(timeframe, interval);
    }
  }, [underlying, timeframe, interval]);

  // Create/update chart when candles change
  useEffect(() => {
    if (!chartContainerRef.current || candles.length === 0) return;

    // Clean up existing chart
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const isDarkMode = document.documentElement.classList.contains('dark');

    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height,
      layout: {
        background: { color: isDarkMode ? '#1f2937' : '#ffffff' },
        textColor: isDarkMode ? '#9ca3af' : '#374151',
      },
      grid: {
        vertLines: { color: isDarkMode ? '#374151' : '#e5e7eb' },
        horzLines: { color: isDarkMode ? '#374151' : '#e5e7eb' },
      },
      crosshair: {
        mode: 1,
      },
      rightPriceScale: {
        borderColor: isDarkMode ? '#374151' : '#e5e7eb',
      },
      timeScale: {
        borderColor: isDarkMode ? '#374151' : '#e5e7eb',
        timeVisible: true,
        secondsVisible: false,
      },
    });

    chartRef.current = chart;

    // Create candlestick series
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderUpColor: '#22c55e',
      borderDownColor: '#ef4444',
      wickUpColor: '#22c55e',
      wickDownColor: '#ef4444',
    });
    seriesRef.current = candleSeries as ISeriesApi<'Candlestick'>;

    // Set candle data
    candleSeries.setData(candles);

    // Find entry and exit candles
    let entryCandle: CandleData | undefined;
    let exitCandle: CandleData | undefined;

    if (openedAt) {
      const openTime = Math.floor(new Date(openedAt).getTime() / 1000);
      entryCandle = candles.find(c => (c.time as number) >= openTime) ||
                    candles.find(c => Math.abs((c.time as number) - openTime) < 86400);
    }

    if (closedAt) {
      const closeTime = Math.floor(new Date(closedAt).getTime() / 1000);
      exitCandle = candles.find(c => (c.time as number) >= closeTime) ||
                   candles.find(c => Math.abs((c.time as number) - closeTime) < 86400);
    }

    // Function to update marker positions
    const updateMarkerPositions = () => {
      if (entryCandle) {
        const x = chart.timeScale().timeToCoordinate(entryCandle.time);
        const y = candleSeries.priceToCoordinate(entryCandle.low);
        if (x !== null && y !== null) {
          setEntryMarker({ x, y: y + 5 }); // Position below the candle
        } else {
          setEntryMarker(null);
        }
      } else {
        setEntryMarker(null);
      }

      if (exitCandle) {
        const x = chart.timeScale().timeToCoordinate(exitCandle.time);
        const y = candleSeries.priceToCoordinate(exitCandle.high);
        if (x !== null && y !== null) {
          setExitMarker({ x, y: y - 20 }); // Position above the candle
        } else {
          setExitMarker(null);
        }
      } else {
        setExitMarker(null);
      }
    };

    chart.timeScale().fitContent();

    // Initial marker position update (after a small delay to ensure chart is rendered)
    setTimeout(updateMarkerPositions, 50);

    // Subscribe to visible range changes to update markers
    chart.timeScale().subscribeVisibleTimeRangeChange(updateMarkerPositions);

    // Handle resize
    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
        });
        // Update markers after resize
        setTimeout(updateMarkerPositions, 10);
      }
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.timeScale().unsubscribeVisibleTimeRangeChange(updateMarkerPositions);
      setEntryMarker(null);
      setExitMarker(null);
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, [candles, openedAt, closedAt, height]);

  const timeframes: TimeFrame[] = ['1D', '1W', '1M', '3M', '6M', '1Y'];
  const intervals: CandleInterval[] = ['1m', '5m', '15m', '1H', '4H', 'D'];

  return (
    <div className="space-y-2">
      {/* Chart header with selectors */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
          {underlying} Price Chart
        </span>
        <div className="flex items-center gap-3">
          {/* Interval selector */}
          <div className="flex items-center gap-1">
            <span className="text-xs text-gray-500 dark:text-gray-400 mr-1">Interval:</span>
            {intervals.map((intv) => (
              <button
                key={intv}
                onClick={() => setInterval(intv)}
                className={`px-2 py-1 text-xs rounded ${
                  interval === intv
                    ? 'bg-green-600 text-white'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                }`}
              >
                {INTERVAL_CONFIG[intv].label}
              </button>
            ))}
          </div>
          {/* Timeframe selector */}
          <div className="flex items-center gap-1">
            <span className="text-xs text-gray-500 dark:text-gray-400 mr-1">Range:</span>
            {timeframes.map((tf) => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={`px-2 py-1 text-xs rounded ${
                  timeframe === tf
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Chart container */}
      <div className="relative">
        {loading && (
          <div
            className="absolute inset-0 flex items-center justify-center bg-gray-50 dark:bg-gray-800 rounded-lg z-10"
            style={{ height }}
          >
            <div className="animate-pulse text-sm text-gray-500 dark:text-gray-400">
              Loading chart...
            </div>
          </div>
        )}

        {error && !loading && (
          <div
            className="flex items-center justify-center bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700"
            style={{ height }}
          >
            <p className="text-sm text-gray-500 dark:text-gray-400">{error}</p>
          </div>
        )}

        {/* Chart with markers wrapper */}
        <div className="relative" style={{ height }}>
          <div
            ref={chartContainerRef}
            className={`rounded-lg overflow-hidden ${error && !loading ? 'hidden' : ''}`}
            style={{ height: '100%' }}
          />

          {/* Entry marker arrow */}
          {entryMarker && !loading && !error && (
            <div
              className="absolute pointer-events-none z-20 flex flex-col items-center"
              style={{
                left: entryMarker.x,
                top: entryMarker.y,
                transform: 'translateX(-50%)',
              }}
            >
              <span className="text-green-500 text-xl font-bold" style={{ textShadow: '0 0 4px rgba(0,0,0,0.8)' }}>▲</span>
              {entryPrice && (
                <span className="text-[10px] font-bold text-green-400 bg-black/70 px-1 rounded whitespace-nowrap">
                  ${Number(entryPrice).toFixed(2)}
                </span>
              )}
            </div>
          )}

          {/* Exit marker arrow */}
          {exitMarker && !loading && !error && (
            <div
              className="absolute pointer-events-none z-20 flex flex-col items-center"
              style={{
                left: exitMarker.x,
                top: exitMarker.y,
                transform: 'translateX(-50%)',
              }}
            >
              {exitPrice && (
                <span className="text-[10px] font-bold text-red-400 bg-black/70 px-1 rounded whitespace-nowrap">
                  ${Number(exitPrice).toFixed(2)}
                </span>
              )}
              <span className="text-red-500 text-xl font-bold" style={{ textShadow: '0 0 4px rgba(0,0,0,0.8)' }}>▼</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
