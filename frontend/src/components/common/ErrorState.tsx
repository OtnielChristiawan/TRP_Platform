import React from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface ErrorStateProps {
  message?: string;
  onRetry?: () => void;
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  message = "Gagal memuat data dari API. Pastikan service backend dan MinIO sedang berjalan.",
  onRetry,
}) => (
  <div className="bg-rose-50 border border-rose-200 rounded-xl p-8 text-center max-w-lg mx-auto my-8">
    <div className="inline-flex p-3 bg-rose-100 rounded-full text-rose-600 mb-3">
      <AlertTriangle className="w-6 h-6" />
    </div>
    <h4 className="text-base font-semibold text-rose-900 mb-1">
      Terjadi Kendala Koneksi Data
    </h4>
    <p className="text-xs text-rose-700 leading-relaxed mb-5">
      {message}
    </p>
    {onRetry && (
      <button
        onClick={onRetry}
        className="inline-flex items-center gap-2 px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white rounded-lg text-xs font-semibold shadow-xs transition-colors cursor-pointer"
      >
        <RefreshCw className="w-3.5 h-3.5" />
        <span>Coba Lagi</span>
      </button>
    )}
  </div>
);

export const EmptyState: React.FC<{
  title?: string;
  message?: string;
}> = ({
  title = "Tidak Ada Data Ditemukan",
  message = "Tidak ada catatan transaksi yang cocok dengan filter tanggal atau cabang yang dipilih. Coba perluas rentang tanggal.",
}) => (
  <div className="bg-white border border-[#ede8df] rounded-xl p-8 text-center max-w-md mx-auto my-8">
    <div className="text-3xl mb-2">🥐</div>
    <h4 className="text-sm font-semibold text-[#1e1b18] mb-1">{title}</h4>
    <p className="text-xs text-[#7c7267] leading-relaxed">{message}</p>
  </div>
);
