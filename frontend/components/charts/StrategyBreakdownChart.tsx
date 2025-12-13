'use client';

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { formatCurrency, formatPercent } from '@/lib/utils';
import type { StrategyBreakdown } from '@/types';

interface StrategyBreakdownChartProps {
  data: StrategyBreakdown[];
  height?: number;
}

export function StrategyBreakdownChart({
  data,
  height = 400,
}: StrategyBreakdownChartProps) {
  const chartData = (data || []).map((item: any) => ({
    strategy: (item.strategy_type || item.strategy || '').replace(/_/g, ' '),
    pnl: parseFloat(item.total_pnl || item.net_pnl || 0),
    trades: item.total_trades || item.trade_count || 0,
    winRate: item.win_rate || 0,
  }));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
        <XAxis
          dataKey="strategy"
          tick={{ fontSize: 12 }}
          stroke="#666"
          angle={-45}
          textAnchor="end"
          height={100}
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
            if (name === 'pnl') return [formatCurrency(value), 'Total P&L'];
            if (name === 'winRate') return [formatPercent(value / 100), 'Win Rate'];
            return [value, 'Trades'];
          }}
        />
        <Legend />
        <Bar dataKey="pnl" fill="#2563eb" name="Total P&L" />
      </BarChart>
    </ResponsiveContainer>
  );
}
