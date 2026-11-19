-- ============================================================================
-- BAKERY DATA PLATFORM V4: VALIDATION & EXPLORATION QUERIES
-- ============================================================================
-- Kumpulan 10 query SQL siap pakai untuk menganalisis dan memvalidasi
-- data transaksi Toko Roti Pagi di MinIO Bronze.
-- Jalankan satu per satu di DBeaver (Ctrl + Enter atau Alt + X).
-- ============================================================================


-- ----------------------------------------------------------------------------
-- 1. Menampilkan 100 transaksi pertama berdasarkan event_time (paling awal)
-- ----------------------------------------------------------------------------
SELECT 
    sales_number,
    bill_number,
    branch,
    event_time,
    producer_sent_at,
    bronze_ingested_at,
    kafka_offset
FROM bronze_transactions
ORDER BY event_time ASC
LIMIT 100;


-- ----------------------------------------------------------------------------
-- 2. Menampilkan 100 transaksi terbaru berdasarkan event_time (paling akhir)
-- ----------------------------------------------------------------------------
SELECT 
    sales_number,
    bill_number,
    branch,
    event_time,
    producer_sent_at,
    bronze_ingested_at,
    kafka_offset
FROM bronze_transactions
ORDER BY event_time DESC
LIMIT 100;


-- ----------------------------------------------------------------------------
-- 3. Melihat seluruh item menu dalam satu bill tertentu (contoh bill pertama)
--    Ganti nomor bill sesuai kebutuhan pencarian Anda.
-- ----------------------------------------------------------------------------
SELECT 
    bill_number,
    item_index,
    menu,
    category,
    category_detail,
    qty,
    price,
    (qty * price) AS subtotal,
    order_time,
    event_time
FROM bronze_transaction_items
WHERE bill_number = (
    SELECT bill_number 
    FROM bronze_transactions 
    ORDER BY event_time ASC 
    LIMIT 1
)
ORDER BY item_index ASC;


-- ----------------------------------------------------------------------------
-- 4. Menghitung total jumlah transaksi (bill) yang sudah masuk ke Bronze
-- ----------------------------------------------------------------------------
SELECT 
    COUNT(*) AS total_transactions,
    COUNT(DISTINCT bill_number) AS distinct_bills,
    COUNT(DISTINCT event_id) AS distinct_events,
    MIN(event_time) AS earliest_event_time,
    MAX(event_time) AS latest_event_time
FROM bronze_transactions;


-- ----------------------------------------------------------------------------
-- 5. Menghitung total baris item transaksi dan total kuantitas terjual
-- ----------------------------------------------------------------------------
SELECT 
    COUNT(*) AS total_item_rows,
    SUM(qty) AS total_qty_sold,
    SUM(qty * price) AS total_gross_sales,
    AVG(price) AS average_item_price
FROM bronze_transaction_items;


-- ----------------------------------------------------------------------------
-- 6. Mencari duplikat berdasarkan event_id
-- ----------------------------------------------------------------------------
SELECT 
    event_id,
    COUNT(*) AS occurrence_count,
    MIN(kafka_offset) AS min_offset,
    MAX(kafka_offset) AS max_offset
FROM bronze_transactions
GROUP BY event_id
HAVING COUNT(*) > 1;


-- ----------------------------------------------------------------------------
-- 7. Mendeteksi data NULL / kosong pada kolom penting
-- ----------------------------------------------------------------------------
SELECT 
    COUNT(*) AS total_checked,
    COUNT(*) FILTER (WHERE sales_number IS NULL OR sales_number = '') AS missing_sales_number,
    COUNT(*) FILTER (WHERE bill_number IS NULL OR bill_number = '') AS missing_bill_number,
    COUNT(*) FILTER (WHERE event_time IS NULL) AS missing_event_time,
    COUNT(*) FILTER (WHERE branch IS NULL OR branch = '') AS missing_branch,
    COUNT(*) FILTER (WHERE raw_payload IS NULL) AS missing_payload
FROM bronze_transactions_raw
LEFT JOIN bronze_transactions USING (event_id);


-- ----------------------------------------------------------------------------
-- 8. Memeriksa urutan event_time dibandingkan Kafka offset
--    Mendeteksi apakah terdapat out-of-order events saat dikirim ke Kafka.
-- ----------------------------------------------------------------------------
WITH sequenced AS (
    SELECT 
        kafka_offset,
        event_time,
        LAG(event_time) OVER (ORDER BY kafka_offset) AS prev_event_time,
        LAG(kafka_offset) OVER (ORDER BY kafka_offset) AS prev_offset
    FROM bronze_transactions
)
SELECT 
    prev_offset,
    kafka_offset,
    prev_event_time,
    event_time,
    date_diff('second', prev_event_time, event_time) AS seconds_diff
FROM sequenced
WHERE prev_event_time IS NOT NULL 
  AND event_time < prev_event_time
ORDER BY kafka_offset ASC
LIMIT 50;


-- ----------------------------------------------------------------------------
-- 9. Membandingkan latency pipeline:
--    event_time -> replay_scheduled_at -> producer_sent_at -> bronze_ingested_at
-- ----------------------------------------------------------------------------
SELECT 
    sales_number,
    bill_number,
    event_time,
    replay_scheduled_at,
    producer_sent_at,
    bronze_ingested_at,
    ROUND(date_diff('millisecond', replay_scheduled_at, producer_sent_at) / 1000.0, 3) AS replay_lag_seconds,
    ROUND(date_diff('millisecond', producer_sent_at, bronze_ingested_at) / 1000.0, 3) AS ingestion_lag_seconds
FROM bronze_transactions
WHERE producer_sent_at IS NOT NULL
ORDER BY event_time DESC
LIMIT 50;


-- ----------------------------------------------------------------------------
-- 10. Menampilkan jumlah transaksi dan item per tanggal dan per jam
-- ----------------------------------------------------------------------------
SELECT 
    CAST(event_time AS DATE) AS transaction_date,
    EXTRACT(HOUR FROM event_time) AS transaction_hour,
    COUNT(DISTINCT bill_number) AS total_bills,
    COUNT(*) AS total_items_sold,
    SUM(qty * price) AS total_sales_amount
FROM bronze_transaction_items
GROUP BY CAST(event_time AS DATE), EXTRACT(HOUR FROM event_time)
ORDER BY transaction_date ASC, transaction_hour ASC;
