# Enterprise Data Catalog & Schema Dictionary (F-09 Compliance)
## Bakery Data Platform V4 — Toko Roti Pagi (TRP)
**Standard:** Functional Requirement F-09 (Metadata, Ownership, Lineage)  
**Governance Framework:** Medallion Data Architecture (Bronze -> Silver -> Gold -> ML)  
**Classification Standard:** Internal Retail Enterprise  

---

## 1. Metadata Governance Policy

| Aspek Tata Kelola | Kebijakan Platform |
|:---|:---|
| **Data Owner** | Head of Retail Operations & Data Platform Engineering Toko Roti Pagi |
| **Data Classification** | **CONFIDENTIAL (Sales & Financial Records)**; **INTERNAL (Menu & Operations)** |
| **Storage Architecture** | On-Premise MinIO Object Storage (S3-Compatible) + Apache Parquet (Snappy) |
| **Retention Policy** | Bronze (180 Hari Raw Archive); Silver (365 Hari Active); Gold (Permanen / Indefinite Marts) |
| **Refresh Frequency** | Streaming (10s Micro-batch); Silver (Tiap 10 Menit); Gold (Tiap 20 Menit); ML (Daily H+1) |

---

## 2. Data Dictionary per Lapisan Medallion

### 2.1 Bronze Layer (`s3://bakery-bronze/`)
* **`transactions/`**: Raw JSON streaming messages dari broker Redpanda.
  - `event_id` (STRING): Unique UUID event stream.
  - `event_time` (TIMESTAMP): Waktu transaksi asli dari kasir POS.
  - `ingest_time` (TIMESTAMP): Waktu penulisan ke MinIO Bronze.
  - `payload_version` (INT): Versi skema pesan (v1, v2).
  - `raw_payload` (STRING): Full unparsed JSON blob transaksi kasir.

### 2.2 Silver Layer (`s3://bakery-silver/`)
* **`sales_bills/`**: Data faktur penjualan yang telah dinormalisasi dan dideduplikasi (*Grain: 1 baris per faktur*).
  - `source_bill_num` (STRING, PK): Nomor faktur unik nota kasir (misal `TRPG202610180001`).
  - `branch` (STRING): Nama cabang toko roti (misal `GWalk Surabaya`).
  - `sales_date` (DATE, Partition Key): Tanggal transaksi asli (`YYYY-MM-DD`).
  - `sales_time` (TIMESTAMP): Timestamp lengkap transaksi.
  - `payment_method` (STRING): Metode pembayaran (`QRIS`, `CASH`, `DEBIT`, `TRANSFER`).
  - `total_bill_gross` (DECIMAL(12,2)): Total kotor nota sebelum diskon.
  - `total_bill_discount` (DECIMAL(12,2)): Total potongan diskon nota.
  - `total_bill_net` (DECIMAL(12,2)): Total bersih yang dibayar pelanggan.

* **`sales_items/`**: Rincian item menu dalam setiap faktur (*Grain: 1 baris per item nota*).
  - `item_line_id` (STRING, PK): Kombinasi `source_bill_num_seq`.
  - `source_bill_num` (STRING, FK): Foreign key ke `sales_bills`.
  - `menu_key` (STRING): Identitas unik produk menu.
  - `menu_name` (STRING): Nama roti/minuman (misal `Original Salt Bread`).
  - `category` (STRING): Kategori produk (`Bread`, `Cake`, `Beverage`, `Pastry`).
  - `qty` (INT): Kuantitas item yang dibeli.
  - `sales_price_gross` (DECIMAL(12,2)): Harga kotor per satuan item.
  - `sales_price_net` (DECIMAL(12,2)): Harga bersih setelah diskon item.

### 2.3 Gold Layer (`s3://bakery-gold/`)
Analytical Data Marts siap saji untuk konsumsi dashboard dan DuckDB:

| Nama Mart | Grain | Partition Key | Matriks Metrik Utama |
|:---|:---|:---:|:---|
| **`gold_sales_daily`** | 1 baris per tanggal per cabang | `sales_date` | `total_bills`, `total_qty_sold`, `gross_sales`, `total_discount`, `net_sales`, `aov` (Average Order Value) |
| **`gold_sales_hourly`** | 1 baris per tanggal per cabang per jam | `sales_date` | `sales_hour` (0-23), `total_bills`, `total_qty_sold`, `net_sales` |
| **`gold_menu_performance_daily`** | 1 baris per tanggal per menu | `sales_date` | `menu_key`, `menu_name`, `category`, `total_qty_sold`, `net_sales`, `contribution_pct` |
| **`gold_category_performance_daily`** | 1 baris per tanggal per kategori | `sales_date` | `category`, `total_qty_sold`, `net_sales`, `contribution_pct` |
| **`gold_payment_daily`** | 1 baris per tanggal per payment method | `sales_date` | `payment_method`, `total_transactions`, `total_amount`, `share_pct` |

### 2.4 ML Layer (`state/ml/predictions/latest/`)
* **`ml_forecast_product_daily`**: Proyeksi demand per menu H+1 untuk Toko Roti Pagi.
* **`ml_forecast_next_7_days`**: Proyeksi total penjualan harian 7 hari ke depan.
* **`ml_forecast_hourly`**: Profil estimasi lonjakan transaksi per jam operasional (07:00 - 21:00).
* **`ml_production_recommendations`**: Rekomendasi kuantitas batch pemanggangan roti dengan safety buffer kebijakan toko.
