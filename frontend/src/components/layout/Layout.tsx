import React, { createContext, useContext, useEffect, useState } from "react";
import { Outlet, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Navbar } from "./Navbar";
import { Sidebar } from "./Sidebar";
import { FilterBar } from "../common/FilterBar";
import { api } from "../../services/api";
import type { FilterOptionsResponse, FreshnessResponse, GlobalFilterState } from "../../types/api";

interface FilterContextType {
  filters: GlobalFilterState;
  filterOptions?: FilterOptionsResponse;
  setFilters: (f: GlobalFilterState) => void;
  resetFilters: () => void;
  freshness?: FreshnessResponse;
  refreshAll: () => void;
}

const FilterContext = createContext<FilterContextType | null>(null);

export const useFilters = () => {
  const ctx = useContext(FilterContext);
  if (!ctx) throw new Error("useFilters must be used within FilterProvider");
  return ctx;
};

export const Layout: React.FC = () => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();

  // Fetch filter options (min/max date, branches) from Gold
  const { data: filterOptions } = useQuery({
    queryKey: ["filterOptions"],
    queryFn: api.getFilters,
    staleTime: 5 * 60 * 1000,
  });

  // Fetch data freshness metadata (refreshed every 60s)
  const { data: freshness, isFetching: isRefreshingFreshness, refetch: refetchFreshness } = useQuery({
    queryKey: ["freshness"],
    queryFn: api.getFreshness,
    refetchInterval: 60 * 1000,
  });

  // Global Filter State with URL Sync
  const [filters, setFiltersState] = useState<GlobalFilterState>({
    startDate: searchParams.get("start_date") || "",
    endDate: searchParams.get("end_date") || "",
    branch: searchParams.get("branch") || "",
  });

  // When filter options are loaded, initialize default start/end dates from Gold if not set
  useEffect(() => {
    if (filterOptions) {
      const defaultStart = searchParams.get("start_date") || filterOptions.min_date || "";
      const defaultEnd = searchParams.get("end_date") || filterOptions.max_date || "";
      const defaultBranch = searchParams.get("branch") || "";

      setFiltersState((prev) => ({
        startDate: prev.startDate || defaultStart,
        endDate: prev.endDate || defaultEnd,
        branch: prev.branch || defaultBranch,
      }));
    }
  }, [filterOptions]);

  const updateFilters = (newFilters: GlobalFilterState) => {
    setFiltersState(newFilters);
    const params = new URLSearchParams();
    if (newFilters.startDate) params.set("start_date", newFilters.startDate);
    if (newFilters.endDate) params.set("end_date", newFilters.endDate);
    if (newFilters.branch) params.set("branch", newFilters.branch);
    setSearchParams(params, { replace: true });
  };

  const resetFilters = () => {
    if (filterOptions) {
      updateFilters({
        startDate: filterOptions.min_date || "",
        endDate: filterOptions.max_date || "",
        branch: "",
      });
    }
  };

  const refreshAll = () => {
    queryClient.invalidateQueries();
    refetchFreshness();
  };

  return (
    <FilterContext.Provider
      value={{
        filters,
        filterOptions,
        setFilters: updateFilters,
        resetFilters,
        freshness,
        refreshAll,
      }}
    >
      <div className="min-h-screen bg-[#faf7f2] flex flex-col">
        <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

        <div className="lg:pl-64 flex flex-col flex-1">
          <Navbar
            onToggleSidebar={() => setSidebarOpen((prev) => !prev)}
            freshness={freshness}
            isLoadingFreshness={isRefreshingFreshness}
            onRefresh={refreshAll}
          />

          <main className="flex-1 p-4 sm:p-6 lg:p-8 max-w-7xl w-full mx-auto space-y-6">
            <FilterBar
              filters={filters}
              options={filterOptions}
              onChange={updateFilters}
              onReset={resetFilters}
            />

            <Outlet />
          </main>
        </div>
      </div>
    </FilterContext.Provider>
  );
};
