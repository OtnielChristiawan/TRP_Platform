# Bakery Data Platform V4 — ESB file ingestion tanpa API

**Status:** kode starter diuji parser dan unit test secara lokal; Docker + Redpanda + Spark + MinIO **belum diuji end-to-end** dalam lingkungan pembuatan. Ini baru Bronze ingestion, **bukan Silver/Gold atau forecasting**.

## Arsitektur

- Transaksi: ekspor ESB XLSX/CSV → `producer/replay.py` (**folder watcher + catch-up**) → Redpanda `bakery.transactions.v1` (JSON, 1 event/bill) → Spark Structured Streaming → MinIO `bakery-bronze/transactions/` (Parquet).
- Master Menu: ekspor ESB XLSX/CSV → pemeriksaan harian atau manual → `batch/master_menu.py` (checksum/snapshot) → arsip XLSX/CSV asli di `bakery-bronze/originals/master_menu/` → Spark Batch → `bakery-bronze/master_menu/snapshot_id=.../` (Parquet).
- Producer menyimpan `state/replay.sqlite`, batch menyimpan `state/master_menu.sqlite`. Jangan hapus database ini atau Docker volumes jika ingin melanjutkan progres. `spark_checkpoints` adalah volume persisten khusus Spark.
- **Belum ada otomatisasi transaksi POS live**. Hanya transaksi dalam ekspor file yang sudah tersedia. File baru terdeteksi tanpa restart producer.
- **Belum ada Silver upsert Master Menu**: snapshot berurutan disimpan di Bronze. INSERT/UPDATE/NO CHANGE, dim_menu serta 3 mart Gold perlu diimplementasikan setelah pipeline Bronze stabil.

## Folder upload

```
data/transactions/incoming/
    Sales Recapitulation Detail Report_CKKNTRPADMIN_....xlsx
    Sales Recapitulation Detail Report_CKKNTRPADMIN_....csv

data/master_menu/incoming/
    Master Menu Template Data - 20261115173456.xlsx
    Master Menu Template Data - ....xlsx
```

JANGAN letakkan semua file dalam satu folder. Format yang dikenali .xlsx dan .csv; untuk contoh awal pakai ekspor Excel asli. Jangan simpan file yang masih sedang disalin dengan ekstensi final: salin sebagai `.tmp`, setelah selesai rename ke `.xlsx`/`.csv`. File yang sudah diambil reader sebaiknya tidak diedit. **Jangan unggah file ESB dengan data personal yang tidak diizinkan.**

## Prasyarat

Windows dengan Docker Desktop + Python 3.10+ terinstal. Disarankan RAM 16 GB dan sisa disk memadai, karena Spark + broker + MinIO cukup berat. Internet diperlukan pertama kali untuk mengunduh image Docker, Python packages, dan JAR Spark. Setelah semua sudah tercache, pipeline lokal bisa dijalankan tanpa internet.

## Langkah cepat (PowerShell, jalankan di root V4)

1. Masukkan kedua file ESB ke folder masing-masing. **ZIP ini tidak menyertakan transaksi pribadi milik pengguna.**
2. Install Python dependency producer:

```powershell
py -m pip install -r requirements.txt
```

3. Jalankan infrastruktur:

```powershell
docker compose up -d redpanda topic-init console minio minio-init
```

4. **Preview** replay (tanpa mengirim):

```powershell
py producer/replay.py --source-anchor-date 2026-10-18 --replay-date 2026-11-17 --once --dry-run
```

5. Producer aktif terus (terminal 1):

```powershell
py producer/replay.py --source-anchor-date 2026-10-18 --replay-date 2026-11-17 --interval 15
```

Waktu replay menggeser **18 Okt 2026 → 17 Nov 2026** pada jam yang sama. Jika dijalankan pada 17 November pukul 12:50, transaksi 18 Oktober yang dijadwalkan sebelum 12:50 dikirim secepat yang bisa di-ACK Kafka, lalu transaksi jam berikutnya menunggu. Tanggal sumber 19 Oktober terjadwal 18 November. Ini **bukan** streaming langsung dari ESB. Bila jam replay sudah berlalu saat file datang, event diproses lewat catch-up.

