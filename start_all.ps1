<#
================================================================================
  TOKO ROTI PAGI (TRP) - START ALL BIG DATA PLATFORM
  Menyalakan seluruh ekosistem:
  1. Redpanda (Streaming Broker) & Redpanda Console
  2. MinIO S3 (Lakehouse Storage)
  3. Spark Bronze Streaming (Ingestion ke S3 Parquet)
  4. Schedulers (Master Menu, Silver Curated, Gold Data Marts)
  5. FastAPI Backend Engine (DuckDB Analytics & Governance)
  6. React Web Dashboard (Vite UI Port 5173)
  7. Producer Replay (Streaming transaksi ke Bronze)
================================================================================
#>

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  MENYALAKAN BAKERY DATA PLATFORM V4 (TOKO ROTI PAGI)    " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Pastikan Docker Desktop sedang aktif
Write-Host "`n[1/4] Memeriksa status Docker..." -ForegroundColor Yellow
try {
    $dockerCheck = docker info 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Docker Desktop belum berjalan!" -ForegroundColor Red
        Write-Host "Silakan buka aplikasi Docker Desktop di Windows terlebih dahulu, lalu jalankan script ini kembali." -ForegroundColor Red
        exit 1
    }
    Write-Host "Docker Engine aktif!" -ForegroundColor Green
} catch {
    Write-Host "ERROR: Gagal menghubungi Docker CLI." -ForegroundColor Red
    exit 1
}

# 2. Menyalakan seluruh container Docker dengan profiles
Write-Host "`n[2/4] Menyalakan 9 Container Ekosistem Big Data (Docker Compose)..." -ForegroundColor Yellow
docker compose --profile spark --profile scheduler --profile silver-scheduler --profile gold-scheduler --profile dashboard up -d

if ($LASTEXITCODE -ne 0) {
    Write-Host "Peringatan: Ada error saat menjalankan docker compose." -ForegroundColor Red
} else {
    Write-Host "Semua 9 Container Docker berhasil dinyalakan (Up)!" -ForegroundColor Green
    Start-Sleep -Seconds 3
}

# 3. Menjalankan Producer Replay (Pengirim Transaksi ke Kafka / Bronze)
Write-Host "`n[3/4] Mengaktifkan Producer Replay (Streaming Transaksi)..." -ForegroundColor Yellow
$pidFile = Join-Path $PSScriptRoot "state\producer_replay.pid"
$pythonExe = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python.exe"
}

# Cek apakah producer sudah jalan sebelumnya
$alreadyRunning = $false
if (Test-Path $pidFile) {
    $oldPid = Get-Content $pidFile -ErrorAction SilentlyContinue
    if ($oldPid -and (Get-Process -Id $oldPid -ErrorAction SilentlyContinue)) {
        Write-Host "Producer Replay sudah aktif (PID: $oldPid)." -ForegroundColor Cyan
        $alreadyRunning = $true
    }
}

if (-not $alreadyRunning) {
    Write-Host "Memulai producer replay di background..." -ForegroundColor Yellow
    $replayArgs = "producer/replay.py --source-anchor-date 2026-10-18 --interval 15"
    $proc = Start-Process -FilePath $pythonExe -ArgumentList $replayArgs -WorkingDirectory $PSScriptRoot -PassThru -WindowStyle Minimized
    if ($proc) {
        $proc.Id | Set-Content $pidFile
        Write-Host "Producer Replay aktif di background (PID: $($proc.Id))!" -ForegroundColor Green
    } else {
        Write-Host "Gagal memulai background producer. Silakan jalankan manual jika diperlukan." -ForegroundColor Red
    }
}

# 4. Membuka Dashboard di Browser
Write-Host "`n[4/4] Membuka Web Dashboard..." -ForegroundColor Yellow
Start-Process "http://localhost:5173"

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host "  PLATFORM SIAP DIGUNAKAN! (ALL SYSTEMS GO)               " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "Dashboard Web UI : http://localhost:5173" -ForegroundColor Cyan
Write-Host "Backend API Docs : http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "MinIO S3 Console : http://localhost:9001 (User: bakeryadmin / Pass: bakerydemo123)" -ForegroundColor Cyan
Write-Host "Redpanda Console : http://localhost:8080" -ForegroundColor Cyan
Write-Host "`nUntuk mematikan sistem nanti, cukup jalankan: .\stop_all.ps1 atau double-click stop_all.bat" -ForegroundColor Yellow
