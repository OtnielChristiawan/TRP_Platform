"""DuckDB connection and query execution utilities for MinIO Parquet."""
import logging
import os
import duckdb
from pathlib import Path
from typing import Any, Dict, List, Optional
from app.core.config import settings

logger = logging.getLogger("bakery.duckdb")


class DuckDBManager:
    _instance: Optional["DuckDBManager"] = None

    def __init__(self):
        self.endpoint = settings.S3_ENDPOINT.replace("http://", "").replace("https://", "").rstrip("/")
        self.access_key = settings.MINIO_ROOT_USER
        self.secret_key = settings.MINIO_ROOT_PASSWORD
        self.use_ssl = settings.MINIO_SECURE
        self.ext_dir = Path(settings.DUCKDB_EXT_DIR).resolve()
        self.ext_dir.mkdir(parents=True, exist_ok=True)
        self._init_connection()

    def _init_connection(self):
        config = {
            "extension_directory": str(self.ext_dir).replace("\\", "/"),
        }
        self.conn = duckdb.connect(":memory:", config=config)
        try:
            self.conn.execute("LOAD httpfs;")
        except Exception:
            try:
                self.conn.execute("INSTALL httpfs;")
                self.conn.execute("LOAD httpfs;")
            except Exception as e:
                logger.warning(f"Could not install/load httpfs via standard method: {e}")

        # Configure S3 persistent SECRET for DuckDB 0.10+ / 1.0+
        try:
            self.conn.execute(f"""
                CREATE OR REPLACE SECRET minio_secret (
                    TYPE S3,
                    KEY_ID '{self.access_key}',
                    SECRET '{self.secret_key}',
                    ENDPOINT '{self.endpoint}',
                    USE_SSL {'true' if self.use_ssl else 'false'},
                    URL_STYLE 'path'
                );
            """)
            logger.info(f"Configured DuckDB persistent S3 secret for endpoint: {self.endpoint}")
        except Exception as e:
            logger.warning(f"Could not create secret, falling back to legacy settings: {e}")

        # Also configure legacy S3 settings
        try:
            self.conn.execute(f"SET s3_endpoint = '{self.endpoint}';")
            self.conn.execute(f"SET s3_access_key_id = '{self.access_key}';")
            self.conn.execute(f"SET s3_secret_access_key = '{self.secret_key}';")
            self.conn.execute(f"SET s3_use_ssl = {'true' if self.use_ssl else 'false'};")
            self.conn.execute("SET s3_url_style = 'path';")
        except Exception:
            pass

    def reset_connection(self):
        """Close existing connection and re-initialize connection & secrets."""
        try:
            self.conn.close()
        except Exception:
            pass
        self._init_connection()

    def get_cursor(self):
        """Return a fresh cursor for query execution."""
        return self.conn.cursor()

    def query(self, sql: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        """Execute parameterized SQL query and return rows as list of dicts."""
        cursor = self.conn.cursor()
        try:
            if params:
                rel = cursor.execute(sql, params)
            else:
                rel = cursor.execute(sql)
            
            if rel.description is None:
                return []
            
            cols = [desc[0] for desc in rel.description]
            rows = rel.fetchall()
            return [dict(zip(cols, row)) for row in rows]
        except Exception as e:
            logger.error(f"DuckDB Query Error: {e} | SQL: {sql} | Params: {params}")
            raise e
        finally:
            cursor.close()


def get_db_manager() -> DuckDBManager:
    if DuckDBManager._instance is None:
        DuckDBManager._instance = DuckDBManager()
    return DuckDBManager._instance
