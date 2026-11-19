<#
================================================================================
  TOKO ROTI PAGI (TRP) - STOP ALL BIG DATA PLATFORM
  Mematikan seluruh ekosistem dengan aman:
  1. Hentikan Producer Replay Python
  2. Hentikan 9 Container Docker (RAM kembali bebas, Data Parquet & DB aman)
================================================================================
#>

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  MEMATIKAN BAKERY DATA PLATFORM V4 (TOKO ROTI PAGI)     " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Hentikan process Producer Replay
Write-Host "`n[1/2] Menghentikan Producer Replay..." -ForegroundColor Yellow
$pidFile = Join-Path $PSScriptRoot "state\producer_replay.pid"
if (Test-Path $pidFile) {
    $targetPid = Get-Content $pidFile -ErrorAction SilentlyContinue
    if ($targetPid) {
        $proc = Get-Process -Id $targetPid -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "Menghentikan process producer (PID $targetPid)..." -ForegroundColor Yellow
            Stop-Process -Id $targetPid -Force -ErrorAction SilentlyContinue
            Write-Host "Producer Replay berhasil dihentikan." -ForegroundColor Green
        }
    }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
} else {
    Write-Host "Tidak ada background producer aktif di PID file." -ForegroundColor Gray
}

# 2. Hentikan container Docker
Write-Host "`n[2/2] Mematikan Container Docker Compose..." -ForegroundColor Yellow
docker compose down

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n==========================================================" -ForegroundColor Green
    Write-Host "  SEMUA LAYANAN TELAH BERHASIL DIMATIKAN DENGAN AMAN!    " -ForegroundColor Green
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host "✓ RAM laptop Anda telah dibebaskan sepenuhnya." -ForegroundColor Green
    Write-Host "✓ Seluruh data Parquet di MinIO dan SQLite di folder 'state/' tersimpan aman di disk." -ForegroundColor Green
} else {
    Write-Host "Peringatan: Terjadi kendala saat docker compose down." -ForegroundColor Red
}
