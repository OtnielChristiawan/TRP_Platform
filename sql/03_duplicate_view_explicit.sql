-- Duplicate detection view with explicit columns
-- Lists each transaction item that has an exact duplicate of the original CSV row.
-- All relevant columns are listed explicitly (no SELECT *).

CREATE OR REPLACE VIEW bronze_transaction_duplicates_explicit AS
WITH dup AS (
    SELECT
        ti.sales_number,
        ti.bill_number,
        ti.event_time,
        ti.menu,
        ti.category,
        ti.category_detail,
        ti.qty,
        ti.price,
        ti.order_time,
        ti.event_id,
        ti.kafka_offset,
        ti.item_index,
        -- Extract the original CSV row JSON (assuming it is stored in raw_payload under the key "source_row")
        r.raw_payload::json->'source_row' AS source_row,
        COUNT(*) OVER (PARTITION BY json_hash(r.raw_payload::json->'source_row')) AS duplicate_count
    FROM bronze_transaction_items ti
    JOIN bronze_transactions_raw r ON ti.event_id = r.event_id
    -- The join reuses the same row; we keep the raw_payload from the raw view for source_row extraction.
)
SELECT
    sales_number,
    bill_number,
    event_time,
    menu,
    category,
    category_detail,
    qty,
    price,
    order_time,
    event_id,
    kafka_offset,
    item_index,
    source_row,
    duplicate_count
FROM dup
WHERE duplicate_count > 1;
