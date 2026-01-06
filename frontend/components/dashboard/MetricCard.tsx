'use client';

import { useState, useMemo } from 'react';
import { TrendingUp, TrendingDown, Minus, Info } from 'lucide-react';

type MetricFormat = 'currency' | 'percent' | 'number' | 'ratio';
type TrendType = 'up' | 'down' | 'neutral';

interface MetricCardProps {
  title: string;
  value: number | string | null | undefined;
  format?: MetricFormat;
  trend?: TrendType;
  subtitle?: string;
  size?: 'sm' | 'md' | 'lg';
  tooltip?: string;
  sparklineData?: number[];
  periodChange?: number;
  invertColors?: boolean; // For metrics where lower is better (e.g., drawdown)
  showScale?: boolean; // Show min/max scale on sparkline
}

function formatValue(value: number | string | null | undefined, format: MetricFormat): string {
  if (value === null || value === undefined) return '-';

  const numValue = typeof value === 'string' ? parseFloat(value) : value;

  if (isNaN(numValue)) return String(value);

  switch (format) {
    case 'currency':
      return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
      }).format(numValue);
    case 'percent':
      return `${numValue.toFixed(1)}%`;
    case 'ratio':
      return numValue.toFixed(2);
    case 'number':
    default:
      return numValue.toLocaleString();
  }
}

function formatChange(value: number, format: MetricFormat): string {
  const prefix = value >= 0 ? '+' : '';
  switch (format) {
    case 'currency':
      return `${prefix}${new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
      }).format(value)}`;
    case 'percent':
      return `${prefix}${value.toFixed(1)}%`;
    case 'ratio':
      return `${prefix}${value.toFixed(2)}`;
    case 'number':
    default:
      return `${prefix}${value.toLocaleString()}`;
  }
}

function getValueColor(
  value: number | string | null | undefined,
  format: MetricFormat,
  invertColors: boolean = false
): string {
  if (value === null || value === undefined) return 'text-gray-900 dark:text-white';

  const numValue = typeof value === 'string' ? parseFloat(value) : value;
  if (isNaN(numValue)) return 'text-gray-900 dark:text-white';

  const isPositive = invertColors ? numValue < 0 : numValue > 0;
  const isNegative = invertColors ? numValue > 0 : numValue < 0;

  if (isPositive) return 'text-green-600 dark:text-green-400';
  if (isNegative) return 'text-red-600 dark:text-red-400';
  return 'text-gray-900 dark:text-white';
}

function getTrendIcon(trend: TrendType) {
  if (trend === 'up') return <TrendingUp className="h-4 w-4" />;
  if (trend === 'down') return <TrendingDown className="h-4 w-4" />;
  return <Minus className="h-4 w-4" />;
}

// Format scale value compactly
function formatScaleValue(value: number, format?: 'currency' | 'percent' | 'number' | 'ratio'): string {
  if (format === 'currency') {
    if (Math.abs(value) >= 1000) {
      return `$${(value / 1000).toFixed(0)}k`;
    }
    return `$${value.toFixed(0)}`;
  }
  if (format === 'percent') {
    return `${value.toFixed(0)}%`;
  }
  if (format === 'ratio') {
    return value.toFixed(1);
  }
  if (Math.abs(value) >= 1000) {
    return `${(value / 1000).toFixed(0)}k`;
  }
  return value.toFixed(0);
}

