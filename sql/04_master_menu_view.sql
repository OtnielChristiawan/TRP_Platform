-- ============================================================================
-- BAKERY DATA PLATFORM V4: BRONZE MASTER MENU SQL VIEW & SAMPLE QUERIES
-- ============================================================================
-- View ini membaca seluruh file snapshot Master Menu Parquet dari MinIO Bronze.
--
-- Persyaratan:
-- 1. Jalankan sql/00_setup_minio.sql terlebih dahulu untuk autentikasi ke MinIO.
-- 2. Pastikan batch master menu sudah pernah berjalan minimal 1 kali
--    (docker compose --profile batch run --rm master-menu-batch)
-- ============================================================================

-- 1. Definisi View bronze_master_menu
CREATE OR REPLACE VIEW bronze_master_menu AS
SELECT
    snapshot_id,
    snapshot_date,
    source_filename,
    source_file_hash,
    source_sheet,
    source_row_number,
    TRY_CAST(batch_ingested_at AS TIMESTAMPTZ) AS batch_ingested_at,
    batch_run_id,
    -- Kolom utama yang sudah diekstrak untuk kemudahan analisis
    menu_name,
    menu_code,
    category,
    category_detail,
    TRY_CAST(price AS DECIMAL(14, 2)) AS price,
    status,
    -- Seluruh baris asli dalam format JSON string dan struct
    raw_payload,
    source_row
FROM read_parquet(
    's3://bakery-bronze/master_menu/**/*.parquet',
    filename = false,
    hive_partitioning = false,
    union_by_name = true
);


-- ============================================================================
-- CONTOH QUERY ANALISIS & VALIDASI MASTER MENU
-- ============================================================================

-- A. Menampilkan 100 menu pertama dari Bronze Master Menu
SELECT *
FROM bronze_master_menu
LIMIT 100;

-- B. Menampilkan daftar snapshot yang tersedia dan jumlah menu per snapshot
SELECT
    snapshot_id,
    snapshot_date,
    source_filename,
    COUNT(*) AS total_menu_items,
    MIN(batch_ingested_at) AS ingested_at
FROM bronze_master_menu
GROUP BY snapshot_id, snapshot_date, source_filename
ORDER BY ingested_at DESC;

-- C. Mengakses seluruh 22 kolom sumber dari raw_payload JSON
SELECT
    menu_name,
    category,
    category_detail,
    raw_payload::json->>'Menu Short Name' AS menu_short_name,
    raw_payload::json->>'Bill of Material' AS bill_of_material,
    raw_payload::json->>'Estimated Cost' AS estimated_cost,
    raw_payload::json->>'Tax' AS tax,
    raw_payload::json->>'Customer Print' AS customer_print,
    raw_payload::json->>'Sales Account Number' AS sales_account_number,
    raw_payload::json->>'Status' AS status_raw
FROM bronze_master_menu
LIMIT 50;

-- D. Menghitung distribusi kategori menu pada snapshot terbaru
WITH latest_snapshot AS (
    SELECT snapshot_id
    FROM bronze_master_menu
    ORDER BY batch_ingested_at DESC
    LIMIT 1
)
SELECT
    category,
    COUNT(*) AS menu_count
FROM bronze_master_menu
WHERE snapshot_id = (SELECT snapshot_id FROM latest_snapshot)
GROUP BY category
ORDER BY menu_count DESC;
