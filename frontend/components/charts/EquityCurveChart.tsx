'use client';

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { formatCurrency, formatDate } from '@/lib/utils';
import type { CumulativePnL } from '@/types';

interface EquityCurveChartProps {
  data: CumulativePnL[];
  height?: number;
}

export function EquityCurveChart({ data, height = 400 }: EquityCurveChartProps) {
  const chartData = data.map((item) => ({
    date: formatDate(item.date),
    pnl: item.cumulative_pnl,
    trades: item.trade_count,
  }));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 12 }}
          stroke="#666"
        />
        <YAxis
          tick={{ fontSize: 12 }}
          stroke="#666"
          tickFormatter={(value) => formatCurrency(value)}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: '#fff',
            border: '1px solid #ccc',
            borderRadius: '4px',
          }}
          formatter={(value: number, name: string) => {
            if (name === 'pnl') return [formatCurrency(value), 'Cumulative P&L'];
            return [value, 'Trades'];
          }}
        />
        <Legend />
        <Line
          type="monotone"
          dataKey="pnl"
          stroke="#2563eb"
          strokeWidth={2}
          dot={false}
          name="Cumulative P&L"
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