// Mini sparkline component using SVG
function Sparkline({
  data,
  width = 80,
  height = 24,
  positive = true,
  showScale = false,
  scaleFormat,
}: {
  data: number[];
  width?: number;
  height?: number;
  positive?: boolean;
  showScale?: boolean;
  scaleFormat?: 'currency' | 'percent' | 'number' | 'ratio';
}) {
  const { path, singlePoint, min, max } = useMemo(() => {
    if (!data || data.length === 0) return { path: '', singlePoint: null, min: 0, max: 0 };

    const minVal = Math.min(...data);
    const maxVal = Math.max(...data);

    // Single data point - show a dot
    if (data.length === 1) {
      return {
        path: '',
        singlePoint: { x: width / 2, y: height / 2 },
        min: minVal,
        max: maxVal,
      };
    }

    const range = maxVal - minVal || 1;

    const points = data.map((value, index) => {
      const x = (index / (data.length - 1)) * width;
      const y = height - ((value - minVal) / range) * (height - 4) - 2;
      return `${x},${y}`;
    });

    return { path: `M ${points.join(' L ')}`, singlePoint: null, min: minVal, max: maxVal };
  }, [data, width, height]);

  if (!data || data.length === 0) return null;

  const strokeColor = positive
    ? 'stroke-green-500 dark:stroke-green-400'
    : 'stroke-red-500 dark:stroke-red-400';
  const fillColor = positive
    ? 'fill-green-500 dark:fill-green-400'
    : 'fill-red-500 dark:fill-red-400';
  const textColor = 'text-gray-400 dark:text-gray-500';

  // Single point - render a dot
  if (singlePoint) {
    return (
      <div className="flex flex-col items-end">
        <svg width={width} height={height} className="overflow-visible">
          <circle
            cx={singlePoint.x}
            cy={singlePoint.y}
            r={3}
            className={fillColor}
          />
        </svg>
        {showScale && (
          <span className={`text-[9px] ${textColor}`}>
            {formatScaleValue(data[0], scaleFormat)}
          </span>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col items-end">
      {showScale && min !== max && (
        <span className={`text-[9px] leading-none ${textColor}`}>
          {formatScaleValue(max, scaleFormat)}
        </span>
      )}
      <svg width={width} height={height} className="overflow-visible">
        <path
          d={path}
          fill="none"
          className={strokeColor}
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      {showScale && min !== max && (
        <span className={`text-[9px] leading-none ${textColor}`}>
          {formatScaleValue(min, scaleFormat)}
        </span>
      )}
    </div>
  );
}

export function MetricCard({
  title,
  value,
  format = 'number',
  trend,
  subtitle,
  size = 'md',
  tooltip,
  sparklineData,
  periodChange,
  invertColors = false,
  showScale = false,
}: MetricCardProps) {
  const [showTooltip, setShowTooltip] = useState(false);
  const formattedValue = formatValue(value, format);
  const valueColor = getValueColor(value, format, invertColors);

  // Determine if sparkline trend is positive
  const sparklinePositive = useMemo(() => {
    if (!sparklineData || sparklineData.length < 2) return true;
    const first = sparklineData[0];
    const last = sparklineData[sparklineData.length - 1];
    return invertColors ? last <= first : last >= first;
  }, [sparklineData, invertColors]);

  // Determine period change color
  const periodChangeColor = useMemo(() => {
    if (periodChange === undefined || periodChange === null) return '';
    const isPositive = invertColors ? periodChange < 0 : periodChange > 0;
    const isNegative = invertColors ? periodChange > 0 : periodChange < 0;
    if (isPositive) return 'text-green-600 dark:text-green-400';
    if (isNegative) return 'text-red-600 dark:text-red-400';
    return 'text-gray-500 dark:text-gray-400';
  }, [periodChange, invertColors]);

  const sizeClasses = {
    sm: 'p-3',
    md: 'p-4',
    lg: 'p-6',
  };

  const valueSizeClasses = {
    sm: 'text-lg',
    md: 'text-2xl',
    lg: 'text-3xl',
  };

  return (
    <div className={`relative rounded-lg bg-white shadow dark:bg-gray-800 ${sizeClasses[size]}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1">
          <p className="text-sm font-medium text-gray-500 dark:text-gray-400">{title}</p>
          {tooltip && (
            <div className="relative">
              <button
                type="button"
                className="text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 focus:outline-none"
                onMouseEnter={() => setShowTooltip(true)}
                onMouseLeave={() => setShowTooltip(false)}
                onClick={() => setShowTooltip(!showTooltip)}
                aria-label="More info"
              >
                <Info className="h-3.5 w-3.5" />
              </button>
              {showTooltip && (
                <div className="absolute left-0 top-6 z-50 w-64 rounded-lg bg-gray-900 dark:bg-gray-700 p-2 text-xs text-white shadow-lg">
                  {tooltip}
                  <div className="absolute -top-1 left-2 h-2 w-2 rotate-45 bg-gray-900 dark:bg-gray-700" />
                </div>
              )}
            </div>
          )}
        </div>
        {trend && (
          <span className={trend === 'up' ? 'text-green-600 dark:text-green-400' : trend === 'down' ? 'text-red-600 dark:text-red-400' : 'text-gray-500 dark:text-gray-400'}>
            {getTrendIcon(trend)}
          </span>
        )}
      </div>

      <div className="flex items-end justify-between mt-1">
        <div className="flex-1">
          <p className={`font-semibold ${valueColor} ${valueSizeClasses[size]}`}>
            {formattedValue}
          </p>
          {periodChange !== undefined && periodChange !== null && (
            <p className={`text-xs font-medium ${periodChangeColor}`}>
              {formatChange(periodChange, format)} from start
            </p>
          )}
          {subtitle && (
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{subtitle}</p>
          )}
        </div>

        {sparklineData && sparklineData.length >= 1 && (
          <div className="ml-2 flex-shrink-0">
            <Sparkline
              data={sparklineData}
              positive={sparklinePositive}
              showScale={showScale}
              scaleFormat={format}
            />
          </div>
        )}
      </div>
    </div>
  );
}
