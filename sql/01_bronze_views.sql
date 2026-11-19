-- ============================================================================
-- BAKERY DATA PLATFORM V4: BRONZE SQL VIEWS
-- ============================================================================
-- Views ini membaca file Parquet langsung dari MinIO secara dinamis.
-- Setiap kali ada data baru yang masuk dari Spark Streaming, query otomatis
-- menyertakan data terbaru tanpa perlu import ulang.
-- ============================================================================

-- 1. View: bronze_transactions_raw
-- Membaca seluruh kolom mentah dari Parquet transaksi Bronze
-- Pola glob **/*.parquet mencakup baik root transaksi maupun subpartisi
CREATE OR REPLACE VIEW bronze_transactions_raw AS
SELECT
    event_id,
    bill_number,
    event_time,
    kafka_timestamp,
    bronze_ingested_at,
    topic,
    "partition",
    "offset",
    raw_payload
FROM read_parquet(
    's3://bakery-bronze/transactions/**/*.parquet',
    filename = false,
    hive_partitioning = false
);


-- 2. View: bronze_transactions
-- Mem-parsing JSON raw_payload untuk menyajikan data tingkat nota/bill
CREATE OR REPLACE VIEW bronze_transactions AS
SELECT
    raw_payload::json->>'sales_number' AS sales_number,
    bill_number,
    raw_payload::json->>'branch' AS branch,
    TRY_CAST(event_time AS TIMESTAMPTZ) AS event_time,
    TRY_CAST(raw_payload::json->>'replay_scheduled_at' AS TIMESTAMPTZ) AS replay_scheduled_at,
    TRY_CAST(raw_payload::json->>'producer_sent_at' AS TIMESTAMPTZ) AS producer_sent_at,
    bronze_ingested_at,
    event_id,
    "offset" AS kafka_offset,
    kafka_timestamp,
    topic,
    "partition"
FROM bronze_transactions_raw;


-- 3. View: bronze_transaction_items
-- Memecah (unnest) array items dari tiap transaksi menjadi baris per item menu
CREATE OR REPLACE VIEW bronze_transaction_items AS
SELECT
    raw_payload::json->>'sales_number' AS sales_number,
    bill_number,
    TRY_CAST(event_time AS TIMESTAMPTZ) AS event_time,
    item->>'menu' AS menu,
    item->>'category' AS category,
    item->>'category_detail' AS category_detail,
    TRY_CAST(item->>'qty' AS DECIMAL(12, 2)) AS qty,
    TRY_CAST(item->>'price' AS DECIMAL(14, 2)) AS price,
    item->>'order_time' AS order_time,
    event_id,
    "offset" AS kafka_offset,
    item_index
FROM bronze_transactions_raw,
LATERAL UNNEST(CAST(json_extract(raw_payload, '$.items') AS JSON[])) WITH ORDINALITY AS t(item, item_index);


-- 4. View: bronze_master_menu
-- Membaca seluruh snapshot Master Menu Parquet langsung dari MinIO secara dinamis.
-- Seluruh kolom sumber asli dipertahankan di Bronze dalam raw_payload dan source_row,
-- serta metadata batch dan kolom utama diekspos untuk kemudahan query.
-- Catatan: Pastikan batch Master Menu sudah dijalankan minimal satu kali agar file Parquet
-- tersedia di MinIO bucket bakery-bronze/master_menu/.
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
    -- Seluruh baris asli dalam format JSON/Struct agar tidak ada kolom sumber yang hilang
    raw_payload,
    source_row
FROM read_parquet(
    's3://bakery-bronze/master_menu/**/*.parquet',
    filename = false,
    hive_partitioning = false,
    union_by_name = true
);
