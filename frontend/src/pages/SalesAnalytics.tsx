import React from "react";
import { useQuery } from "@tanstack/react-query";
import { Banknote, TrendingUp, Clock, CalendarDays } from "lucide-react";
import { useFilters } from "../components/layout/Layout";
import { api } from "../services/api";
import { KPICard } from "../components/common/KPICard";
import { SalesTrendChart } from "../components/charts/SalesTrendChart";
import { HourlySalesChart } from "../components/charts/HourlySalesChart";
import { ChartSkeleton, KPISkeleton, TableSkeleton } from "../components/common/LoadingSkeleton";
import { EmptyState, ErrorState } from "../components/common/ErrorState";
import { formatDateIndo, formatNumber, formatRupiah } from "../utils/formatters";

export const SalesAnalytics: React.FC = () => {
  const { filters, refreshAll } = useFilters();

  const {
    data: summary,
    isLoading: isLoadingSummary,
    isError: isErrorSummary,
    error: summaryError,
  } = useQuery({
    queryKey: ["salesSummary", filters],
    queryFn: () => api.getSummary(filters),
    enabled: Boolean(filters.startDate && filters.endDate),
  });

  const {
    data: dailySales,
    isLoading: isLoadingDaily,
  } = useQuery({
    queryKey: ["salesDaily", filters],
    queryFn: () => api.getDailySales(filters),
    enabled: Boolean(filters.startDate && filters.endDate),
  });

  const {
    data: hourlySales,
    isLoading: isLoadingHourly,
  } = useQuery({
    queryKey: ["salesHourly", filters],
    queryFn: () => api.getHourlySales(filters),
    enabled: Boolean(filters.startDate && filters.endDate),
  });

  if (isErrorSummary) {
    return (
      <ErrorState
        message={summaryError instanceof Error ? summaryError.message : undefined}
        onRetry={refreshAll}
      />
    );
  }

  const hasData = summary && summary.total_bills > 0;

  // Find peak hour
  const peakHour = hourlySales && hourlySales.length > 0
    ? [...hourlySales].sort((a, b) => b.net_sales - a.net_sales)[0]
    : null;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="pb-2 border-b border-[#ede8df]">
        <h2 className="text-xl font-bold tracking-tight text-[#1e1b18]">
          Sales Analytics
        </h2>
        <p className="text-xs text-[#7c7267] mt-0.5">
          Analisis mendalam performa finansial harian, pola jam sibuk operasional, dan nilai rata-rata belanja.
        </p>
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
              title="Gross Sales"
              value={formatRupiah(summary?.total_gross_sales)}
              subtitle="Nilai penjualan kotor"
              icon={<Banknote className="w-5 h-5" />}
            />
            <KPICard
              title="Net Sales"
              value={formatRupiah(summary?.total_net_sales)}
              subtitle={`Total Diskon: ${formatRupiah(summary?.total_discount)}`}
              icon={<TrendingUp className="w-5 h-5 text-emerald-700" />}
              growthPct={summary?.sales_growth_pct}
            />
            <KPICard
              title="Average Order Value"
              value={formatRupiah(summary?.average_order_value)}
              subtitle="Rata-rata nominal per transaksi"
              icon={<CalendarDays className="w-5 h-5" />}
            />
            <KPICard
              title="Jam Paling Ramai"
              value={peakHour ? `Pukul ${String(peakHour.sales_hour).padStart(2, "0")}:00` : "-"}
              subtitle={peakHour ? `${formatRupiah(peakHour.net_sales)} (${peakHour.total_bills} bills)` : "Belum terdeteksi"}
              icon={<Clock className="w-5 h-5" />}
            />
          </>
        )}
      </div>

      {!isLoadingSummary && !hasData ? (
        <EmptyState />
      ) : (
        <>
          {/* Charts Row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-white rounded-xl border border-[#ede8df] p-5 shadow-xs">
              <h3 className="text-sm font-bold text-[#1e1b18] mb-1">
                Grafik Penjualan Bersih Harian
              </h3>
              <p className="text-xs text-[#7c7267] mb-4">
                Fluktuasi omzet bersih (Net Sales) harian
              </p>
              {isLoadingDaily ? (
                <ChartSkeleton />
              ) : dailySales && dailySales.length > 0 ? (
                <SalesTrendChart data={dailySales} />
              ) : null}
            </div>

            <div className="bg-white rounded-xl border border-[#ede8df] p-5 shadow-xs">
              <h3 className="text-sm font-bold text-[#1e1b18] mb-1">
                Pola Penjualan per Jam Operasional
              </h3>
              <p className="text-xs text-[#7c7267] mb-4">
                Waktu selesai transaksi kasir (Asia/Jakarta)
              </p>
              {isLoadingHourly ? (
                <ChartSkeleton />
              ) : hourlySales && hourlySales.length > 0 ? (
                <HourlySalesChart data={hourlySales} />
              ) : null}
            </div>
          </div>

          {/* Daily Summary Data Table */}
          <div className="bg-white rounded-xl border border-[#ede8df] overflow-hidden shadow-xs">
            <div className="p-5 border-b border-[#ede8df]">
              <h3 className="text-sm font-bold text-[#1e1b18]">
                Tabel Ringkasan Penjualan Harian
              </h3>
              <p className="text-xs text-[#7c7267] mt-0.5">
                Rincian transaksi per hari dan cabang Toko Roti Pagi
              </p>
            </div>

            {isLoadingDaily ? (
              <div className="p-5">
                <TableSkeleton rows={4} />
              </div>
            ) : dailySales && dailySales.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-[#faf7f2] text-[#7c7267] font-semibold border-b border-[#ede8df]">
                    <tr>
                      <th className="py-3 px-4">Tanggal</th>
                      <th className="py-3 px-4">Cabang</th>
                      <th className="py-3 px-4 text-right">Bills</th>
                      <th className="py-3 px-4 text-right">Item Rows</th>
                      <th className="py-3 px-4 text-right">Qty Terjual</th>
                      <th className="py-3 px-4 text-right">Gross Sales</th>
                      <th className="py-3 px-4 text-right">Diskon</th>
                      <th className="py-3 px-4 text-right font-bold text-[#1e1b18]">Net Sales</th>
                      <th className="py-3 px-4 text-right">AOV</th>
                      <th className="py-3 px-4 text-center">Item Promo</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#f4f0e9]">
                    {dailySales.map((row, idx) => (
                      <tr key={idx} className="hover:bg-[#fcfaf7] transition-colors">
                        <td className="py-3 px-4 font-medium text-[#1e1b18]">
                          {formatDateIndo(row.sales_date)}
                        </td>
                        <td className="py-3 px-4 text-[#4a4238]">{row.branch}</td>
                        <td className="py-3 px-4 text-right font-medium">{formatNumber(row.total_bills)}</td>
                        <td className="py-3 px-4 text-right text-[#7c7267]">{formatNumber(row.total_item_rows)}</td>
                        <td className="py-3 px-4 text-right font-medium">{formatNumber(row.total_qty_sold)}</td>
                        <td className="py-3 px-4 text-right text-[#7c7267]">{formatRupiah(row.gross_sales)}</td>
                        <td className="py-3 px-4 text-right text-rose-600">
                          {row.total_discount > 0 ? `-${formatRupiah(row.total_discount)}` : "Rp 0"}
                        </td>
                        <td className="py-3 px-4 text-right font-bold text-[#7c3f15]">
                          {formatRupiah(row.net_sales)}
                        </td>
                        <td className="py-3 px-4 text-right text-[#4a4238]">{formatRupiah(row.average_order_value)}</td>
                        <td className="py-3 px-4 text-center">
                          {row.zero_price_item_count > 0 ? (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-100 text-amber-800">
                              {row.zero_price_item_count} gratis
                            </span>
                          ) : (
                            <span className="text-[#a09789]">-</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="p-8 text-center text-xs text-[#7c7267]">
                Tidak ada data harian.
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
};
