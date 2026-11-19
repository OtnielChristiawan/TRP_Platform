"""ML Configuration for Bakery Data Platform V4."""
import os
from pathlib import Path

# Base Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = PROJECT_ROOT / "state" / "ml"
ARTIFACTS_DIR = STATE_DIR / "models"
EXPERIMENTS_DIR = STATE_DIR / "experiments"
PREDICTIONS_DIR = STATE_DIR / "predictions"
DATASETS_DIR = STATE_DIR / "datasets"

for d in [STATE_DIR, ARTIFACTS_DIR, EXPERIMENTS_DIR, PREDICTIONS_DIR, DATASETS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# MinIO S3 Configuration
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://localhost:9000")
MINIO_ROOT_USER = os.getenv("MINIO_ROOT_USER", "bakeryadmin")
MINIO_ROOT_PASSWORD = os.getenv("MINIO_ROOT_PASSWORD", "bakerydemo123")
GOLD_BUCKET = os.getenv("GOLD_BUCKET", "bakery-gold")
DUCKDB_EXT_DIR = os.getenv("DUCKDB_EXT_DIR", str(PROJECT_ROOT / "state" / "duckdb_ext"))

# ML Experimentation Parameters
RANDOM_SEED = 42
DEFAULT_HORIZON_DAYS = 7
OPERATIONAL_HOURS_START = 9
OPERATIONAL_HOURS_END = 19
SAFETY_STOCK_Z = 1.0  # Approx 84% cycle service level buffer
MIN_SAMPLES_FOR_EVAL = 5

TIMEZONE = "Asia/Jakarta"
