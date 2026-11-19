import React from "react";

export const KPISkeleton: React.FC = () => (
  <div className="bg-white rounded-xl border border-[#ede8df] p-5 animate-pulse">
    <div className="flex justify-between items-center">
      <div className="h-3 w-24 bg-[#ede8df] rounded" />
      <div className="h-8 w-8 bg-[#f5efe6] rounded-lg" />
    </div>
    <div className="h-7 w-32 bg-[#ede8df] rounded mt-4" />
    <div className="h-3 w-20 bg-[#ede8df] rounded mt-2" />
  </div>
);

export const ChartSkeleton: React.FC<{ height?: string }> = ({ height = "h-80" }) => (
  <div className={`bg-white rounded-xl border border-[#ede8df] p-5 animate-pulse ${height}`}>
    <div className="h-4 w-40 bg-[#ede8df] rounded mb-6" />
    <div className="h-48 w-full bg-[#f9f7f4] rounded flex items-center justify-center">
      <div className="text-xs text-[#a09789]">Memuat data visualisasi...</div>
    </div>
  </div>
);

export const TableSkeleton: React.FC<{ rows?: number }> = ({ rows = 5 }) => (
  <div className="bg-white rounded-xl border border-[#ede8df] p-5 animate-pulse">
    <div className="h-4 w-48 bg-[#ede8df] rounded mb-4" />
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-10 bg-[#f9f7f4] rounded w-full" />
      ))}
    </div>
  </div>
);
