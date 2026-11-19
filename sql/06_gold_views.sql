-- ============================================================================
-- BAKERY DATA PLATFORM V4: GOLD LAYER DUCKDB VIEWS & ANALYTICS
-- ============================================================================
-- Skrip ini mendefinisikan view analitik siap pakai untuk DBeaver / DuckDB / FastAPI
-- yang membaca langsung Parquet Gold Data Marts dari MinIO (s3://bakery-gold/).
--
-- Prasyarat:
-- 1. Jalankan sql/00_setup_minio.sql terlebih dahulu untuk inisialisasi credential S3/MinIO.
-- 2. Pastikan batch Gold sudah dijalankan minimal 1 kali:
--    docker compose --profile gold run --rm gold-batch
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. View: gold_sales_daily
-- Grain: (sales_date, branch)
-- KPI Utama: Total Bills, Net Sales, Gross Sales, AOV, Qty, Zero Price Items
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW gold_sales_daily AS
SELECT
    sales_date,
    branch,
    TRY_CAST(total_bills AS BIGINT) AS total_bills,
    TRY_CAST(total_item_rows AS BIGINT) AS total_item_rows,
    TRY_CAST(total_qty_sold AS DECIMAL(12, 2)) AS total_qty_sold,
    TRY_CAST(gross_sales AS DECIMAL(14, 2)) AS gross_sales,
    TRY_CAST(total_discount AS DECIMAL(14, 2)) AS total_discount,
    TRY_CAST(net_sales AS DECIMAL(14, 2)) AS net_sales,
    TRY_CAST(average_order_value AS DECIMAL(14, 2)) AS average_order_value,
    TRY_CAST(zero_price_item_count AS BIGINT) AS zero_price_item_count,
    batch_run_id,
    TRY_CAST(last_updated_at AS TIMESTAMPTZ) AS last_updated_at
FROM read_parquet(
    's3://bakery-gold/gold_sales_daily/**/*.parquet',
    hive_partitioning = true,
    union_by_name = true
);


-- ----------------------------------------------------------------------------
-- 2. View: gold_sales_hourly
-- Grain: (sales_date, sales_hour, branch)
-- Menggunakan sales_date_out (waktu transaksi selesai) untuk distribusi jam asli.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW gold_sales_hourly AS
SELECT
    sales_date,
    TRY_CAST(sales_hour AS INTEGER) AS sales_hour,
    branch,
    TRY_CAST(total_bills AS BIGINT) AS total_bills,
    TRY_CAST(total_item_rows AS BIGINT) AS total_item_rows,
    TRY_CAST(total_qty_sold AS DECIMAL(12, 2)) AS total_qty_sold,
    TRY_CAST(gross_sales AS DECIMAL(14, 2)) AS gross_sales,
    TRY_CAST(total_discount AS DECIMAL(14, 2)) AS total_discount,
    TRY_CAST(net_sales AS DECIMAL(14, 2)) AS net_sales,
    TRY_CAST(average_order_value AS DECIMAL(14, 2)) AS average_order_value,
    batch_run_id,
    TRY_CAST(last_updated_at AS TIMESTAMPTZ) AS last_updated_at
FROM read_parquet(
    's3://bakery-gold/gold_sales_hourly/**/*.parquet',
    hive_partitioning = true,
    union_by_name = true
);


-- ----------------------------------------------------------------------------
-- 3. View: gold_menu_performance_daily
-- Grain: (sales_date, branch, menu_key)
-- Top seller, low seller, revenue menu, dan status rekonsiliasi Master Menu.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW gold_menu_performance_daily AS
SELECT
    sales_date,
    branch,
    menu_key,
    menu_name,
    menu_category,
    menu_category_detail,
    TRY_CAST(qty_sold AS DECIMAL(12, 2)) AS qty_sold,
    TRY_CAST(total_bills AS BIGINT) AS total_bills,
    TRY_CAST(gross_sales AS DECIMAL(14, 2)) AS gross_sales,
    TRY_CAST(net_sales AS DECIMAL(14, 2)) AS net_sales,
    TRY_CAST(zero_price_qty AS DECIMAL(12, 2)) AS zero_price_qty,
    master_menu_code,
    TRY_CAST(master_standard_price AS DECIMAL(14, 2)) AS master_standard_price,
    is_active,
    is_master_matched,
    master_match_status,
    batch_run_id,
    TRY_CAST(last_updated_at AS TIMESTAMPTZ) AS last_updated_at
FROM read_parquet(
    's3://bakery-gold/gold_menu_performance_daily/**/*.parquet',
    hive_partitioning = true,
    union_by_name = true
);


-- ----------------------------------------------------------------------------
-- 4. View: gold_category_performance_daily
-- Grain: (sales_date, branch, menu_category)
-- Kontribusi penjualan per kategori produk (Beverage, Pastry, dll.)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW gold_category_performance_daily AS
SELECT
    sales_date,
    branch,
    menu_category,
    TRY_CAST(qty_sold AS DECIMAL(12, 2)) AS qty_sold,
    TRY_CAST(total_bills AS BIGINT) AS total_bills,
    TRY_CAST(total_item_rows AS BIGINT) AS total_item_rows,
    TRY_CAST(gross_sales AS DECIMAL(14, 2)) AS gross_sales,
    TRY_CAST(net_sales AS DECIMAL(14, 2)) AS net_sales,
    TRY_CAST(sales_contribution_pct AS DECIMAL(6, 2)) AS sales_contribution_pct,
    batch_run_id,
    TRY_CAST(last_updated_at AS TIMESTAMPTZ) AS last_updated_at
FROM read_parquet(
    's3://bakery-gold/gold_category_performance_daily/**/*.parquet',
    hive_partitioning = true,
    union_by_name = true
);


-- ----------------------------------------------------------------------------
-- 5. View: gold_payment_daily
-- Grain: (sales_date, branch, payment_method)
-- Dihitung dari bill grain untuk menghindari penggandaan nilai transaksi.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW gold_payment_daily AS
SELECT
    sales_date,
    branch,
    payment_method,
    TRY_CAST(total_bills AS BIGINT) AS total_bills,
    TRY_CAST(net_sales AS DECIMAL(14, 2)) AS net_sales,
    TRY_CAST(payment_contribution_pct AS DECIMAL(6, 2)) AS payment_contribution_pct,
    batch_run_id,
    TRY_CAST(last_updated_at AS TIMESTAMPTZ) AS last_updated_at
FROM read_parquet(
    's3://bakery-gold/gold_payment_daily/**/*.parquet',
    hive_partitioning = true,
    union_by_name = true
);


-- ----------------------------------------------------------------------------
-- 6. View: gold_ml_demand_features
-- Grain: (sales_date, branch, menu_key)
-- Fitur Machine Learning untuk demand forecasting (lags & rolling tanpa leakage).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW gold_ml_demand_features AS
SELECT
    sales_date,
    branch,
    menu_key,
    menu_name,
    menu_category,
    TRY_CAST(qty_sold AS DECIMAL(12, 2)) AS qty_sold,
    TRY_CAST(day_of_week AS INTEGER) AS day_of_week,
    TRY_CAST(day_of_month AS INTEGER) AS day_of_month,
    TRY_CAST(month AS INTEGER) AS month,
    is_weekend,
    TRY_CAST(lag_1_qty AS DECIMAL(12, 2)) AS lag_1_qty,
    TRY_CAST(lag_7_qty AS DECIMAL(12, 2)) AS lag_7_qty,
    TRY_CAST(rolling_avg_7d_qty AS DECIMAL(12, 2)) AS rolling_avg_7d_qty,
    batch_run_id,
    TRY_CAST(last_updated_at AS TIMESTAMPTZ) AS last_updated_at
FROM read_parquet(
    's3://bakery-gold/gold_ml_demand_features/**/*.parquet',
    hive_partitioning = true,
    union_by_name = true
);


-- ============================================================================
-- CONTOH KUERI ANALITIK & MONITORING (BUSINESS-READY)
-- ============================================================================

-- Q1: Ringkasan Eksekutif Penjualan Harian (Executive Daily Summary)
-- SELECT
--     sales_date,
--     branch,
--     total_bills,
--     total_qty_sold,
--     net_sales,
--     average_order_value,
--     zero_price_item_count
-- FROM gold_sales_daily
-- ORDER BY sales_date DESC, branch;

-- Q2: Jam Sibuk Penjualan (Peak Sales Hours Pattern)
-- SELECT
--     sales_hour,
--     SUM(total_bills) AS total_bills,
--     SUM(total_qty_sold) AS total_qty_sold,
--     SUM(net_sales) AS total_net_sales,
--     ROUND(AVG(average_order_value), 2) AS avg_aov
-- FROM gold_sales_hourly
-- GROUP BY sales_hour
-- ORDER BY total_net_sales DESC;

-- Q3: Top 10 Menu Terlaris Berdasarkan Pendapatan
-- SELECT
--     menu_name,
--     menu_category,
--     SUM(qty_sold) AS total_qty,
--     SUM(total_bills) AS bill_occurrences,
--     SUM(net_sales) AS total_revenue,
--     master_match_status
-- FROM gold_menu_performance_daily
-- GROUP BY menu_name, menu_category, master_match_status
-- ORDER BY total_revenue DESC
-- LIMIT 10;

-- Q4: Kontribusi Penjualan per Kategori Produk
-- SELECT
--     sales_date,
--     menu_category,
--     qty_sold,
--     net_sales,
--     sales_contribution_pct
-- FROM gold_category_performance_daily
-- ORDER BY sales_date DESC, net_sales DESC;

-- Q5: Distribusi Metode Pembayaran
-- SELECT
--     payment_method,
--     SUM(total_bills) AS total_bills,
--     SUM(net_sales) AS total_volume,
--     ROUND(SUM(net_sales) * 100.0 / (SELECT SUM(net_sales) FROM gold_payment_daily), 2) AS overall_pct
-- FROM gold_payment_daily
-- GROUP BY payment_method
-- ORDER BY total_volume DESC;

-- Q6: Rekonsiliasi Finansial Antar-Mart (Cross-Mart Financial Reconciliation Check)
-- SELECT
--     d.sales_date,
--     d.net_sales AS daily_net_sales,
--     h.hourly_net_sales,
--     c.category_net_sales,
--     p.payment_net_sales,
--     (d.net_sales - h.hourly_net_sales) AS diff_daily_hourly,
--     (d.net_sales - c.category_net_sales) AS diff_daily_category,
--     (d.net_sales - p.payment_net_sales) AS diff_daily_payment
-- FROM gold_sales_daily d
-- JOIN (SELECT sales_date, SUM(net_sales) AS hourly_net_sales FROM gold_sales_hourly GROUP BY sales_date) h
--   ON d.sales_date = h.sales_date
-- JOIN (SELECT sales_date, SUM(net_sales) AS category_net_sales FROM gold_category_performance_daily GROUP BY sales_date) c
--   ON d.sales_date = c.sales_date
-- JOIN (SELECT sales_date, SUM(net_sales) AS payment_net_sales FROM gold_payment_daily GROUP BY sales_date) p
--   ON d.sales_date = p.sales_date
-- ORDER BY d.sales_date;
