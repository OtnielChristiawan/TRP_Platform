# Architecture Decision Records (ADR) & Resource Budget (F-19 & F-20 Compliance)
## Bakery Data Platform V4 — Toko Roti Pagi (TRP)
**Evaluation Standards:** Section 3.3, Functional Requirement F-19 (Profiling & Trade-offs), F-20 (Laporan Arsitektur)  

---

## 1. Resource Budget per Layanan (Kapasitas & Estimasi Pertumbuhan)

Tabel berikut mencatat alokasi dan konsumsi sumber daya aktual di lingkungan VM lokal:

| Service / Container | Alokasi CPU Core | Alokasi RAM (Limit) | Konsumsi RAM Aktual | Penggunaan Disk Awal | Estimasi Pertumbuhan Disk / Bulan |
|:---|:---:|:---:|:---:|:---:|:---:|
| **Redpanda Streaming Broker** | 1.0 vCPU | 1024 MB | ~280 MB | ~120 MB | ~450 MB / bulan |
| **MinIO Object Storage (S3)** | 1.0 vCPU | 1024 MB | ~110 MB | ~350 MB (Data Lake) | ~1.2 GB / bulan |
| **Spark Streaming (Bronze)** | 1.5 vCPU | 1536 MB | ~720 MB | ~80 MB (Ivy Checkpoints) | ~200 MB / bulan |
| **Silver & Gold Scheduler** | 1.0 vCPU | 1024 MB | ~450 MB (saat run) | ~50 MB (State SQLite) | ~80 MB / bulan |
| **FastAPI Backend (DuckDB)** | 1.0 vCPU | 1024 MB | ~45 MB | ~150 MB (DuckDB Ext) | ~50 MB / bulan |
| **React Frontend (Nginx)** | 0.5 vCPU | 256 MB | ~18 MB | ~40 MB | Static (0 MB / bulan) |
| **Redpanda Console UI** | 0.5 vCPU | 256 MB | ~42 MB | ~25 MB | Static (0 MB / bulan) |
| **TOTAL SISTEM** | **6.5 vCPU** | **6.1 GB RAM** | **~1.7 GB (Idle/Active)**| **~815 MB Initial** | **~2.03 GB / Bulan** |

> **Catatan Profil Lab:** Sistem ini dirancang untuk berjalan mulus pada **Profil A (Compact: 1 VM / Laptop 8 vCPU, RAM 8–16 GB)** tanpa membebani komputer.

---

## 2. ADR-01: Pemilihan Message Broker, Partisi, dan Delivery Semantics

* **Status:** APPROVED  
* **Konteks:** Sistem membutuhkan message broker lokal berkinerja tinggi untuk menerima ribuan transaksi kasir per menit dari mesin POS Toko Roti Pagi.
* **Keputusan:** Memilih **Redpanda** (kompatibel penuh dengan Apache Kafka API v26) dibanding Apache Kafka resmi atau RabbitMQ.
* **Alasan & Trade-off:**
  1. *Resource Footprint*: Redpanda ditulis dalam C++ (*thread-per-core* architecture) tanpa ketergantungan JVM / ZooKeeper, memangkas konsumsi RAM dari ~1.5 GB (Kafka standar) menjadi hanya ~280 MB.
  2. *Delivery Semantics*: Menggunakan strategi **At-Least-Once Delivery** dengan konfigurasi producer `acks=all`. Potensi duplikasi pesan saat replay ditangani secara deterministik di Silver layer melalui deduplikasi *business key* `(source_bill_num, payload_version, offset)`.
  3. *Partisi*: 1 partisi pada topic `bakery.transactions.v1` mencukupi untuk throughput demo lokal (100–500 msg/sec) dengan jaminan urutan pesan per transaksi.

---

## 3. ADR-02: Format Penyimpanan, Object Store, Table Format, dan Partisi

* **Status:** APPROVED  
* **Konteks:** Diperlukan format penyimpanan analitik yang efisien untuk volume transaksi besar, hemat disk, dan cepat dibaca oleh DuckDB.
* **Keputusan:** Menggunakan **Apache Parquet (Snappy)** di atas **MinIO Object Storage** dengan mekanisme snapshot atomik berbasis **Manifest Metadata (`current_manifest.json`)**.
* **Alasan & Trade-off:**
  1. *Efisiensi Parquet*: Format kolumnar Parquet menghasilkan kompresi disk hingga **74% lebih hemat** dibandingkan raw JSON/CSV, serta mendukung *column projection* (DuckDB hanya membaca kolom yang di-select).
  2. *Alternative Table Format*: Mengingat batasan hardware lokal, alih-alih memasang engine berat seperti Apache Iceberg atau Delta Lake yang membutuhkan catalog service tambahan, kami menerapkan **Atomic Manifest Versioning**: Setiap batch commit menerbitkan snapshot ID baru ke SQLite dan MinIO metadata.
  3. *Partition Key*: Partisi menggunakan `sales_date` (`YYYY-MM-DD`). Ini membatasi scan I/O DuckDB hanya ke rentang tanggal yang dipilih di filter dashboard.
  4. *Retensi*: Bronze (180 hari raw audit), Silver (365 hari active), Gold (Permanen untuk analisis tren multi-tahun).