> Kalau memulai pada tanggal yang berbeda, ganti `--replay-date` pada **run pertama**. Berikutnya harus mempertahankan mapping itu; V4 menyimpannya di SQLite dan mengabaikan opsi tanggal yang berbeda saat restart. `--source-anchor-date` sebaiknya tanggal paling awal yang direncanakan, misalnya 2026-10-18.

6. Jalankan Spark Streaming → Bronze (terminal 2):

```powershell
docker compose --profile spark up -d spark-bronze
docker compose logs -f spark-bronze
```

7. **Batch Master Menu sekarang (manual)**:

```powershell
# Menjalankan satu kali (manual backfill / catch-up langsung):
docker compose --profile batch run --rm master-menu-batch
```

8. **Aktifkan batch scheduler otomatis setiap hari pukul 06:00 WIB**:

```powershell
# Menjalankan scheduler di latar belakang (daemon):
docker compose --profile scheduler up -d master-menu-scheduler

# Memeriksa log scheduler:
docker compose logs -f master-menu-scheduler

# Menghentikan scheduler:
docker compose --profile scheduler stop master-menu-scheduler
```

> **Perilaku Batch & Idempotensi:**
> - Scheduler berjalan setiap hari pukul **06:00 WIB** (Asia/Jakarta) dan memeriksa folder `data/master_menu/incoming/`.
> - **Catch-up otomatis:** Jika laptop mati saat jadwal terlewat, scheduler akan langsung memproses file yang belum di-ingest saat container dinyalakan kembali.
> - **Idempotensi berbasis SHA-256:** Checksum setiap file dihitung dan disimpan di `state/master_menu.sqlite`. File dengan konten yang sama tidak akan menghasilkan snapshot duplikat.
> - **Preservasi kolom 100%:** Seluruh baris, sheet, dan 22+ kolom asli dari ekspor ESB dipertahankan di Bronze (`s3a://bakery-bronze/master_menu/snapshot_id=.../`) dalam format Parquet (kompresi Snappy), raw payload JSON, dan struct.
> - **Arsip sumber immutable:** File XLSX/CSV asli diarsipkan secara utuh ke `s3a://bakery-bronze/originals/master_menu/{snapshot_id}/`.
> - **Query di DBeaver (DuckDB):** Jalankan `sql/04_master_menu_view.sql` untuk membuat view `bronze_master_menu` dan mengeksplorasi data dengan `SELECT * FROM bronze_master_menu LIMIT 100;`.

9. **Silver Layer Incremental Batch (manual & scheduler)**:

```powershell
# Jalankan satu kali (manual incremental batch / backfill):
docker compose --profile silver run --rm silver-batch

# Jalankan scheduler otomatis setiap 15 menit di background:
docker compose --profile silver-scheduler up -d silver-scheduler

# Memeriksa log scheduler Silver:
docker compose logs -f silver-scheduler

# Menghentikan scheduler Silver:
docker compose --profile silver-scheduler stop silver-scheduler
```

> **Perilaku Silver Layer:**
> - **Dataset Output:**
>   - `s3a://bakery-silver/sales_bills/`: Grain 1 baris per bill/transaksi (partitioned by `sales_date`).
>   - `s3a://bakery-silver/sales_items/`: Grain 1 baris per item penjualan (partitioned by `sales_date`).
>   - `s3a://bakery-silver/master_menu/`: Master menu ternormalisasi (partitioned by `snapshot_date`).
>   - `s3a://bakery-silver/data_quality/`: Ringkasan audit dan metrik batch.
> - **Deduplikasi Teknis:** Memprioritaskan `payload_version` tertinggi (V2 menggantikan V1) dan Kafka offset tertinggi. Item sah dengan menu yang sama dalam satu bill tidak hilang.
> - **Pembersihan & Tipe Data:** Nilai mata uang Indonesia (`xx.xxx,yy`) dikonversi ke `DECIMAL(14,2)` murni. Kuantitas ke `DECIMAL(12,2)`. Timestamp dalam WIB (`Asia/Jakarta`).
> - **Penghapusan Kolom:** Kolom `Table Section`, `Table Name`, `Area`, dan PII (nama pelanggan/karyawan) telah dihilangkan dari Silver.
> - **Flag Anomali:** Item berharga 0 diberi flag `is_zero_price = true` dan tidak dihapus.
> - **Dynamic Partition Overwrite:** Menggunakan mode overwrite partisi dinamis Spark sehingga hanya partisi `sales_date` yang terdampak yang diperbarui; partisi historis tetap aman.
> - **Query di DBeaver (DuckDB):** Jalankan `sql/05_silver_views.sql` untuk query `silver_sales_bills`, `silver_sales_items`, `silver_master_menu`, dan `silver_data_quality`.

