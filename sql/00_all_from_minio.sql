-- Simple view to read all Bronze data directly from MinIO and expose every column
-- This view does NOT alter any existing setup; it merely reads the Parquet files
-- stored under the `bakery-bronze/transactions/` bucket.

CREATE OR REPLACE VIEW bronze_all AS
SELECT *
FROM read_parquet(
    's3://bakery-bronze/transactions/**/*.parquet',
    filename = false,
    hive_partitioning = false
);
