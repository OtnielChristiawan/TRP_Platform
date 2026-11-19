# Panduan Integrasi DuckDB + DBeaver untuk Bakery Data Platform V4

Panduan ini menjelaskan cara menghubungkan **DBeaver Community di Windows** ke dataset Parquet di **MinIO** menggunakan query engine **DuckDB** via JDBC lokal.

Dengan setup ini, Anda dapat menjalankan query SQL langsung ke dataset Parquet MinIO dan melihat hasilnya dalam bentuk grid tabel di DBeaver, tanpa perlu menulis script Python terminal atau mengekspor CSV.

---

## 1. Persiapan DBeaver & DuckDB di Windows

### Jika DBeaver Belum Terpasang:
1. Unduh installer **DBeaver Community** untuk Windows dari situs resmi: [https://dbeaver.io/download/](https://dbeaver.io/download/)
2. Jalankan file `.exe` installer (pilih opsi default *Standard Installation*).
3. Buka aplikasi DBeaver.

---

## 2. Membuat Koneksi DuckDB di DBeaver (Langkah per Langkah)

1. **Buka DBeaver** di Windows Anda.
2. Di menu bar atas, klik **Database** > **New Database Connection** (atau klik ikon colokan listrik dengan tanda tambah di toolbar kiri atas).
3. Di kotak pencarian driver, ketik: `DuckDB` lalu pilih icon **DuckDB** dan klik **Next**.
4. Di jendela **Connection Settings**:
   - **Path**: Biarkan kosong atau isi `:memory:` untuk koneksi in-memory. Jika ingin views Anda tersimpan permanen di file lokal, Anda bisa mengarahkan path ke file lokal, misalnya:
     `C:\Users\asus Pc\Documents\3.Kuliah\Semester 5\Desain Aplikasi Big Data\Projek\bakery-data-platform-v4\state\bakery_explorer.duckdb`
   - Klik tombol **Driver Properties** atau langsung klik **Test Connection**.
   - *Catatan Driver*: Saat pertama kali klik *Test Connection*, DBeaver akan otomatis menawarkan untuk mendownload driver JDBC DuckDB resmi. Klik **Download** dan tunggu hingga selesai (hanya butuh beberapa detik).
5. Klik **Finish**. Koneksi DuckDB sekarang muncul di panel **Database Navigator** di sebelah kiri.

---

## 3. Menghubungkan DuckDB ke MinIO

1. Di panel *Database Navigator*, klik kanan pada koneksi DuckDB yang baru dibuat, lalu pilih **SQL Editor** > **Open SQL Console** (atau tekan `F3`).
2. Buka file [sql/00_setup_minio.sql](file:///c:/Users/asus%20Pc/Documents/3.Kuliah/Semester%205/Desain%20Aplikasi%20Big%20Data/Projek/bakery-data-platform-v4/sql/00_setup_minio.sql).
3. Copy isi skrip tersebut dan paste ke SQL Editor DBeaver, lalu tekan tombol **Execute SQL Script** (ikon panah ganda kuning atau `Alt + X`).
4. Ekstensi `httpfs` akan dimuat dan secret MinIO (`localhost:9000`) akan diinisialisasi.

---

## 4. Mendaftarkan SQL Views Bronze

1. Buka file [sql/01_bronze_views.sql](file:///c:/Users/asus%20Pc/Documents/3.Kuliah/Semester%205/Desain%20Aplikasi%20Big%20Data/Projek/bakery-data-platform-v4/sql/01_bronze_views.sql).
2. Copy seluruh isinya ke SQL Editor DBeaver, lalu eksekusi (`Alt + X`).
3. Ini akan membuat views dinamis:
   - `bronze_transactions_raw` (seluruh payload dan metadata Kafka)
   - `bronze_transactions` (ringkasan per bill/transaksi)
   - `bronze_transaction_items` (rincian item menu per baris transaksi)

---

## 5. Menjalankan Query Eksplorasi & Validasi

Buka file [sql/02_validation_queries.sql](file:///c:/Users/asus%20Pc/Documents/3.Kuliah/Semester%205/Desain%20Aplikasi%20Big%20Data/Projek/bakery-data-platform-v4/sql/02_validation_queries.sql) yang berisi 10 query validasi siap pakai.

Contoh query utama:
```sql
SELECT *
FROM bronze_transaction_items
ORDER BY event_time ASC
LIMIT 100;
```
Arahkan kursor pada query tersebut lalu tekan `Ctrl + Enter`. Hasil data Toko Roti Pagi akan langsung muncul dalam grid tabel interaktif di DBeaver!

---

## 6. Cara Menambahkan Views untuk Silver & Gold di Masa Depan

Arsitektur view dinamis ini sangat fleksibel. Ketika Anda nantinya menambahkan layer Silver dan Gold:

1. **Layer Silver (Cleaned & Enriched)**:
   Buat file baru, misalnya `sql/03_silver_views.sql`:
   ```sql
   CREATE OR REPLACE VIEW silver_transactions AS
   SELECT 
       sales_number,
       bill_number,
       branch,
       event_time,
       kafka_offset
   FROM read_parquet('s3://bakery-silver/transactions/*/*.parquet');
   ```

2. **Layer Gold (Aggregated / Marts)**:
   Buat file baru, misalnya `sql/04_gold_views.sql`:
   ```sql
   CREATE OR REPLACE VIEW gold_daily_sales AS
   SELECT 
       date_trunc('day', event_time) AS sales_date,
       category,
       SUM(qty) AS total_qty,
       SUM(qty * price) AS total_revenue
   FROM bronze_transaction_items
   GROUP BY 1, 2;
   ```
3. Eksekusi skrip tersebut di DBeaver, dan layer baru Anda langsung dapat di-query.