10. **Gold Layer Analytical Data Marts (manual & scheduler)**:

```powershell
# Jalankan satu kali (manual batch / full recalculation):
docker-compose --profile gold run --rm gold-batch

# Jalankan scheduler otomatis setiap 30 menit di background (daemon):
docker-compose --profile gold-scheduler up -d gold-scheduler

# Memeriksa log scheduler Gold:
docker-compose logs -f gold-scheduler

# Menghentikan scheduler Gold:
docker-compose --profile gold-scheduler stop gold-scheduler
```

> **Perilaku & Data Marts Gold Layer:**
> - **Dataset Output (`s3a://bakery-gold/`):**
>   - `gold_sales_daily/`: Grain `(sales_date, branch)`. KPI harian: Total Bills, Net Sales, Gross Sales, AOV, Qty, Zero Price Items.
>   - `gold_sales_hourly/`: Grain `(sales_date, sales_hour, branch)`. Distribusi penjualan per jam berdasarkan `sales_date_out` (WIB).
>   - `gold_menu_performance_daily/`: Grain `(sales_date, branch, menu_key)`. Top selling menu, revenue per menu, dan enrichment Master Menu (status `MATCHED`/`UNMATCHED`).
>   - `gold_category_performance_daily/`: Grain `(sales_date, branch, menu_category)`. Kontribusi penjualan per kategori produk (`sales_contribution_pct`).
>   - `gold_payment_daily/`: Grain `(sales_date, branch, payment_method)`. Distribusi pembayaran dari grain bill (`payment_contribution_pct`).
>   - `gold_ml_demand_features/`: Grain `(sales_date, branch, menu_key)`. Fitur time-series lags (`lag_1_qty`, `lag_7_qty`) dan rolling average 7 hari tanpa data leakage.
>   - `metadata/current_manifest.json`: Manifest kesehatan batch, metadata run, dan catatan validasi data quality.
> - **Integritas Finansial 100%:** Seluruh perhitungan `Net Sales` terekonsiliasi sempurna (selisih Rp 0,00) antara laporan harian, per jam, per menu, per kategori, dan metode pembayaran.
> - **Query di DBeaver (DuckDB):** Jalankan `sql/06_gold_views.sql` untuk membuat view DBeaver siap pakai dan kueri analitik dashboard monitoring.

11. Console:
- Redpanda: http://localhost:8080
- MinIO: http://localhost:9001 (demo user: `bakeryadmin`, password: `bakerydemo123`)

Ubah kredensial contoh sebelum dipakai di jaringan bersama. Jangan expose kedua console ke internet. Jalankan `docker compose down` untuk berhenti (tanpa `-v`: volumes disimpan). `docker compose down -v` **menghapus data volumes**, hindari jika ingin menyimpan data.

## Perilaku file transaksi bertahap

- Upload file A: `18 Okt–16 Nov`, producer mendeteksi, menggabungkan tiap bill dalam satu event dan menyimpan jadwal di `state/replay.sqlite`.
- Upload file B kemudian, misalnya `17–30 Nov` setelah periode itu benar-benar ada; **producer masih berjalan** dan memindai folder setiap 15 detik.
- Bila bill yang sama ada dalam dua ekspor dan payload identik, cuma satu bill masuk antrean. Bila payload bill sama ID tapi berbeda isi, V4 mencatat di tabel `conflicts` dan **tidak otomatis mengganti data sebelumnya**. Perubahan/void transaksi harus ditangani dengan aturan update terpisah pada iterasi lanjutan.
- Jika upload file periode lebih awal belakangan, transaksi itu akan ditambahkan dengan jadwal asli yang mungkin sudah lewat sehingga langsung catch-up. Urutan kedatangan di Kafka dapat berbeda dari urutan event_time; itu valid untuk late events.
- Producer menandai `sent` hanya setelah broker memberi ACK; crash tepat setelah ACK dan sebelum commit SQLite masih bisa menghasilkan retry duplikat. Bronze append-only menyimpan jejak, dedup dilakukan di Silver berdasarkan `event_id` dan kebijakan versioning.

