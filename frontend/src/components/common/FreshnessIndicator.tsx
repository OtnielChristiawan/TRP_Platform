import React from "react";
import { RefreshCw } from "lucide-react";
import type { FreshnessResponse } from "../../types/api";
import { formatDateTimeIndo } from "../../utils/formatters";

interface FreshnessIndicatorProps {
  freshness?: FreshnessResponse;
  isLoading?: boolean;
  onRefresh?: () => void;
}

export const FreshnessIndicator: React.FC<FreshnessIndicatorProps> = ({
  freshness,
  isLoading,
  onRefresh,
}) => {
  const isHealthy = freshness?.status === "HEALTHY";

  return (
    <div className="flex items-center gap-3 bg-white border border-[#ede8df] rounded-xl px-4 py-2 text-xs shadow-xs">
      <div className="flex items-center gap-1.5">
        <span className="relative flex h-2 w-2">
          {isHealthy && (
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
          )}
          <span
            className={`relative inline-flex rounded-full h-2 w-2 ${
              isHealthy ? "bg-emerald-500" : "bg-amber-500"
            }`}
          ></span>
        </span>
        <span className="font-semibold text-[#4a4238]">
          {isHealthy ? "Gold Synced" : "Pending Sync"}
        </span>
      </div>

      <div className="h-3 w-px bg-[#ede8df]" />

      <div className="text-[#7c7267] hidden sm:block">
        Updated: <span className="font-medium text-[#1e1b18]">{formatDateTimeIndo(freshness?.last_refresh_at)}</span>
      </div>

      {freshness?.batch_id && (
        <>
          <div className="h-3 w-px bg-[#ede8df] hidden md:block" />
          <div className="text-[#8c8275] hidden md:block font-mono text-[11px]">
            Batch: {freshness.batch_id.slice(0, 15)}
          </div>
        </>
      )}

      {onRefresh && (
        <button
          onClick={onRefresh}
          disabled={isLoading}
          className="ml-auto p-1 text-[#7c3f15] hover:text-[#5a2c0c] hover:bg-[#f5efe6] rounded-md transition-colors"
          title="Refresh Data Sekarang"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
        </button>
      )}
    </div>
  );
};
