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
  sparklineColorByValue?: boolean; // Use metric value (not trend) to determine sparkline color
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

// Mini sparkline component using SVG with area fill
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
  const gradientId = useMemo(() => `sparkline-gradient-${Math.random().toString(36).substr(2, 9)}`, []);

  const { linePath, areaPath, singlePoint, min, max, hasPositive, hasNegative, zeroY } = useMemo(() => {
    if (!data || data.length === 0) return { linePath: '', areaPath: '', singlePoint: null, min: 0, max: 0, hasPositive: false, hasNegative: false, zeroY: 0 };

    const minVal = Math.min(...data);
    const maxVal = Math.max(...data);

    // Single data point - show a dot
    if (data.length === 1) {
      return {
        linePath: '',
        areaPath: '',
        singlePoint: { x: width / 2, y: height / 2 },
        min: minVal,
        max: maxVal,
        hasPositive: data[0] >= 0,
        hasNegative: data[0] < 0,
        zeroY: height / 2,
      };
    }

    const range = maxVal - minVal || 1;
    const padding = 2;
    const chartHeight = height - padding * 2;

    // Calculate zero line position
    const zeroYPos = maxVal <= 0
      ? padding
      : minVal >= 0
        ? height - padding
        : padding + ((maxVal - 0) / range) * chartHeight;

    const points = data.map((value, index) => {
      const x = (index / (data.length - 1)) * width;
      const y = padding + ((maxVal - value) / range) * chartHeight;
      return { x, y };
    });

    const linePoints = points.map(p => `${p.x},${p.y}`).join(' L ');
    const linePath = `M ${linePoints}`;

    // Create area path that fills to zero line (or bottom if all positive, top if all negative)
    const firstPoint = points[0];
    const lastPoint = points[points.length - 1];
    const areaPath = `M ${firstPoint.x},${zeroYPos} L ${linePoints} L ${lastPoint.x},${zeroYPos} Z`;

    return {
      linePath,
      areaPath,
      singlePoint: null,
      min: minVal,
      max: maxVal,
      hasPositive: maxVal >= 0,
      hasNegative: minVal < 0,
      zeroY: zeroYPos,
    };
  }, [data, width, height]);

  if (!data || data.length === 0) return null;

  const textColor = 'text-gray-400 dark:text-gray-500';

  // Single point - render a dot
  if (singlePoint) {
    const fillColor = positive
      ? 'fill-green-500 dark:fill-green-400'
      : 'fill-red-500 dark:fill-red-400';
    return (
      <div className="flex flex-col items-center">
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
    <div className="flex items-center gap-1 rounded border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50 px-2 py-1">
      {showScale && min !== max && (
        <div className="flex flex-col justify-between h-full">
          <span className={`text-[8px] leading-none ${textColor}`}>
            {formatScaleValue(max, scaleFormat)}
          </span>
          <span className={`text-[8px] leading-none ${textColor}`}>
            {formatScaleValue(min, scaleFormat)}
          </span>
        </div>
      )}
      <svg width={width} height={height} className="overflow-visible">
        <defs>
          <linearGradient id={`${gradientId}-green`} x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="rgb(34, 197, 94)" stopOpacity="0.4" />
            <stop offset="100%" stopColor="rgb(34, 197, 94)" stopOpacity="0.05" />
          </linearGradient>
          <linearGradient id={`${gradientId}-red`} x1="0%" y1="100%" x2="0%" y2="0%">
            <stop offset="0%" stopColor="rgb(239, 68, 68)" stopOpacity="0.4" />
            <stop offset="100%" stopColor="rgb(239, 68, 68)" stopOpacity="0.05" />
          </linearGradient>
        </defs>
        {/* Area fill */}
        <path
          d={areaPath}
          fill={positive ? `url(#${gradientId}-green)` : `url(#${gradientId}-red)`}
        />
        {/* Line stroke */}
        <path
          d={linePath}
          fill="none"
          stroke={positive ? 'rgb(34, 197, 94)' : 'rgb(239, 68, 68)'}
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
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
  sparklineColorByValue = false,
}: MetricCardProps) {
  const [showTooltip, setShowTooltip] = useState(false);
  const formattedValue = formatValue(value, format);
  const valueColor = getValueColor(value, format, invertColors);

  // Determine if sparkline trend is positive
  const sparklinePositive = useMemo(() => {
    // If sparklineColorByValue is true, use the metric value to determine color
    if (sparklineColorByValue) {
      const numValue = typeof value === 'string' ? parseFloat(value) : value;
      if (numValue === null || numValue === undefined || isNaN(numValue)) return true;
      return invertColors ? numValue <= 0 : numValue >= 0;
    }
    // Otherwise, compare first vs last values in the sparkline
    if (!sparklineData || sparklineData.length < 2) return true;
    const first = sparklineData[0];
    const last = sparklineData[sparklineData.length - 1];
    return invertColors ? last <= first : last >= first;
  }, [sparklineData, invertColors, sparklineColorByValue, value]);

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
    sm: 'p-2',
    md: 'p-3',
    lg: 'p-4',
  };

  const valueSizeClasses = {
    sm: 'text-xl',
    md: 'text-2xl',
    lg: 'text-3xl',
  };

  return (
    <div className={`relative rounded-lg bg-white shadow dark:bg-gray-800 ${sizeClasses[size]} text-center flex flex-col h-full`}>
      <div className="flex items-center justify-center gap-1">
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
              <Info className="h-3 w-3" />
            </button>
            {showTooltip && (
              <div className="absolute left-1/2 -translate-x-1/2 top-5 z-50 w-56 rounded-lg bg-gray-900 dark:bg-gray-700 p-2 text-xs text-white shadow-lg">
                {tooltip}
                <div className="absolute -top-1 left-1/2 -translate-x-1/2 h-2 w-2 rotate-45 bg-gray-900 dark:bg-gray-700" />
              </div>
            )}
          </div>
        )}
        {trend && (
          <span className={trend === 'up' ? 'text-green-600 dark:text-green-400' : trend === 'down' ? 'text-red-600 dark:text-red-400' : 'text-gray-500 dark:text-gray-400'}>
            {getTrendIcon(trend)}
          </span>
        )}
      </div>

      <div className="mt-0.5">
        <p className={`font-semibold ${valueColor} ${valueSizeClasses[size]}`}>
          {formattedValue}
        </p>
        {periodChange !== undefined && periodChange !== null && (
          <p className={`text-xs font-medium ${periodChangeColor}`}>
            {formatChange(periodChange, format)} from start
          </p>
        )}
        {subtitle && (
          <p className="text-xs text-gray-500 dark:text-gray-400">{subtitle}</p>
        )}
      </div>

      {sparklineData && sparklineData.length >= 1 && (
        <div className="mt-auto pt-2 flex justify-center">
          <Sparkline
            data={sparklineData}
            width={100}
            height={32}
            positive={sparklinePositive}
            showScale={showScale}
            scaleFormat={format}
          />
        </div>
      )}
    </div>
  );
}