## Recovery

- **Spark mati, Kafka hidup**: broker menampung event baru selama volume + retention cukup (contoh 30 hari), Spark mengambil backlog dari checkpoint ketika hidup lagi.
- **Producer mati**: semua transaksi terjadwal yang belum ditandai `sent` tetap di SQLite, dilanjutkan setelah restart.
- **Laptop mati**: tidak ada producer/broker yang bekerja selama mati; file CSV/XLSX tetap ada dan jadwal tertinggal akan catch-up saat semuanya aktif lagi.
- Untuk audit sumber batch, master XLSX/CSV asli disalin ke MinIO secara immutable, bersamaan dengan snapshot Parquet.
- Perlu backup folder `state`, file sumber dan volumes Docker; SQLite saja bukan cadangan seluruh sistem.

## Batasan penting

1. Topic Kafka memakai **JSON**, bukan Avro. Keduanya tetap disimpan sebagai **Parquet** di MinIO Bronze.
2. V4 tidak punya menu Silver join/upsert, tabel Delta/Iceberg, monitoring/alerting lengkap, atau inference ML. Semua itu pekerjaan lanjutan sesuai dokumen TBP.
3. Identitas `event_id` menggunakan `Sales Number:Bill Number`. Jika satu bill memiliki pembatalan/perubahan, konflik dicatat; jangan menganggap update otomatis.
4. Master Menu tidak punya `Menu Code` stabil pada sampel. Silver kelak butuh business key yang mempertimbangkan `Menu Template Name`, `Menu Category`, `Menu Category Detail`, `Menu Name` serta kemungkinan perubahan nama.
5. Untuk streaming historis sepanjang ~1 bulan dengan kecepatan asli, replay membutuhkan ~1 bulan waktu nyata; mode catch-up hanya mempercepat event **yang sudah lewat jadwalnya**.
6. Jadwal batch harian hanya memeriksa file ekspor yang tersedia di disk; tidak menghubungi ESB API.
7. Package Spark (`hadoop-aws` dan kafka connector) diambil pada run pertama. Jika runtime tidak kompatibel, sesuaikan versi JAR dengan versi Spark Hadoop lingkunganmu.

## Tes

```powershell
py -m unittest discover -s tests -v
```

Cek batch registry: `state/master_menu.sqlite`; replay registry: `state/replay.sqlite`.

## Panduan Operasional Docker (Mematikan & Menghidupkan)

### 1. Cara Mematikan Sistem (Shutdown)

#### A. Mematikan Normal (DATA & PROGRESS TETAP AMAN)
Gunakan ini saat selesai bekerja/kuliah dan ingin mematikan laptop tanpa kehilangan data MinIO & Kafka:
```powershell
# Matikan semua container dari seluruh profile (tanpa menghapus volume data)
docker compose --profile "*" down
```
> **PENTING:** Jangan gunakan flag `-v`! Semua data transaksi di Kafka, bucket MinIO (Bronze & Silver), dan checkpoint Spark akan tersimpan aman di volume Docker.

atau

> .\stop_all.ps1

---

### 2. Cara Menghidupkan Kembali Sistem (Startup)

#### Opsi A: Hidupkan Bertahap (Direkomendasikan untuk Development & Testing)

