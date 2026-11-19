import React from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import type { HourlySalesItem } from "../../types/api";
import { formatHour, formatRupiah } from "../../utils/formatters";

interface HourlySalesChartProps {
  data: HourlySalesItem[];
}

export const HourlySalesChart: React.FC<HourlySalesChartProps> = ({ data }) => {
  const chartData = data.map((d) => ({
    ...d,
    hourLabel: formatHour(d.sales_hour),
  }));

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const row = payload[0].payload;
      return (
        <div className="bg-[#1e1b18] text-white p-3 rounded-lg text-xs shadow-lg border border-stone-800">
          <p className="font-semibold text-stone-200 mb-1">Pukul {row.hourLabel}</p>
          <p className="text-amber-400 font-bold">{formatRupiah(row.net_sales)}</p>
          <div className="mt-1 pt-1 border-t border-stone-700 text-stone-300">
            <p>Total Bills: <span className="font-medium text-white">{row.total_bills}</span></p>
            <p>Qty: <span className="font-medium text-white">{row.total_qty_sold} unit</span></p>
          </div>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="w-full h-72">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#ede8df" />
          <XAxis
            dataKey="hourLabel"
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
          <Bar
            dataKey="net_sales"
            fill="#c86d51"
            radius={[4, 4, 0, 0]}
            maxBarSize={32}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
};
