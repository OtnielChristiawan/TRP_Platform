import React from "react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import type { DailySalesItem } from "../../types/api";
import { formatDateIndo, formatRupiah } from "../../utils/formatters";

interface SalesTrendChartProps {
  data: DailySalesItem[];
}

export const SalesTrendChart: React.FC<SalesTrendChartProps> = ({ data }) => {
  const chartData = data.map((d) => ({
    ...d,
    formattedDate: formatDateIndo(d.sales_date),
  }));

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const row = payload[0].payload;
      return (
        <div className="bg-[#1e1b18] text-white p-3 rounded-lg text-xs shadow-lg border border-stone-800">
          <p className="font-semibold text-stone-200 mb-1">{row.formattedDate}</p>
          <p className="text-amber-400 font-bold">{formatRupiah(row.net_sales)}</p>
          <div className="mt-1.5 pt-1.5 border-t border-stone-700 space-y-0.5 text-stone-300">
            <p>Total Bills: <span className="font-medium text-white">{row.total_bills}</span></p>
            <p>Produk Terjual: <span className="font-medium text-white">{row.total_qty_sold} unit</span></p>
            <p>AOV: <span className="font-medium text-white">{formatRupiah(row.average_order_value)}</span></p>
          </div>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="w-full h-72">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="salesGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#7c3f15" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#7c3f15" stopOpacity={0.0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#ede8df" />
          <XAxis
            dataKey="formattedDate"
            tick={{ fontSize: 11, fill: "#8c8275" }}
            axisLine={{ stroke: "#ede8df" }}
            tickLine={false}
          />
          <YAxis
            tickFormatter={(val) => `${(val / 1000000).toFixed(1)}jt`}
            tick={{ fontSize: 11, fill: "#8c8275" }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={<CustomTooltip />} />
          <Area
            type="monotone"
            dataKey="net_sales"
            stroke="#7c3f15"
            strokeWidth={2.5}
            fillOpacity={1}
            fill="url(#salesGrad)"
            activeDot={{ r: 5, fill: "#7c3f15", stroke: "#ffffff", strokeWidth: 2 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
};
