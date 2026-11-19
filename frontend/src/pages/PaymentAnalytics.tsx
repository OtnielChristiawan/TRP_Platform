import React from "react";
import { useQuery } from "@tanstack/react-query";
import {
  CreditCard,
  Wallet,
  Receipt,
  PieChart as PieIcon,
} from "lucide-react";
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
} from "recharts";
import { useFilters } from "../components/layout/Layout";
import { api } from "../services/api";
import { KPICard } from "../components/common/KPICard";
import { ChartSkeleton, KPISkeleton, TableSkeleton } from "../components/common/LoadingSkeleton";
import { EmptyState, ErrorState } from "../components/common/ErrorState";
import { formatNumber, formatPercent, formatRupiah } from "../utils/formatters";

const PAYMENT_COLORS = ["#7c3f15", "#c86d51", "#d97706", "#2563eb", "#059669"];

export const PaymentAnalytics: React.FC = () => {
  const { filters, refreshAll } = useFilters();

  const {
    data: payments,
    isLoading: isLoadingPayments,
    isError: isErrorPayments,
    error: paymentsError,
  } = useQuery({
    queryKey: ["paymentSummary", filters],
    queryFn: () => api.getPaymentSummary(filters),
    enabled: Boolean(filters.startDate && filters.endDate),
  });

  if (isErrorPayments) {
    return (
      <ErrorState
        message={paymentsError instanceof Error ? paymentsError.message : undefined}
        onRetry={refreshAll}
      />
    );
  }

  const hasData = payments && payments.length > 0;

  // Calculate totals
  const totalVolume = payments ? payments.reduce((acc, p) => acc + p.net_sales, 0) : 0;
  const totalBills = payments ? payments.reduce((acc, p) => acc + p.total_bills, 0) : 0;
  const topPayment = hasData ? payments[0] : null;

  const CustomPieTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const row = payload[0].payload;
      return (
        <div className="bg-[#1e1b18] text-white p-3 rounded-lg text-xs shadow-lg border border-stone-800">
          <p className="font-semibold text-stone-200 mb-1">{row.payment_method}</p>
          <p className="text-amber-400 font-bold">{formatRupiah(row.net_sales)}</p>
          <p className="text-stone-300 mt-1">
            Transaksi: <span className="font-medium text-white">{row.total_bills} bills</span>
          </p>
          <p className="text-stone-300">
            Pangsa: <span className="font-medium text-white">{formatPercent(row.payment_contribution_pct)}</span>
          </p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="pb-2 border-b border-[#ede8df]">
        <h2 className="text-xl font-bold tracking-tight text-[#1e1b18]">
          Payment Method Analytics
        </h2>
        <p className="text-xs text-[#7c7267] mt-0.5">
          Analisis perputaran uang berdasarkan metode pembayaran kasir Toko Roti Pagi (dihitung dari level Bill Grain tanpa duplikasi).
        </p>
      </div>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {isLoadingPayments ? (
          <>
            <KPISkeleton />
            <KPISkeleton />
            <KPISkeleton />
          </>
        ) : (
          <>
            <KPICard
              title="Total Volume Pembayaran"
              value={formatRupiah(totalVolume)}
              subtitle="Nilai penyelesaian transaksi"
              icon={<Wallet className="w-5 h-5" />}
            />
            <KPICard
              title="Total Struk / Bills"
              value={`${formatNumber(totalBills)} bills`}
              subtitle="Jumlah transaksi terverifikasi"
              icon={<Receipt className="w-5 h-5" />}
            />
            <KPICard
              title="Metode Paling Populer"
              value={topPayment ? topPayment.payment_method : "-"}
              subtitle={
                topPayment
                  ? `${formatPercent(topPayment.payment_contribution_pct)} dari total penjualan`
                  : "-"
              }
              icon={<CreditCard className="w-5 h-5" />}
            />
          </>
        )}
      </div>

      {!isLoadingPayments && !hasData ? (
        <EmptyState />
      ) : (
        <>
          {/* Charts Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Payment Volume Bar Chart */}
            <div className="bg-white rounded-xl border border-[#ede8df] p-5 shadow-xs">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-bold text-[#1e1b18]">
                    Volume Transaksi per Metode
                  </h3>
                  <p className="text-xs text-[#7c7267]">
                    Perbandingan omzet bersih metode pembayaran
                  </p>
                </div>
                <div className="p-1.5 bg-[#f5efe6] text-[#7c3f15] rounded-lg">
                  <CreditCard className="w-4 h-4" />
                </div>
              </div>
              {isLoadingPayments ? (
                <ChartSkeleton />
              ) : payments && payments.length > 0 ? (
                <div className="w-full h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={payments} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#ede8df" />
                      <XAxis
                        dataKey="payment_method"
                        tick={{ fontSize: 11, fill: "#8c8275" }}
                        axisLine={{ stroke: "#ede8df" }}
                        tickLine={false}
                      />
                      <YAxis
                        tickFormatter={(val) => `${(val / 1000000).toFixed(1)}jt`}
                        tick={{ fontSize: 11, fill: "#8c8275" }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <Tooltip content={<CustomPieTooltip />} />
                      <Bar
                        dataKey="net_sales"
                        fill="#7c3f15"
                        radius={[4, 4, 0, 0]}
                        maxBarSize={48}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : null}
            </div>

            {/* Payment Contribution Pie Chart */}
            <div className="bg-white rounded-xl border border-[#ede8df] p-5 shadow-xs">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-bold text-[#1e1b18]">
                    Pangsa Pasar Metode Pembayaran
                  </h3>
                  <p className="text-xs text-[#7c7267]">
                    Persentase kontribusi omzet per metode
                  </p>
                </div>
                <div className="p-1.5 bg-[#f5efe6] text-[#7c3f15] rounded-lg">
                  <PieIcon className="w-4 h-4" />
                </div>
              </div>
              {isLoadingPayments ? (
                <ChartSkeleton />
              ) : payments && payments.length > 0 ? (
                <div className="w-full h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={payments}
                        dataKey="net_sales"
                        nameKey="payment_method"
                        cx="50%"
                        cy="50%"
                        innerRadius={50}
                        outerRadius={80}
                        paddingAngle={4}
                      >
                        {payments.map((_, index) => (
                          <Cell
                            key={`cell-${index}`}
                            fill={PAYMENT_COLORS[index % PAYMENT_COLORS.length]}
                          />
                        ))}
                      </Pie>
                      <Tooltip content={<CustomPieTooltip />} />
                      <Legend
                        verticalAlign="bottom"
                        height={36}
                        formatter={(val, entry: any) => (
                          <span className="text-xs text-[#4a4238] font-medium mr-2">
                            {val} ({formatPercent(entry.payload.payment_contribution_pct)})
                          </span>
                        )}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              ) : null}
            </div>
          </div>

          {/* Payment Summary Table */}
          <div className="bg-white rounded-xl border border-[#ede8df] overflow-hidden shadow-xs">
            <div className="p-5 border-b border-[#ede8df]">
              <h3 className="text-sm font-bold text-[#1e1b18]">
                Tabel Distribusi Pembayaran
              </h3>
              <p className="text-xs text-[#7c7267] mt-0.5">
                Rincian frekuensi transaksi dan nominal settlement
              </p>
            </div>

            {isLoadingPayments ? (
              <div className="p-5">
                <TableSkeleton rows={4} />
              </div>
            ) : payments && payments.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-[#faf7f2] text-[#7c7267] font-semibold border-b border-[#ede8df]">
                    <tr>
                      <th className="py-3 px-4">Metode Pembayaran</th>
                      <th className="py-3 px-4 text-right">Total Transaksi (Bills)</th>
                      <th className="py-3 px-4 text-right font-bold text-[#1e1b18]">Net Sales</th>
                      <th className="py-3 px-4 text-right">Pangsa Kontribusi</th>
                      <th className="py-3 px-4 w-48">Porsi Visual</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#f4f0e9]">
                    {payments.map((row, idx) => (
                      <tr key={idx} className="hover:bg-[#fcfaf7] transition-colors">
                        <td className="py-3 px-4 font-semibold text-[#1e1b18] flex items-center gap-2">
                          <span
                            className="w-2.5 h-2.5 rounded-full"
                            style={{
                              backgroundColor: PAYMENT_COLORS[idx % PAYMENT_COLORS.length],
                            }}
                          />
                          {row.payment_method}
                        </td>
                        <td className="py-3 px-4 text-right font-medium">
                          {formatNumber(row.total_bills)}
                        </td>
                        <td className="py-3 px-4 text-right font-bold text-[#7c3f15]">
                          {formatRupiah(row.net_sales)}
                        </td>
                        <td className="py-3 px-4 text-right font-semibold text-[#4a4238]">
                          {formatPercent(row.payment_contribution_pct)}
                        </td>
                        <td className="py-3 px-4">
                          <div className="w-full bg-[#ede8df] rounded-full h-2 overflow-hidden">
                            <div
                              className="h-2 rounded-full transition-all duration-500"
                              style={{
                                width: `${Math.min(100, Math.max(0, row.payment_contribution_pct))}%`,
                                backgroundColor: PAYMENT_COLORS[idx % PAYMENT_COLORS.length],
                              }}
                            />
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>
        </>
      )}
    </div>
  );
};
