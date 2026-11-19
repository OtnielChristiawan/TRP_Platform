-- Duplicate detection view for bakery data platform
-- This view lists every transaction item that has an exact duplicate
-- of the original CSV row (i.e., the same `source_row` JSON payload).
-- It uses a JSON hash to group identical source rows and returns all rows
-- that appear more than once.

CREATE OR REPLACE VIEW bronze_transaction_duplicates AS
WITH dup AS (
    SELECT
        event_id,
        bill_number,
        item_index,
        source_row,
        COUNT(*) OVER (PARTITION BY json_hash(source_row)) AS duplicate_count
    FROM bronze_transaction_items
)
SELECT
    event_id,
    bill_number,
    item_index,
    source_row,
    duplicate_count
FROM dup
WHERE duplicate_count > 1;
