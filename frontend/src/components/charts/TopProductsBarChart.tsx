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
import type { TopMenuItem } from "../../types/api";
import { formatNumber, formatRupiah } from "../../utils/formatters";

interface TopProductsBarChartProps {
  data: TopMenuItem[];
  metric?: "sales" | "quantity";
}

export const TopProductsBarChart: React.FC<TopProductsBarChartProps> = ({
  data,
  metric = "sales",
}) => {
  const chartData = data.slice(0, 5).map((d) => ({
    ...d,
    shortName: d.menu_name.length > 18 ? `${d.menu_name.slice(0, 16)}...` : d.menu_name,
  }));

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const row = payload[0].payload;
      return (
        <div className="bg-[#1e1b18] text-white p-3 rounded-lg text-xs shadow-lg border border-stone-800">
          <p className="font-semibold text-stone-200 mb-1">{row.menu_name}</p>
          <p className="text-amber-400 font-bold">{formatRupiah(row.net_sales)}</p>
          <div className="mt-1 pt-1 border-t border-stone-700 text-stone-300">
            <p>Terjual: <span className="font-medium text-white">{formatNumber(row.qty_sold)} unit</span></p>
            <p>Transaksi: <span className="font-medium text-white">{row.total_bills} bills</span></p>
            <p>Kategori: <span className="font-medium text-stone-300">{row.menu_category || "-"}</span></p>
          </div>
        </div>
      );
    }
    return null;
  };

  const isSales = metric === "sales";

  return (
    <div className="w-full h-72">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          layout="vertical"
          data={chartData}
          margin={{ top: 10, right: 20, left: 20, bottom: 0 }}
        >
          <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#ede8df" />
          <XAxis
            type="number"
            tickFormatter={(val) =>
              isSales ? `${(val / 1000000).toFixed(1)}jt` : `${val}`
            }
            tick={{ fontSize: 11, fill: "#8c8275" }}
            axisLine={{ stroke: "#ede8df" }}
            tickLine={false}
          />
          <YAxis
            type="category"
            dataKey="shortName"
            tick={{ fontSize: 11, fill: "#4a4238" }}
            axisLine={false}
            tickLine={false}
            width={110}
          />
          <Tooltip content={<CustomTooltip />} />
          <Bar
            dataKey={isSales ? "net_sales" : "qty_sold"}
            fill="#7c3f15"
            radius={[0, 4, 4, 0]}
            maxBarSize={22}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
};
