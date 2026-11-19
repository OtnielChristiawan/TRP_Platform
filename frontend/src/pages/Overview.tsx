import React from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Banknote,
  Receipt,
  ShoppingBag,
  TrendingUp,
  Tag,
  ArrowRight,
} from "lucide-react";
import { Link } from "react-router-dom";
import { useFilters } from "../components/layout/Layout";
import { api } from "../services/api";
import { KPICard } from "../components/common/KPICard";
import { SalesTrendChart } from "../components/charts/SalesTrendChart";
import { HourlySalesChart } from "../components/charts/HourlySalesChart";
import { CategoryPieChart } from "../components/charts/CategoryPieChart";
import { TopProductsBarChart } from "../components/charts/TopProductsBarChart";
import { ChartSkeleton, KPISkeleton } from "../components/common/LoadingSkeleton";
import { EmptyState, ErrorState } from "../components/common/ErrorState";
import { formatNumber, formatRupiah } from "../utils/formatters";

export const Overview: React.FC = () => {
  const { filters, refreshAll } = useFilters();

  const {
    data: summary,
    isLoading: isLoadingSummary,
    isError: isErrorSummary,
    error: summaryError,
  } = useQuery({
    queryKey: ["summary", filters],
    queryFn: () => api.getSummary(filters),
    enabled: Boolean(filters.startDate && filters.endDate),
  });

  const {
    data: dailySales,
    isLoading: isLoadingDaily,
    isError: isErrorDaily,
  } = useQuery({
    queryKey: ["dailySales", filters],
    queryFn: () => api.getDailySales(filters),
    enabled: Boolean(filters.startDate && filters.endDate),
  });

  const {
    data: hourlySales,
    isLoading: isLoadingHourly,
  } = useQuery({
    queryKey: ["hourlySales", filters],
    queryFn: () => api.getHourlySales(filters),
    enabled: Boolean(filters.startDate && filters.endDate),
  });

  const {
    data: topMenus,
    isLoading: isLoadingMenus,
  } = useQuery({
    queryKey: ["topMenus", filters],
    queryFn: () => api.getTopMenus(filters, 5, "sales"),
    enabled: Boolean(filters.startDate && filters.endDate),
  });

  const {
    data: categories,
    isLoading: isLoadingCategories,
  } = useQuery({
    queryKey: ["categories", filters],
    queryFn: () => api.getCategoryPerformance(filters),
    enabled: Boolean(filters.startDate && filters.endDate),
  });

  if (isErrorSummary || isErrorDaily) {
    return (
      <ErrorState
        message={summaryError instanceof Error ? summaryError.message : undefined}
        onRetry={refreshAll}
      />
    );
  }

  const hasData = summary && summary.total_bills > 0;

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2 border-b border-[#ede8df]">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-[#1e1b18]">
            Overview Penjualan
          </h2>
          <p className="text-xs text-[#7c7267] mt-0.5">
            Ringkasan performa pendapatan, volume transaksi, dan menu terlaris Toko Roti Pagi.
          </p>
        </div>
      </div>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {isLoadingSummary ? (
          <>
            <KPISkeleton />
            <KPISkeleton />
            <KPISkeleton />
            <KPISkeleton />
          </>
        ) : (
          <>
            <KPICard
              title="Total Net Sales"
              value={formatRupiah(summary?.total_net_sales)}
              subtitle={`Gross: ${formatRupiah(summary?.total_gross_sales)}`}
              icon={<Banknote className="w-5 h-5" />}
              growthPct={summary?.sales_growth_pct}
            />
            <KPICard
              title="Total Transaksi"
              value={`${formatNumber(summary?.total_bills)} bills`}
              subtitle={`${formatNumber(summary?.total_item_rows)} baris item`}
              icon={<Receipt className="w-5 h-5" />}
              growthPct={summary?.bills_growth_pct}
            />
            <KPICard
              title="Produk Terjual"
              value={`${formatNumber(summary?.total_qty_sold)} unit`}
              subtitle={`Promo/Gratis: ${summary?.zero_price_item_count || 0} item`}
              icon={<ShoppingBag className="w-5 h-5" />}
            />
            <KPICard
              title="Average Order Value"
              value={formatRupiah(summary?.average_order_value)}
              subtitle="Rata-rata belanja per bill"
              icon={<TrendingUp className="w-5 h-5" />}
            />
          </>
        )}
      </div>

      {!isLoadingSummary && !hasData ? (
        <EmptyState />
      ) : (
        <>
          {/* Main Visualizations Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Sales Trend */}
            <div className="bg-white rounded-xl border border-[#ede8df] p-5 shadow-xs">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-bold text-[#1e1b18]">
                    Tren Penjualan Harian
                  </h3>
                  <p className="text-xs text-[#7c7267]">
                    Perkembangan omzet bersih harian
                  </p>
                </div>
                <Link
                  to="/sales"
                  className="text-xs font-semibold text-[#7c3f15] hover:text-[#5a2c0c] flex items-center gap-1 hover:underline"
                >
                  Detail <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              </div>
              {isLoadingDaily ? (
                <ChartSkeleton />
              ) : dailySales && dailySales.length > 0 ? (
                <SalesTrendChart data={dailySales} />
              ) : (
                <div className="h-72 flex items-center justify-center text-xs text-[#8c8275]">
                  Data tidak tersedia
                </div>
              )}
            </div>

            {/* Hourly Sales Pattern */}
            <div className="bg-white rounded-xl border border-[#ede8df] p-5 shadow-xs">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-bold text-[#1e1b18]">
                    Distribusi Jam Penjualan
                  </h3>
                  <p className="text-xs text-[#7c7267]">
                    Berdasarkan jam transaksi selesai (WIB)
                  </p>
                </div>
                <Link
                  to="/sales"
                  className="text-xs font-semibold text-[#7c3f15] hover:text-[#5a2c0c] flex items-center gap-1 hover:underline"
                >
                  Detail <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              </div>
              {isLoadingHourly ? (
                <ChartSkeleton />
              ) : hourlySales && hourlySales.length > 0 ? (
                <HourlySalesChart data={hourlySales} />
              ) : (
                <div className="h-72 flex items-center justify-center text-xs text-[#8c8275]">
                  Data tidak tersedia
                </div>
              )}
            </div>
          </div>

          {/* Secondary Visualizations Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Top 5 Products */}
            <div className="bg-white rounded-xl border border-[#ede8df] p-5 shadow-xs">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-bold text-[#1e1b18]">
                    Top 5 Menu Berdasarkan Revenue
                  </h3>
                  <p className="text-xs text-[#7c7267]">
                    Produk dengan kontribusi omzet tertinggi
                  </p>
                </div>
                <Link
                  to="/products"
                  className="text-xs font-semibold text-[#7c3f15] hover:text-[#5a2c0c] flex items-center gap-1 hover:underline"
                >
                  Lihat Semua <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              </div>
              {isLoadingMenus ? (
                <ChartSkeleton />
              ) : topMenus && topMenus.length > 0 ? (
                <TopProductsBarChart data={topMenus} metric="sales" />
              ) : (
                <div className="h-72 flex items-center justify-center text-xs text-[#8c8275]">
                  Data tidak tersedia
                </div>
              )}
            </div>

            {/* Category Performance */}
            <div className="bg-white rounded-xl border border-[#ede8df] p-5 shadow-xs">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-bold text-[#1e1b18]">
                    Pangsa Penjualan per Kategori
                  </h3>
                  <p className="text-xs text-[#7c7267]">
                    Proporsi kontribusi kategori menu
                  </p>
                </div>
                <div className="p-1 text-[#7c3f15]">
                  <Tag className="w-4 h-4" />
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
        </>
      )}
    </div>
  );
};
