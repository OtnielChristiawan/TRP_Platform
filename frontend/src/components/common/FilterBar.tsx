import React from "react";
import { Calendar, Store, RotateCcw } from "lucide-react";
import type { FilterOptionsResponse, GlobalFilterState } from "../../types/api";

interface FilterBarProps {
  filters: GlobalFilterState;
  options?: FilterOptionsResponse;
  onChange: (newFilters: GlobalFilterState) => void;
  onReset: () => void;
}

export const FilterBar: React.FC<FilterBarProps> = ({
  filters,
  options,
  onChange,
  onReset,
}) => {
  const handleStartDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onChange({ ...filters, startDate: e.target.value });
  };

  const handleEndDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onChange({ ...filters, endDate: e.target.value });
  };

  const handleBranchChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    onChange({ ...filters, branch: e.target.value });
  };

  return (
    <div className="bg-white border border-[#ede8df] rounded-xl p-3.5 shadow-xs flex flex-wrap items-center gap-3">
      {/* Date Range Start */}
      <div className="flex items-center gap-2 bg-[#fcfaf7] border border-[#e5dec9] rounded-lg px-3 py-1.5 text-xs text-[#4a4238]">
        <Calendar className="w-3.5 h-3.5 text-[#7c3f15]" />
        <span className="font-semibold text-[#8c8275]">Dari:</span>
        <input
          type="date"
          value={filters.startDate}
          min={options?.min_date || undefined}
          max={options?.max_date || undefined}
          onChange={handleStartDateChange}
          className="bg-transparent border-0 focus:outline-hidden text-[#1e1b18] font-medium text-xs cursor-pointer"
        />
      </div>

      {/* Date Range End */}
      <div className="flex items-center gap-2 bg-[#fcfaf7] border border-[#e5dec9] rounded-lg px-3 py-1.5 text-xs text-[#4a4238]">
        <Calendar className="w-3.5 h-3.5 text-[#7c3f15]" />
        <span className="font-semibold text-[#8c8275]">Sampai:</span>
        <input
          type="date"
          value={filters.endDate}
          min={options?.min_date || undefined}
          max={options?.max_date || undefined}
          onChange={handleEndDateChange}
          className="bg-transparent border-0 focus:outline-hidden text-[#1e1b18] font-medium text-xs cursor-pointer"
        />
      </div>

      {/* Branch Selector */}
      <div className="flex items-center gap-2 bg-[#fcfaf7] border border-[#e5dec9] rounded-lg px-3 py-1.5 text-xs text-[#4a4238]">
        <Store className="w-3.5 h-3.5 text-[#7c3f15]" />
        <span className="font-semibold text-[#8c8275]">Cabang:</span>
        <select
          value={filters.branch}
          onChange={handleBranchChange}
          className="bg-transparent border-0 focus:outline-hidden text-[#1e1b18] font-medium text-xs cursor-pointer pr-2"
        >
          <option value="">Semua Cabang</option>
          {options?.branches?.map((b) => (
            <option key={b} value={b}>
              {b}
            </option>
          ))}
        </select>
      </div>

      {/* Reset Filter Button */}
      <button
        onClick={onReset}
        className="ml-auto inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-[#7c3f15] hover:bg-[#f5efe6] border border-transparent hover:border-[#e5dec9] transition-all cursor-pointer"
      >
        <RotateCcw className="w-3.5 h-3.5" />
        <span>Reset Filter</span>
      </button>
    </div>
  );
};
