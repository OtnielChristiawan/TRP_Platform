"""ML Data Extractor: Queries Gold Data Marts from MinIO using DuckDB."""
import logging
from typing import Optional
import duckdb
import pandas as pd
from ml.config import (
    DUCKDB_EXT_DIR,
    GOLD_BUCKET,
    MINIO_ROOT_PASSWORD,
    MINIO_ROOT_USER,
    S3_ENDPOINT,
)

logger = logging.getLogger("bakery.ml.data")


class GoldDataExtractor:
    """Extracts analytical datasets from MinIO Gold Parquet marts."""

    def __init__(self, endpoint: Optional[str] = None):
        self.endpoint = (endpoint or S3_ENDPOINT).replace("http://", "").replace("https://", "")
        self.use_ssl = "false"
        self._init_duckdb()

    def _init_duckdb(self):
        self.conn = duckdb.connect()
        try:
            self.conn.execute(f"SET extension_directory = '{DUCKDB_EXT_DIR}';")
            self.conn.execute("INSTALL httpfs; LOAD httpfs;")
            secret_query = f"""
            CREATE OR REPLACE SECRET minio_secret (
                TYPE S3,
                KEY_ID '{MINIO_ROOT_USER}',
                SECRET '{MINIO_ROOT_PASSWORD}',
                ENDPOINT '{self.endpoint}',
                USE_SSL {self.use_ssl},
                URL_STYLE 'path'
            );
            """
            self.conn.execute(secret_query)
        except Exception as e:
            logger.warning(f"Failed to initialize MinIO secret in DuckDB: {e}")

    def get_demand_features(self) -> pd.DataFrame:
        """Extracts gold_ml_demand_features dataset."""
        query = f"""
        SELECT 
            CAST(sales_date AS DATE) AS sales_date,
            branch,
            menu_key,
            menu_name,
            menu_category,
            CAST(qty_sold AS DOUBLE) AS qty_sold,
            CAST(day_of_week AS INTEGER) AS day_of_week,
            CAST(day_of_month AS INTEGER) AS day_of_month,
            CAST(month AS INTEGER) AS month,
            CAST(is_weekend AS BOOLEAN) AS is_weekend,
            CAST(lag_1_qty AS DOUBLE) AS lag_1_qty,
            CAST(lag_7_qty AS DOUBLE) AS lag_7_qty,
            CAST(rolling_avg_7d_qty AS DOUBLE) AS rolling_avg_7d_qty,
            batch_run_id
        FROM read_parquet('s3://{GOLD_BUCKET}/gold_ml_demand_features/*/*.parquet')
        ORDER BY sales_date ASC, branch, menu_key
        """
        try:
            df = self.conn.execute(query).fetchdf()
            logger.info(f"Extracted {len(df)} demand feature rows from MinIO Gold.")
            return df
        except Exception as e:
            logger.error(f"Error extracting demand features from MinIO Gold: {e}")
            raise

    def get_daily_sales(self) -> pd.DataFrame:
        """Extracts gold_sales_daily dataset."""
        query = f"""
        SELECT 
            CAST(sales_date AS DATE) AS sales_date,
            branch,
            CAST(total_bills AS BIGINT) AS total_bills,
            CAST(total_item_rows AS BIGINT) AS total_item_rows,
            CAST(total_qty_sold AS DOUBLE) AS total_qty_sold,
            CAST(net_sales AS DOUBLE) AS net_sales,
            CAST(gross_sales AS DOUBLE) AS gross_sales,
            batch_run_id
        FROM read_parquet('s3://{GOLD_BUCKET}/gold_sales_daily/*/*.parquet')
        ORDER BY sales_date ASC, branch
        """
        try:
            df = self.conn.execute(query).fetchdf()
            logger.info(f"Extracted {len(df)} daily sales rows from MinIO Gold.")
            return df
        except Exception as e:
            logger.error(f"Error extracting daily sales: {e}")
            raise

    def get_hourly_sales(self) -> pd.DataFrame:
        """Extracts gold_sales_hourly dataset."""
        query = f"""
        SELECT 
            CAST(sales_date AS DATE) AS sales_date,
            CAST(sales_hour AS INTEGER) AS sales_hour,
            branch,
            CAST(total_bills AS BIGINT) AS total_bills,
            CAST(total_qty_sold AS DOUBLE) AS total_qty_sold,
            CAST(net_sales AS DOUBLE) AS net_sales,
            batch_run_id
        FROM read_parquet('s3://{GOLD_BUCKET}/gold_sales_hourly/*/*.parquet')
        ORDER BY sales_date ASC, sales_hour ASC
        """
        try:
            df = self.conn.execute(query).fetchdf()
            logger.info(f"Extracted {len(df)} hourly sales rows from MinIO Gold.")
            return df
        except Exception as e:
            logger.error(f"Error extracting hourly sales: {e}")
            raise
