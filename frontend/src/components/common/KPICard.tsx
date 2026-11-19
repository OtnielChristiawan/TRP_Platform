import React from "react";
import { ArrowUpRight, ArrowDownRight, Minus } from "lucide-react";

interface KPICardProps {
  title: string;
  value: string;
  subtitle?: string;
  icon: React.ReactNode;
  growthPct?: number | null;
  growthLabel?: string;
}

export const KPICard: React.FC<KPICardProps> = ({
  title,
  value,
  subtitle,
  icon,
  growthPct,
  growthLabel = "vs periode lalu",
}) => {
  const isPositive = growthPct !== null && growthPct !== undefined && growthPct > 0;
  const isNegative = growthPct !== null && growthPct !== undefined && growthPct < 0;
  const isNeutral = growthPct === 0;

  return (
    <div className="bg-white rounded-xl border border-[#ede8df] p-5 shadow-xs hover:shadow-md transition-shadow">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider text-[#7c7267]">
          {title}
        </span>
        <div className="p-2.5 rounded-lg bg-[#f5efe6] text-[#7c3f15]">
          {icon}
        </div>
      </div>

      <div className="mt-3">
        <h3 className="text-2xl font-bold tracking-tight text-[#1e1b18]">
          {value}
        </h3>
        {subtitle && (
          <p className="text-xs text-[#7c7267] mt-1">{subtitle}</p>
        )}
      </div>

      {growthPct !== null && growthPct !== undefined && (
        <div className="mt-4 pt-3 border-t border-[#f4f0e9] flex items-center text-xs">
          <span
            className={`inline-flex items-center font-semibold px-2 py-0.5 rounded-md ${
              isPositive
                ? "bg-emerald-50 text-emerald-700"
                : isNegative
                ? "bg-rose-50 text-rose-700"
                : "bg-stone-100 text-stone-600"
            }`}
          >
            {isPositive && <ArrowUpRight className="w-3.5 h-3.5 mr-0.5" />}
            {isNegative && <ArrowDownRight className="w-3.5 h-3.5 mr-0.5" />}
            {isNeutral && <Minus className="w-3.5 h-3.5 mr-0.5" />}
            {Math.abs(growthPct).toFixed(1)}%
          </span>
          <span className="text-[#8c8275] ml-2">{growthLabel}</span>
        </div>
      )}
    </div>
  );
};
