-- ============================================================================
-- BAKERY DATA PLATFORM V4: SILVER LAYER DUCKDB VIEWS & ANALYTICS
-- ============================================================================
-- Skrip ini mendefinisikan views untuk membaca Silver Layer langsung dari MinIO.
-- Persyaratan:
-- 1. Jalankan sql/00_setup_minio.sql terlebih dahulu untuk autentikasi ke MinIO.
-- 2. Pastikan batch Silver sudah dijalankan minimal 1 kali:
--    docker compose --profile silver run --rm silver-batch
-- ============================================================================

-- 1. View: silver_sales_bills
-- Grain: 1 baris per bill/transaksi penjualan
-- Kolom Table Section, Table Name, Area, dan data pribadi (PII) sudah dihilangkan.
CREATE OR REPLACE VIEW silver_sales_bills AS
SELECT
    event_id,
    sales_number,
    bill_number,
    sales_type,
    batch_order,
    sales_date,
    TRY_CAST(sales_date_in AS TIMESTAMPTZ) AS sales_date_in,
    TRY_CAST(sales_date_out AS TIMESTAMPTZ) AS sales_date_out,
    TRY_CAST(event_time AS TIMESTAMPTZ) AS event_time,
    branch,
    brand,
    city,
    visit_purpose,
    payment_method,
    regular_member_code,
    loyalty_member_code,
    loyalty_member_type,
    employee_code,
    waiter,
    total_items,
    TRY_CAST(total_qty AS DECIMAL(12, 2)) AS total_qty,
    TRY_CAST(bill_subtotal AS DECIMAL(14, 2)) AS bill_subtotal,
    TRY_CAST(bill_discount AS DECIMAL(14, 2)) AS bill_discount,
    TRY_CAST(bill_service_charge AS DECIMAL(14, 2)) AS bill_service_charge,
    TRY_CAST(bill_tax AS DECIMAL(14, 2)) AS bill_tax,
    TRY_CAST(bill_vat AS DECIMAL(14, 2)) AS bill_vat,
    TRY_CAST(bill_total AS DECIMAL(14, 2)) AS bill_total,
    TRY_CAST(bill_nett_sales AS DECIMAL(14, 2)) AS bill_nett_sales,
    TRY_CAST(bill_dpp AS DECIMAL(14, 2)) AS bill_dpp,
    TRY_CAST(bill_total_after_discount AS DECIMAL(14, 2)) AS bill_total_after_discount,
    has_zero_price_item,
    payload_version,
    source_filename,
    bronze_offset,
    TRY_CAST(bronze_ingested_at AS TIMESTAMPTZ) AS bronze_ingested_at,
    TRY_CAST(silver_ingested_at AS TIMESTAMPTZ) AS silver_ingested_at,
    batch_run_id,
    dq_status
FROM read_parquet(
    's3://bakery-silver/sales_bills/**/*.parquet',
    hive_partitioning = true,
    union_by_name = true
);


-- 2. View: silver_sales_items
-- Grain: 1 baris per item menu yang terjual
-- Seluruh angka uang sudah dinormalisasi ke DECIMAL, dan flag is_zero_price tersedia.
CREATE OR REPLACE VIEW silver_sales_items AS
SELECT
    item_id,
    event_id,
    sales_number,
    bill_number,
    item_index,
    source_row_number,
    sales_date,
    TRY_CAST(sales_date_out AS TIMESTAMPTZ) AS sales_date_out,
    TRY_CAST(order_time AS TIMESTAMPTZ) AS order_time,
    branch,
    brand,
    payment_method,
    menu_category,
    menu_category_detail,
    menu,
    custom_menu_name,
    menu_code,
    menu_notes,
    order_mode,
    TRY_CAST(qty AS DECIMAL(12, 2)) AS qty,
    TRY_CAST(price AS DECIMAL(14, 2)) AS price,
    TRY_CAST(subtotal AS DECIMAL(14, 2)) AS subtotal,
    TRY_CAST(discount AS DECIMAL(14, 2)) AS discount,
    TRY_CAST(service_charge AS DECIMAL(14, 2)) AS service_charge,
    TRY_CAST(tax AS DECIMAL(14, 2)) AS tax,
    TRY_CAST(vat AS DECIMAL(14, 2)) AS vat,
    TRY_CAST(total AS DECIMAL(14, 2)) AS total,
    TRY_CAST(nett_sales AS DECIMAL(14, 2)) AS nett_sales,
    TRY_CAST(dpp AS DECIMAL(14, 2)) AS dpp,
    TRY_CAST(bill_discount AS DECIMAL(14, 2)) AS bill_discount,
    TRY_CAST(total_after_bill_discount AS DECIMAL(14, 2)) AS total_after_bill_discount,
    is_zero_price,
    source_filename,
    TRY_CAST(silver_ingested_at AS TIMESTAMPTZ) AS silver_ingested_at,
    batch_run_id
