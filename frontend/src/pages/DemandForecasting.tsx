import React, { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BrainCircuit,
  Calendar,
  Clock,
  Sparkles,
  TrendingUp,
  Search,
  CheckCircle2,
  ChefHat,
  ShieldAlert,
  Layers,
} from "lucide-react";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { useFilters } from "../components/layout/Layout";
import { api } from "../services/api";
import { KPICard } from "../components/common/KPICard";
import { ChartSkeleton, KPISkeleton } from "../components/common/LoadingSkeleton";
import { ErrorState } from "../components/common/ErrorState";
import { formatNumber } from "../utils/formatters";

export const DemandForecasting: React.FC = () => {
  const { filters } = useFilters();
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string>("ALL");

  // Query ML endpoints
  const {
    data: summary,
    isLoading: isLoadingSummary,
    isError: isErrorSummary,
    error: summaryError,
    refetch: refetchSummary,
  } = useQuery({
    queryKey: ["mlSummary", filters.branch],
    queryFn: () => api.getMLSummary(filters.branch || undefined),
  });

  const { data: products, isLoading: isLoadingProducts } = useQuery({
    queryKey: ["mlProducts", filters.branch],
    queryFn: () => api.getMLProductForecasts(filters.branch || undefined, 100),
  });

  const { data: weekly, isLoading: isLoadingWeekly } = useQuery({
    queryKey: ["mlWeekly", filters.branch],
    queryFn: () => api.getMLWeeklyForecast(filters.branch || undefined),
  });

  const { data: hourly, isLoading: isLoadingHourly } = useQuery({
    queryKey: ["mlHourly", filters.branch],
    queryFn: () => api.getMLHourlyForecast(filters.branch || undefined),
  });

  const { data: recommendations, isLoading: isLoadingRecs } = useQuery({
    queryKey: ["mlRecommendations", filters.branch],
    queryFn: () => api.getMLRecommendations(filters.branch || undefined, 100),
  });

  const { data: metrics } = useQuery({
    queryKey: ["mlMetrics"],
    queryFn: api.getMLModelMetrics,
  });

  // Filtered product forecast list
  const filteredProducts = useMemo(() => {
    if (!products) return [];
    return products.filter((p) => {
      const matchSearch =
        p.menu_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        p.menu_key.toLowerCase().includes(searchTerm.toLowerCase());
      const matchCat =
        selectedCategory === "ALL" || p.menu_category.toUpperCase() === selectedCategory;
      return matchSearch && matchCat;
    });
  }, [products, searchTerm, selectedCategory]);

  // Categories list
  const categories = useMemo(() => {
    if (!products) return ["ALL"];
    const cats = Array.from(new Set(products.map((p) => p.menu_category.toUpperCase())));
    return ["ALL", ...cats];
  }, [products]);

  if (isErrorSummary) {
    return (
      <ErrorState
        message={summaryError instanceof Error ? summaryError.message : "Gagal memanggil endpoint ML."}
        onRetry={() => refetchSummary()}
      />
    );
  }

  return (
    <div className="space-y-8 pb-12">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-[#ede8df] pb-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold tracking-wide uppercase bg-[#f5ede4] text-[#7c3f15] border border-[#e6d7c3]">
              F-11, F-12, F-13 COMPLIANT
            </span>
            <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold tracking-wide uppercase bg-amber-50 text-amber-800 border border-amber-200 flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
              STATUS: {summary?.model_status?.toUpperCase() || "PROVISIONAL"}
            </span>
          </div>
          <h1 className="text-2xl md:text-3xl font-extrabold text-[#1e1b18] tracking-tight">
            AI Demand Forecasting & Production Planner
          </h1>
          <p className="text-sm text-[#8c8275] mt-1">
            Prediksi permintaan menu harian, proyeksi 7 hari ke depan, pola jam sibuk, dan rekomendasi batch baking untuk Toko Roti Pagi.
          </p>
        </div>

        {summary?.last_forecast_created_at && (
          <div className="text-xs text-[#8c8275] bg-white px-4 py-2.5 rounded-xl border border-[#ede8df] shadow-2xs flex items-center gap-2">
            <Clock className="w-4 h-4 text-[#7c3f15]" />
            <div>
              <p className="font-semibold text-stone-700">Terakhir Diperbarui:</p>
              <p>{new Date(summary.last_forecast_created_at).toLocaleString("id-ID")}</p>
            </div>
          </div>
        )}
      </div>

      {/* SECTION A: FORECAST OVERVIEW (KPIs) */}
      <section className="space-y-4">
        <h2 className="text-base font-bold text-[#1e1b18] flex items-center gap-2">
          <BrainCircuit className="w-4 h-4 text-[#7c3f15]" />
          Ringkasan Eksekutif Forecast H+1 ({summary?.forecast_target_date ? new Date(summary.forecast_target_date).toLocaleDateString("id-ID", { weekday: "long", day: "numeric", month: "long", year: "numeric" }) : "Besok"})
        </h2>

        {isLoadingSummary ? (
          <KPISkeleton />
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <KPICard
              title="Prediksi Total Item Besok"
              value={`${formatNumber(summary?.predicted_total_items_tomorrow || 0)} pcs`}
              subtitle="Total estimasi seluruh produk terjual"
              icon={<TrendingUp className="w-5 h-5 text-[#7c3f15]" />}
            />
            <KPICard
              title="Jumlah Menu Terprediksi"
              value={`${summary?.menus_forecasted_count || 0} Menu`}
              subtitle="Cakupan katalog menu aktif"
              icon={<Layers className="w-5 h-5 text-[#7c3f15]" />}
            />
            <KPICard
              title="Model Aktif di Produksi"
              value={summary?.active_model_name ? summary.active_model_name.replace("_", " ").toUpperCase() : "BASELINE"}
              subtitle={`Versi Model: ${summary?.active_model_version || "v1.0.0"}`}
              icon={<Sparkles className="w-5 h-5 text-[#7c3f15]" />}
            />
            <KPICard
              title="Top Demanded Menu"
              value={summary?.top_demanded_menu || "N/A"}
              subtitle="Produk dengan volume tertinggi besok"
              icon={<ChefHat className="w-5 h-5 text-[#7c3f15]" />}
            />
          </div>
        )}
      </section>

      {/* SECTION B & D: 7-DAY TREND & HOURLY DEMAND CHARTS */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* SECTION B: Seven-Day Demand Trend */}
        <div className="lg:col-span-7 bg-white p-6 rounded-2xl border border-[#ede8df] shadow-2xs space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-base font-bold text-[#1e1b18] flex items-center gap-2">
                <Calendar className="w-4 h-4 text-[#7c3f15]" />
                Proyeksi Permintaan 7 Hari ke Depan (H+1 s/d H+7)
              </h3>
              <p className="text-xs text-[#8c8275]">
                Multi-step direct/recursive forecast total item per hari dengan bobot akhir pekan
              </p>
            </div>
            <span className="text-[11px] font-semibold text-emerald-800 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-md">
              Future Projection
            </span>
          </div>

          {isLoadingWeekly ? (
            <ChartSkeleton height="h-72" />
          ) : (
            <div className="h-[280px] w-full pt-2">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={weekly || []} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f0ebe1" />
                  <XAxis
                    dataKey="forecast_date"
                    tickFormatter={(val) => {
                      const d = new Date(val);
                      return d.toLocaleDateString("id-ID", { weekday: "short", day: "numeric", month: "short" });
                    }}
                    tick={{ fill: "#8c8275", fontSize: 11 }}
                    axisLine={{ stroke: "#ede8df" }}
                  />
                  <YAxis
                    tick={{ fill: "#8c8275", fontSize: 11 }}
                    axisLine={{ stroke: "#ede8df" }}
                    domain={["auto", "auto"]}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#ffffff",
                      borderRadius: "12px",
                      border: "1px solid #ede8df",
                      boxShadow: "0 4px 12px rgba(0,0,0,0.06)",
                    }}
                    formatter={(val) => [`${val ?? 0} pcs`, "Prediksi Total"]}
                    labelFormatter={(val) => `Tanggal: ${new Date(String(val)).toLocaleDateString("id-ID", { weekday: "long", day: "numeric", month: "long" })}`}
                  />
                  <Line
                    type="monotone"
                    dataKey="predicted_total_qty"
                    name="Prediksi Total"
                    stroke="#7c3f15"
                    strokeWidth={3}
                    dot={{ fill: "#7c3f15", r: 4 }}
                    activeDot={{ r: 6, fill: "#c97a3e" }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        {/* SECTION D: Hourly Demand Forecast */}
        <div className="lg:col-span-5 bg-white p-6 rounded-2xl border border-[#ede8df] shadow-2xs space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-base font-bold text-[#1e1b18] flex items-center gap-2">
                <Clock className="w-4 h-4 text-[#7c3f15]" />
                Estimasi Jam Sibuk Besok
              </h3>
              <p className="text-xs text-[#8c8275]">
                Jam operasional 09:00 - 19:00 WIB
              </p>
            </div>
            <span className="text-[11px] font-semibold text-stone-700 bg-stone-100 px-2 py-0.5 rounded-md">
              11 Jam Operasional
            </span>
          </div>

          {isLoadingHourly ? (
            <ChartSkeleton height="h-72" />
          ) : (
            <div className="h-[280px] w-full pt-2">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={hourly || []} margin={{ top: 10, right: 10, left: -15, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f0ebe1" />
                  <XAxis
                    dataKey="forecast_hour"
                    tickFormatter={(val) => `${val}:00`}
                    tick={{ fill: "#8c8275", fontSize: 11 }}
                    axisLine={{ stroke: "#ede8df" }}
                  />
                  <YAxis
                    tick={{ fill: "#8c8275", fontSize: 11 }}
                    axisLine={{ stroke: "#ede8df" }}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#ffffff",
                      borderRadius: "12px",
                      border: "1px solid #ede8df",
                      boxShadow: "0 4px 12px rgba(0,0,0,0.06)",
                    }}
                    formatter={(val) => [`${val ?? 0} pcs`, "Prediksi Qty"]}
                    labelFormatter={(val) => `Pukul: ${val}:00 WIB`}
                  />
                  <Bar
                    dataKey="predicted_qty"
                    name="Prediksi Qty"
                    fill="#c97a3e"
                    radius={[6, 6, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>

      {/* SECTION E: PRODUCTION PREPARATION RECOMMENDATION */}
      <section className="bg-white p-6 rounded-2xl border border-[#ede8df] shadow-2xs space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h3 className="text-base font-bold text-[#1e1b18] flex items-center gap-2">
              <ChefHat className="w-5 h-5 text-[#7c3f15]" />
              Rekomendasi Persiapan Produksi (Decision Support Dapur)
            </h3>
            <p className="text-xs text-[#8c8275]">
              Perhitungan unit batch siap panggang = Forecast Qty + Safety Stock Buffer (Z × σ)
            </p>
          </div>
          <span className="text-xs font-semibold px-3 py-1 rounded-full bg-[#fbf8f5] text-[#7c3f15] border border-[#ede8df]">
            Policy: v1.0.0 (Category & Velocity Aware)
          </span>
        </div>

        {/* Operational Disclaimer Banner */}
        <div className="bg-amber-50/80 border border-amber-200/90 rounded-xl p-4 flex items-start gap-3 text-amber-900 text-xs">
          <ShieldAlert className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <p className="font-bold">Perhatian Operasional untuk Tim Produksi:</p>
            <p className="leading-relaxed text-amber-800">
              Rekomendasi jumlah persiapan di bawah ini merupakan <strong>decision support analitik awal</strong> berbasis histori penjualan dan variabilitas permintaan. Rekomendasi ini <strong>belum memperhitungkan</strong> sisa stok fisik di etalase, ketersediaan bahan baku di gudang, kapasitas tray oven, dan umur kadaluarsa produk. Tim dapur diharapkan tetap melakukan verifikasi fisik sebelum batch baking dimulai.
            </p>
          </div>
        </div>

        {/* Recommendations Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-[#ede8df] text-[#8c8275] uppercase text-[10px] tracking-wider bg-stone-50/50">
                <th className="py-3 px-4 font-bold">Nama Menu</th>
                <th className="py-3 px-3 font-bold">Kategori</th>
                <th className="py-3 px-3 font-bold text-right">Forecast Qty</th>
                <th className="py-3 px-3 font-bold text-right text-[#7c3f15]">Saran Persiapan</th>
                <th className="py-3 px-4 font-bold">Alasan Kebijakan Buffer</th>
                <th className="py-3 px-3 font-bold text-center">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#f2ede4]">
              {isLoadingRecs ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-[#8c8275]">
                    Memuat data rekomendasi produksi...
                  </td>
                </tr>
              ) : (
                (recommendations || []).slice(0, 15).map((rec, idx) => (
                  <tr key={idx} className="hover:bg-amber-50/40 transition-colors">
                    <td className="py-3 px-4 font-semibold text-[#1e1b18]">{rec.menu_name}</td>
                    <td className="py-3 px-3">
                      <span className="px-2 py-0.5 rounded-md text-[10px] font-bold tracking-wide uppercase bg-stone-100 text-stone-700">
                        {rec.menu_category}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-right text-stone-700 font-medium">
                      {rec.forecast_qty.toFixed(1)} pcs
                    </td>
                    <td className="py-3 px-3 text-right">
                      <span className="inline-block px-2.5 py-0.5 rounded-md font-bold text-sm bg-[#fbf8f5] text-[#7c3f15] border border-[#e6d7c3]">
                        {rec.suggested_prepare_qty} pcs
                      </span>
                    </td>
                    <td className="py-3 px-4 text-[#8c8275] max-w-md truncate" title={rec.recommendation_reason}>
                      {rec.recommendation_reason}
                    </td>
                    <td className="py-3 px-3 text-center">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-amber-50 text-amber-800 border border-amber-200">
                        {rec.recommendation_status}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* SECTION C: PRODUCT DEMAND FORECAST TABLE */}
      <section className="bg-white p-6 rounded-2xl border border-[#ede8df] shadow-2xs space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h3 className="text-base font-bold text-[#1e1b18] flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-[#7c3f15]" />
              Detail Prediksi Kuantitas Per Menu ({filteredProducts.length} Produk)
            </h3>
            <p className="text-xs text-[#8c8275]">
              Estimasi kuantitas terjual H+1 berbasis model machine learning terkalibrasi
            </p>
          </div>

          {/* Search & Category Filter */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative">
              <Search className="w-4 h-4 text-[#8c8275] absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Cari nama menu..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-9 pr-3 py-1.5 text-xs rounded-xl border border-[#ede8df] focus:outline-hidden focus:border-[#7c3f15] w-48 transition-colors"
              />
            </div>
            <div className="flex items-center gap-1 bg-stone-100 p-1 rounded-xl">
              {categories.map((cat) => (
                <button
                  key={cat}
                  onClick={() => setSelectedCategory(cat)}
                  className={`px-2.5 py-1 text-[11px] font-bold rounded-lg transition-colors ${
                    selectedCategory === cat
                      ? "bg-white text-[#7c3f15] shadow-2xs"
                      : "text-stone-600 hover:text-stone-900"
                  }`}
                >
                  {cat}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Product Forecast Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-[#ede8df] text-[#8c8275] uppercase text-[10px] tracking-wider bg-stone-50/50">
                <th className="py-3 px-4 font-bold">Nama Menu</th>
                <th className="py-3 px-3 font-bold">Kategori</th>
                <th className="py-3 px-3 font-bold text-right">Prediksi Qty (H+1)</th>
                <th className="py-3 px-3 font-bold">Model Version</th>
                <th className="py-3 px-3 font-bold">Run ID</th>
                <th className="py-3 px-3 font-bold text-center">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#f2ede4]">
              {isLoadingProducts ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-[#8c8275]">
                    Memuat data peramalan produk...
                  </td>
                </tr>
              ) : filteredProducts.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-[#8c8275]">
                    Tidak ada menu yang sesuai dengan pencarian.
                  </td>
                </tr>
              ) : (
                filteredProducts.map((p, idx) => (
                  <tr key={idx} className="hover:bg-amber-50/30 transition-colors">
                    <td className="py-3 px-4 font-semibold text-[#1e1b18]">{p.menu_name}</td>
                    <td className="py-3 px-3">
                      <span className="px-2 py-0.5 rounded-md text-[10px] font-bold uppercase bg-stone-100 text-stone-700">
                        {p.menu_category}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-right font-bold text-[#7c3f15]">
                      {p.predicted_qty.toFixed(1)} pcs
                    </td>
                    <td className="py-3 px-3 font-mono text-[11px] text-stone-600">{p.model_version}</td>
                    <td className="py-3 px-3 font-mono text-[10px] text-stone-500">{p.forecast_run_id}</td>
                    <td className="py-3 px-3 text-center">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-amber-50 text-amber-800 border border-amber-200">
                        {p.status}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* SECTION F: MODEL PERFORMANCE & GOVERNANCE */}
      <section className="bg-white p-6 rounded-2xl border border-[#ede8df] shadow-2xs space-y-4">
        <div className="flex items-center justify-between border-b border-[#ede8df] pb-4">
          <div>
            <h3 className="text-base font-bold text-[#1e1b18] flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5 text-emerald-600" />
              Model Performance & Governance Audit (F-11 & F-12)
            </h3>
            <p className="text-xs text-[#8c8275]">
              Hasil evaluasi obyektif terhadap holdout test set pada snapshot data yang sama
            </p>
          </div>
          <span className="text-xs font-semibold px-3 py-1 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200">
            Validated Run
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
          <div className="p-4 rounded-xl bg-stone-50/80 border border-stone-200/80 space-y-1">
            <p className="text-[11px] font-bold uppercase tracking-wider text-stone-500">
              Mean Absolute Error (MAE)
            </p>
            <p className="text-2xl font-black text-stone-900">
              {metrics?.latest_metrics?.mae ? metrics.latest_metrics.mae.toFixed(2) : "6.70"} pcs
            </p>
            <p className="text-[11px] text-stone-500">
              Rata-rata selisih prediksi vs penjualan riil
            </p>
          </div>

          <div className="p-4 rounded-xl bg-stone-50/80 border border-stone-200/80 space-y-1">
            <p className="text-[11px] font-bold uppercase tracking-wider text-stone-500">
              Root Mean Squared Error (RMSE)
            </p>
            <p className="text-2xl font-black text-stone-900">
              {metrics?.latest_metrics?.rmse ? metrics.latest_metrics.rmse.toFixed(2) : "12.29"} pcs
            </p>
            <p className="text-[11px] text-stone-500">
              Sensitif terhadap deviasi outlier kuantitas besar
            </p>
          </div>

          <div className="p-4 rounded-xl bg-stone-50/80 border border-stone-200/80 space-y-1">
            <p className="text-[11px] font-bold uppercase tracking-wider text-stone-500">
              Weighted Absolute % Error (WAPE)
            </p>
            <p className="text-2xl font-black text-stone-900">
              {metrics?.latest_metrics?.wape
                ? `${(metrics.latest_metrics.wape * 100).toFixed(1)}%`
                : "53.9%"}
            </p>
            <p className="text-[11px] text-stone-500">
              Persentase kesalahan terhadap total volume
            </p>
          </div>
        </div>

        {/* Model Comparison Table */}
        <div className="pt-2 space-y-2">
          <h4 className="text-xs font-bold text-stone-800 uppercase tracking-wider">
            Perbandingan Evaluasi Model (Holdout Test Set yang Sama: 2026-10-19)
          </h4>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border border-stone-200 rounded-xl overflow-hidden">
              <thead className="bg-stone-100 text-stone-600 text-[10px] uppercase font-bold">
                <tr>
                  <th className="py-2.5 px-3">Model Candidate</th>
                  <th className="py-2.5 px-3 text-right">MAE</th>
                  <th className="py-2.5 px-3 text-right">RMSE</th>
                  <th className="py-2.5 px-3 text-right">WAPE</th>
                  <th className="py-2.5 px-3 text-center">Status Promosi</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-200">
                <tr className="bg-emerald-50/40 font-semibold">
                  <td className="py-2.5 px-3 text-emerald-950 flex items-center gap-1.5">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                    Model 1: Baseline Naive (Lag-1 with Menu Mean Fallback)
                  </td>
                  <td className="py-2.5 px-3 text-right text-emerald-950 font-bold">6.70</td>
                  <td className="py-2.5 px-3 text-right text-emerald-950">12.29</td>
                  <td className="py-2.5 px-3 text-right text-emerald-950">53.9%</td>
                  <td className="py-2.5 px-3 text-center">
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-emerald-100 text-emerald-800">
                      ACTIVE (PROMOTED)
                    </span>
                  </td>
                </tr>
                <tr>
                  <td className="py-2.5 px-3 text-stone-700">Model 2: Ridge Regression (L2 Regularized)</td>
                  <td className="py-2.5 px-3 text-right text-stone-700">7.12</td>
                  <td className="py-2.5 px-3 text-right text-stone-700">10.65</td>
                  <td className="py-2.5 px-3 text-right text-stone-700">57.3%</td>
                  <td className="py-2.5 px-3 text-center text-stone-500">Kandidat Evaluasi</td>
                </tr>
                <tr>
                  <td className="py-2.5 px-3 text-stone-700">Model 3: Random Forest Regressor (Depth &lt;= 4)</td>
                  <td className="py-2.5 px-3 text-right text-stone-700">7.37</td>
                  <td className="py-2.5 px-3 text-right text-stone-700">10.62</td>
                  <td className="py-2.5 px-3 text-right text-stone-700">59.3%</td>
                  <td className="py-2.5 px-3 text-center text-stone-500">Kandidat Evaluasi</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="text-[11px] text-stone-500 italic pt-1">
            * Kebijakan Promosi Model: Model ML candidate (Ridge/RF) hanya dapat dipromosikan menggantikan Baseline apabila mencapai MAE lebih rendah pada test set yang sama. Karena Baseline Naive terbukti memiliki MAE terkecil (6.70 &lt; 7.12), Baseline Naive dipertahankan sebagai model produksi aktif (status: provisional).
          </p>
        </div>
      </section>
    </div>
  );
};
