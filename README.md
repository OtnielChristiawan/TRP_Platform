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
docker compose --profile batch run --rm master-menu-batch
```

8. **Opsional: aktifkan batch otomatis setiap hari pukul 06:00 WIB**:

```powershell
docker compose --profile scheduler up -d master-menu-scheduler
```

Gunakan salah satu atau keduanya sesuai tujuan. Batch memeriksa checksum file, menyimpan snapshot baru hanya untuk **konten baru**. Jika ada file master baru besok, tambahkan ke folder; job 06:00 berikutnya akan memprosesnya. Jika tidak ada perubahan, tidak menulis snapshot duplikat.

9. Console:
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
