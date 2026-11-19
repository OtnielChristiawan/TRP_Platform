import React from "react";
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
} from "recharts";
import type { CategoryPerformanceItem } from "../../types/api";
import { formatPercent, formatRupiah } from "../../utils/formatters";

interface CategoryPieChartProps {
  data: CategoryPerformanceItem[];
}

const PALETTE = ["#7c3f15", "#c86d51", "#d97706", "#a08264", "#e2a97e", "#5a3219"];

export const CategoryPieChart: React.FC<CategoryPieChartProps> = ({ data }) => {
  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const row = payload[0].payload;
      return (
        <div className="bg-[#1e1b18] text-white p-3 rounded-lg text-xs shadow-lg border border-stone-800">
          <p className="font-semibold text-stone-200 mb-1">{row.menu_category}</p>
          <p className="text-amber-400 font-bold">{formatRupiah(row.net_sales)}</p>
          <p className="text-stone-300 mt-0.5">Kontribusi: <span className="font-medium text-white">{formatPercent(row.sales_contribution_pct)}</span></p>
          <p className="text-stone-300">Total Qty: <span className="font-medium text-white">{row.qty_sold} unit</span></p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="w-full h-72">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            dataKey="net_sales"
            nameKey="menu_category"
            cx="50%"
            cy="50%"
            innerRadius={50}
            outerRadius={80}
            paddingAngle={3}
          >
            {data.map((_, index) => (
              <Cell key={`cell-${index}`} fill={PALETTE[index % PALETTE.length]} />
            ))}
          </Pie>
          <Tooltip content={<CustomTooltip />} />
          <Legend
            verticalAlign="bottom"
            height={36}
            formatter={(value, entry: any) => (
              <span className="text-xs text-[#4a4238] font-medium mr-2">
                {value} ({formatPercent(entry.payload.sales_contribution_pct)})
              </span>
            )}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
};
