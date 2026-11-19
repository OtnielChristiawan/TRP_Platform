import React, { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  UtensilsCrossed,
  Search,
  Sparkles,
  CheckCircle2,
  HelpCircle,
} from "lucide-react";
import { useFilters } from "../components/layout/Layout";
import { api } from "../services/api";
import { TopProductsBarChart } from "../components/charts/TopProductsBarChart";
import { CategoryPieChart } from "../components/charts/CategoryPieChart";
import { ChartSkeleton, TableSkeleton } from "../components/common/LoadingSkeleton";
import { EmptyState, ErrorState } from "../components/common/ErrorState";
import { formatNumber, formatRupiah } from "../utils/formatters";

export const ProductAnalytics: React.FC = () => {
  const { filters, filterOptions, refreshAll } = useFilters();
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string>("");
  const [sortBy, setSortBy] = useState<"quantity" | "sales">("sales");

  const {
    data: menus,
    isLoading: isLoadingMenus,
    isError: isErrorMenus,
    error: menusError,
  } = useQuery({
    queryKey: ["productMenus", filters, sortBy, selectedCategory],
    queryFn: () =>
      api.getTopMenus(filters, 50, sortBy, selectedCategory || undefined),
    enabled: Boolean(filters.startDate && filters.endDate),
  });

  const {
    data: categories,
    isLoading: isLoadingCategories,
  } = useQuery({
    queryKey: ["productCategories", filters],
    queryFn: () => api.getCategoryPerformance(filters),
    enabled: Boolean(filters.startDate && filters.endDate),
  });

  // Client-side search filtering on the returned list
  const filteredMenus = useMemo(() => {
    if (!menus) return [];
    if (!searchTerm.trim()) return menus;
    const term = searchTerm.toLowerCase();
    return menus.filter(
      (m) =>
        m.menu_name.toLowerCase().includes(term) ||
        (m.menu_category && m.menu_category.toLowerCase().includes(term))
    );
  }, [menus, searchTerm]);

  if (isErrorMenus) {
    return (
      <ErrorState
        message={menusError instanceof Error ? menusError.message : undefined}
        onRetry={refreshAll}
      />
    );
  }

  const hasData = menus && menus.length > 0;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="pb-2 border-b border-[#ede8df] flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-[#1e1b18]">
            Product & Menu Analytics
          </h2>
          <p className="text-xs text-[#7c7267] mt-0.5">
            Analisis performa produk, kontribusi kategori, dan status pencocokan Master Menu Toko Roti Pagi.
          </p>
        </div>

        {/* Sort By Toggle */}
        <div className="inline-flex bg-white p-1 rounded-xl border border-[#ede8df] shadow-xs self-start sm:self-auto">
          <button
            onClick={() => setSortBy("sales")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
              sortBy === "sales"
                ? "bg-[#7c3f15] text-white shadow-2xs"
                : "text-[#6b6256] hover:text-[#1e1b18]"
            }`}
          >
            Rank by Net Sales
          </button>
          <button
            onClick={() => setSortBy("quantity")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
              sortBy === "quantity"
                ? "bg-[#7c3f15] text-white shadow-2xs"
                : "text-[#6b6256] hover:text-[#1e1b18]"
            }`}
          >
            Rank by Quantity
          </button>
        </div>
      </div>

      {/* Visualizations Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border border-[#ede8df] p-5 shadow-xs">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-sm font-bold text-[#1e1b18]">
                Top 5 Produk Terunggul
              </h3>
              <p className="text-xs text-[#7c7267]">
                {sortBy === "sales" ? "Berdasarkan total omzet bersih" : "Berdasarkan volume unit terjual"}
              </p>
            </div>
            <div className="p-1.5 bg-[#f5efe6] text-[#7c3f15] rounded-lg">
              <UtensilsCrossed className="w-4 h-4" />
            </div>
          </div>
          {isLoadingMenus ? (
            <ChartSkeleton />
          ) : menus && menus.length > 0 ? (
            <TopProductsBarChart data={menus} metric={sortBy} />
          ) : (
            <div className="h-72 flex items-center justify-center text-xs text-[#8c8275]">
              Data tidak tersedia
            </div>
          )}
        </div>

        <div className="bg-white rounded-xl border border-[#ede8df] p-5 shadow-xs">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-sm font-bold text-[#1e1b18]">
                Pangsa Omzet per Kategori
              </h3>
              <p className="text-xs text-[#7c7267]">
                Kontribusi kategori terhadap total penjualan
              </p>
            </div>
            <div className="p-1.5 bg-[#f5efe6] text-[#7c3f15] rounded-lg">
              <Sparkles className="w-4 h-4" />
            </div>
          </div>
          {isLoadingCategories ? (
            <ChartSkeleton />
          ) : categories && categories.length > 0 ? (
            <CategoryPieChart data={categories} />
          ) : (
            <div className="h-72 flex items-center justify-center text-xs text-[#8c8275]">
              Data tidak tersedia
            </div>
          )}
        </div>
      </div>

      {/* Product Ranking Table Section */}
      <div className="bg-white rounded-xl border border-[#ede8df] overflow-hidden shadow-xs">
        <div className="p-5 border-b border-[#ede8df] flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-bold text-[#1e1b18]">
              Daftar Performa Seluruh Menu ({filteredMenus.length} Produk)
            </h3>
            <p className="text-xs text-[#7c7267] mt-0.5">
              Data terintegrasi Gold Layer dan rekonsiliasi Master Menu TRP
            </p>
          </div>

          {/* Table Filters: Search & Category */}
          <div className="flex flex-wrap items-center gap-2.5">
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-[#8c8275]" />
              <input
                type="text"
                placeholder="Cari menu..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-8 pr-3 py-1.5 bg-[#faf7f2] border border-[#ede8df] rounded-lg text-xs text-[#1e1b18] placeholder-[#a09789] focus:outline-hidden focus:border-[#7c3f15] w-48"
              />
            </div>

            <select
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
              className="py-1.5 px-3 bg-[#faf7f2] border border-[#ede8df] rounded-lg text-xs text-[#1e1b18] focus:outline-hidden focus:border-[#7c3f15] cursor-pointer"
            >
              <option value="">Semua Kategori</option>
              {filterOptions?.categories?.map((cat) => (
                <option key={cat} value={cat}>
                  {cat}
                </option>
              ))}
            </select>
          </div>
        </div>

        {isLoadingMenus ? (
          <div className="p-5">
            <TableSkeleton rows={8} />
          </div>
        ) : !hasData ? (
          <EmptyState />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-[#faf7f2] text-[#7c7267] font-semibold border-b border-[#ede8df]">
                <tr>
                  <th className="py-3 px-4 w-12 text-center">#</th>
                  <th className="py-3 px-4">Nama Menu</th>
                  <th className="py-3 px-4">Kategori</th>
                  <th className="py-3 px-4 text-right">Unit Terjual</th>
                  <th className="py-3 px-4 text-right">Kemunculan Bills</th>
                  <th className="py-3 px-4 text-right font-bold text-[#1e1b18]">Net Sales</th>
                  <th className="py-3 px-4 text-center">Promo/Gratis</th>
                  <th className="py-3 px-4 text-center">Status Master Menu</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#f4f0e9]">
                {filteredMenus.map((row) => (
                  <tr key={row.menu_key} className="hover:bg-[#fcfaf7] transition-colors">
                    <td className="py-3 px-4 text-center font-bold text-[#8c8275]">
                      {row.rank}
                    </td>
                    <td className="py-3 px-4">
                      <div className="font-semibold text-[#1e1b18]">{row.menu_name}</div>
                      <div className="text-[10px] text-[#8c8275] font-mono">{row.menu_key}</div>
                    </td>
                    <td className="py-3 px-4">
                      <span className="inline-flex px-2 py-0.5 rounded-md text-[10px] font-semibold bg-[#f5efe6] text-[#7c3f15]">
                        {row.menu_category || "OTHERS"}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right font-medium">
                      {formatNumber(row.qty_sold)}
                    </td>
                    <td className="py-3 px-4 text-right text-[#7c7267]">
                      {formatNumber(row.total_bills)}
                    </td>
                    <td className="py-3 px-4 text-right font-bold text-[#7c3f15]">
                      {formatRupiah(row.net_sales)}
                    </td>
                    <td className="py-3 px-4 text-center">
                      {row.zero_price_qty > 0 ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-100 text-amber-800">
                          {row.zero_price_qty} free
                        </span>
                      ) : (
                        <span className="text-[#a09789]">-</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-center">
                      {row.is_master_matched ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-100 text-emerald-800">
                          <CheckCircle2 className="w-3 h-3" /> MATCHED
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-stone-100 text-stone-600">
                          <HelpCircle className="w-3 h-3" /> UNMATCHED
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