---

## 4. ADR-03: Pemilihan Batch & Stream Processor serta Limit Sumber Daya

* **Status:** APPROVED  
* **Konteks:** Platform memerlukan mesin komputasi terdistribusi yang mampu menangani streaming transaksi real-time sekaligus batch cleansing dan agregasi berkala.
* **Keputusan:** Menggunakan **Apache Spark 3.5.5** (PySpark) untuk Structured Streaming dan Batch Jobs.
* **Alasan & Trade-off:**
  1. *Stream Processing*: Spark Structured Streaming menyediakan dukungan *Event-Time Watermark* bawaan (`withWatermark("event_time", "1 hour")`), menangani transaksi kasir yang terlambat masuk secara otomatis.
  2. *Unified Engine*: Engine yang sama digunakan untuk streaming Bronze dan batch Silver/Gold, mengurangi kompleksitas teknologi tim.
  3. *Resource Limits*: Spark driver dibatasi memori heap `1024 MB` dengan non-interactive scheduled batches (Silver berjalan tiap 10 menit, Gold tiap 20 menit) agar CPU laptop tidak terbebani secara terus-menerus.

---

## 5. ADR-04: Metode Inferensi Machine Learning & Pemilihan Model Baseline

* **Status:** APPROVED  
* **Konteks:** Manajemen Toko Roti Pagi memerlukan estimasi kebutuhan stok dan jumlah pemanggangan roti harian untuk meminimalkan *food waste*.
* **Keputusan:** Memilih **Scheduled Batch Inference Harian (H+1)** dengan promosi model **Naive Previous-Day Baseline** didampingi kandidat model regresi ML (*Ridge Regression* & *Random Forest*).
* **Alasan & Trade-off:**
  1. *Batch Inference vs Online API*: Toko roti merencanakan adonan dan memanggang roti pada subuh hari sebelum toko buka (bukan real-time per detik transaksi). Batch inference harian jauh lebih hemat biaya komputasi, stabil, dan prediksinya dapat langsung disimpan di Parquet untuk konsumsi cepat dashboard.
  2. *Model Baseline Selection*: Pada pengujian test set holdout riil tanggal 19 Oktober 2026, **Naive Previous-Day Baseline mencatat MAE terendah (6.70)** dibandingkan Ridge Regression (7.12) dan Random Forest (7.37) karena data historis masih pendek (2 hari). Sesuai prinsip MLOps yang sehat, model dengan error terendahlah yang dipromosikan ke status *Active (Provisional)*, sementara model machine learning disiapkan untuk retraining saat data historis telah mencapai 30+ hari.
  3. *Keamanan Endpoint*: Seluruh akses prediksi ML dilindungi oleh peran autentikasi RBAC (Viewer/Operator/Admin).

---

## 6. ADR-05: Rencana Recovery, Backup, dan Toleransi Kegagalan

* **Status:** APPROVED  
* **Konteks:** Sistem harus memiliki jaminan keberlanjutan bisnis jika terjadi crash pada salah satu komponen infrastruktur lokal.
* **Keputusan:** Menerapkan strategi backup snapshot biner (`.tar.gz`) bersertifikat hash SHA-256 dan isolasi status toleransi kegagalan.
* **Toleransi Kegagalan:**
  1. *Kegagalan yang DAPAT Ditoleransi (Fault-Tolerant)*:
     - **Broker Redpanda Restart**: Pesan tertahan di buffer producer, setelah restart pesan pending langsung dialirkan kembali.
     - **Spark Streaming Restart**: Konsumsi stream otomatis melanjutkan dari offset terakhir yang tercatat di MinIO checkpoint (`spark_checkpoints`).
     - **Transaksi Terlambat Masuk**: Watermark 1 jam mengakomodasi transaksi offline yang baru tersinkronisasi.
     - **Rerun Batch**: Idempotent execution menjamin rerun tidak menimbulkan duplikasi faktur di Silver maupun Gold.
  2. *Kegagalan yang TIDAK DAPAT Ditoleransi (Memerlukan Restore/Intervensi)*:
     - **Silent Data Corruption pada Disk SQLite**: Terdeteksi melalui mismatch hash SHA-256 dan dipulihkan via `scripts/restore_state.py`.
     - **Korupsi Parquet Header**: Terdeteksi oleh Data Quality Gate F-08 dan memicu penolakan publish snapshot ke Gold mart.