FROM read_parquet(
    's3://bakery-silver/sales_items/**/*.parquet',
    hive_partitioning = true,
    union_by_name = true
);


-- 3. View: silver_master_menu
-- Master produk yang telah dinormalisasi dari snapshot Bronze
CREATE OR REPLACE VIEW silver_master_menu AS
SELECT
    menu_code,
    menu_name,
    category,
    category_detail,
    TRY_CAST(price AS DECIMAL(14, 2)) AS price,
    status,
    is_active,
    snapshot_id,
    snapshot_date,
    source_filename,
    source_file_hash,
    source_sheet,
    source_row_number,
    TRY_CAST(silver_ingested_at AS TIMESTAMPTZ) AS silver_ingested_at,
    batch_run_id
FROM read_parquet(
    's3://bakery-silver/master_menu/**/*.parquet',
    hive_partitioning = true,
    union_by_name = true
);


-- 4. View: silver_data_quality
-- Laporan metrik kualitas data tiap eksekusi batch incremental
CREATE OR REPLACE VIEW silver_data_quality AS
SELECT
    batch_id,
    TRY_CAST(batch_timestamp AS TIMESTAMPTZ) AS batch_timestamp,
    bronze_records,
    silver_bills,
    silver_items,
    zero_price_items,
    v1_count,
    v2_count,
    master_menu_records,
    status
FROM read_parquet(
    's3://bakery-silver/data_quality/**/*.parquet',
    hive_partitioning = false,
    union_by_name = true
);


-- ============================================================================
-- CONTOH QUERY VERIFIKASI & ANALISIS BISNIS (SESUAI SPESIFIKASI)
-- ============================================================================

-- A. Menampilkan 100 baris item penjualan pertama
SELECT *
FROM silver_sales_items
LIMIT 100;

-- B. Agregasi Menu terlaris berdasarkan total kuantitas dan total nett sales
-- Menggunakan nilai numerik murni DECIMAL (bukan string Rupiah)
SELECT
    menu,
    SUM(qty) AS total_qty,
    SUM(nett_sales) AS total_nett_sales
FROM silver_sales_items
GROUP BY menu
ORDER BY total_qty DESC;

-- C. Menampilkan 100 transaksi (bills) terbaru
SELECT
    sales_number,
    bill_number,
    sales_date,
    branch,
    payment_method,
    total_items,
    total_qty,
    bill_nett_sales,
    has_zero_price_item
FROM silver_sales_bills
ORDER BY sales_date DESC, event_time DESC
LIMIT 100;

-- D. Pemeriksaan item dengan harga 0 (zero-price / promosi)
SELECT
    bill_number,
    menu,
    qty,
    price,
    total,
    is_zero_price,
    sales_date
FROM silver_sales_items
WHERE is_zero_price = true
LIMIT 50;

-- E. Riwayat eksekusi batch dan audit kualitas data
SELECT *
FROM silver_data_quality
ORDER BY batch_timestamp DESC;