1. **Nyalakan Layanan Inti (Broker Kafka & Storage MinIO):**
   ```powershell
   docker compose up -d redpanda topic-init minio minio-init console
   
   ```
   *Tunggu ~10 detik hingga Redpanda Console ([http://localhost:8080](http://localhost:8080)) dan MinIO ([http://localhost:9001](http://localhost:9001)) aktif.*

2. **Nyalakan Spark Bronze Streaming:**
   ```powershell
   docker compose --profile spark up -d spark-bronze
   ```
   *Spark akan standby menunggu data masuk ke topik Kafka `bakery.transactions.v1`.*

3. **Jalankan Ingestion Master Menu (Produk):**
   ```powershell
   # Sekali jalan (manual):
   docker compose --profile batch run --rm master-menu-batch
   
   # ATAU scheduler harian (06:00 WIB di background):
   docker compose --profile scheduler up -d master-menu-scheduler
   ```

4. **Jalankan Producer Replay Transaksi:**
   ```powershell
   .\.venv\Scripts\python producer/replay.py --source-anchor-date 2026-10-18
   ```

5. **Jalankan Transformasi Silver Layer:**
   ```powershell
   # Sekali jalan (manual batch):
   docker compose --profile silver run --rm silver-batch
   
   # ATAU scheduler otomatis tiap 15 menit:
   docker compose --profile silver-scheduler up -d silver-scheduler
   ```

6. **Jalankan Sales Analytics Dashboard (FastAPI & React UI):**
   ```powershell
   # Jalankan backend API dan frontend dashboard bersamaan:
   docker-compose --profile dashboard up -d

   # Akses Web Dashboard di browser:
   # http://localhost:5173

   # Akses Dokumentasi Interaktif Swagger REST API:
   # http://localhost:8000/docs
   ```

#### Opsi B: Nyalakan Semua Service Sekaligus (All Daemon Mode)
Jika semua pipeline sudah siap dan ingin menjalankan seluruh daemon background:
```powershell
docker-compose --profile spark --profile scheduler --profile silver-scheduler --profile gold-scheduler --profile dashboard up -d
```

atau > .\start_all.ps1
---

## Sales Analytics Dashboard & REST API

Aplikasi dashboard analitik modern untuk Toko Roti Pagi (TRP) yang terhubung langsung ke **Gold Layer Parquet** di MinIO via engine query **DuckDB**:

### 1. Fitur Halaman Dashboard
- **Overview:** Ringkasan KPI eksekutif (Net Sales, Total Bills, Qty Sold, AOV), grafik tren penjualan harian, pola jam sibuk transaksi, Top 5 Menu terlaris, dan pangsa pasar kategori.
- **Sales Analytics:** Visualisasi mendalam penjualan bersih harian, jam sibuk operasional kasir, serta tabel data harian per cabang.
- **Product & Menu Analytics:** Peringkat menu terlaris (sort by Net Sales / Qty), pencarian nama menu, filter kategori, status item promo gratis (`zero_price_qty`), dan status rekonsiliasi Master Menu (`MATCHED`/`UNMATCHED`).
- **Payment Analytics:** Distribusi metode pembayaran (CASH, QRIS BRI) dihitung dari level *bill grain* tanpa risiko penggandaan nominal transaksi.
- **Global Filters:** Filter dinamis tanggal mulai, tanggal akhir, dan cabang yang secara otomatis disesuaikan dengan rentang data yang tersedia di Gold Layer.

### 2. Endpoint REST API FastAPI (`http://localhost:8000`)
- `GET /api/v1/health`: Status kesehatan backend dan informasi versi.
- `GET /api/v1/data/freshness`: Metadata run ID batch Gold, status sinkronisasi, dan timestamp transaksi terbaru.
- `GET /api/v1/filters`: Pilihan filter cabang, rentang tanggal (min/max), kategori, dan metode pembayaran.
- `GET /api/v1/dashboard/summary`: Agregasi KPI utama dan perbandingan pertumbuhan periode lalu.
- `GET /api/v1/sales/daily`: Data runtun waktu penjualan harian.
- `GET /api/v1/sales/hourly`: Agregasi volume dan nilai transaksi per jam (WIB).
- `GET /api/v1/menus/top`: Peringkat produk menu teratas (`limit`, `sort_by`, `category`).
- `GET /api/v1/categories/performance`: Kontribusi penjualan per kategori produk.
- `GET /api/v1/payments/summary`: Pembagian metode pembayaran dan persentase kontribusi.

---

### 3. Troubleshooting Docker & Spark Checkpoint

* **Container `spark-bronze` Restart Terus (Crash Loop):**
  Jika log Spark menampilkan error `BATCH_METADATA_NOT_FOUND` atau `Unable to find batch ... 9.compact`, ini berarti file metadata di MinIO tidak sinkron dengan checkpoint Spark (biasanya terjadi jika bucket MinIO sempat dihapus sebagian sementara volume checkpoint masih ada).
  **Solusi:**
  ```powershell
  # 1. Stop spark-bronze
  docker stop bakery-v4-spark-bronze-1

  # 2. Hapus checkpoint Spark yang korup
  docker run --rm -v bakery-v4_spark_checkpoints:/cp alpine sh -c "rm -rf /cp/bakery-bronze"

  # 3. Jalankan kembali spark-bronze
  docker compose --profile spark up -d spark-bronze
  ```
  Spark akan membaca ulang topik Kafka dari offset awal (`earliest`) dan membuat metadata baru yang bersih.

* **Perbedaan Waktu Jam Transaksi di DuckDB / DBeaver (UTC vs WIB):**
  File Parquet menyimpan timestamp dalam standar UTC. Oleh karena itu, jam `19:38 WIB` akan tersimpan sebagai `12:38 UTC` (-7 jam).
  Untuk menampilkannya kembali dalam waktu lokal Jakarta di DBeaver, jalankan perintah ini sebelum query:
  ```sql
  SET TimeZone = 'Asia/Jakarta';
  ```


---

## Machine Learning Demand Forecasting & Production Planner (F-11, F-12, F-13)

Modul Machine Learning terintegrasi penuh untuk peramalan permintaan roti/minuman dan perencanaan produksi dapur:

### 1. Fitur Halaman Demand Forecasting (`http://localhost:5173/forecast`)
- **Section A — Forecast Overview (KPIs):** Estimasi total kuantitas produk terjual besok (H+1), jumlah menu terprediksi, model aktif, dan top demanded menu.
- **Section B — Seven-Day Demand Trend:** Proyeksi multi-step total penjualan 7 hari ke depan (H+1 s/d H+7) dengan faktor musiman akhir pekan.
- **Section C — Product Demand Forecast:** Tabel prediksi detail per menu dengan pencarian cepat dan filter kategori.
- **Section D — Hourly Demand Forecast:** Estimasi kurva jam sibuk operasional kasir (09:00 - 19:00 WIB) untuk persiapan staf dan batch oven.
- **Section E — Production Preparation Recommendation:** Rekomendasi kuantitas batch siap panggang (`Forecast Qty + Safety Stock Buffer Z*σ`), alasan kebijakan, dan operational disclaimer.
- **Section F — Model Performance & Governance:** Evaluasi obyektif terhadap holdout test set (MAE, RMSE, WAPE) dan tabel perbandingan Model 1 (Baseline) vs Model 2 (Ridge) vs Model 3 (Random Forest).

### 2. Endpoint REST API ML (`http://localhost:8000/api/v1/ml/*`)
- `GET /api/v1/ml/summary`: Ringkasan KPI eksekutif prediksi besok.
- `GET /api/v1/ml/forecast/products`: Prediksi permintaan per menu (`branch`, `forecast_date`, `menu_key`, `limit`).
- `GET /api/v1/ml/forecast/weekly`: Proyeksi permintaan total 7 hari ke depan.
- `GET /api/v1/ml/forecast/hourly`: Distribusi jam sibuk operasional untuk hari berikutnya.
- `GET /api/v1/ml/recommendations`: Saran jumlah persiapan batch baking tim produksi dapur.
- `GET /api/v1/ml/model/metrics`: Metrik evaluasi aktual model (MAE, RMSE, WAPE) dan model registry.
- `GET /api/v1/ml/model/status`: Status kesehatan model dan audit data readiness.

### 3. Perintah PowerShell Eksekusi ML
```powershell
# Jalankan Training Manual (Multi-Model Training & Evaluation)
& ".venv\Scripts\python.exe" -m ml.training.train_runner

# Jalankan Batch Inference Manual (4 Output Bisnis)
& ".venv\Scripts\python.exe" -m ml.inference.batch_inference

# Jalankan Scheduler (Minggu 02:00 WIB Training, Tiap Hari 03:00 WIB Inference)
& ".venv\Scripts\python.exe" -m ml.scheduler --loop

# Jalankan Seluruh Test Suite (49 Tests Unit & Integrasi)
& ".venv\Scripts\pytest.exe" tests/ backend/tests/ -v
```
