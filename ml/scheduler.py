"""ML Scheduler for Weekly Training and Daily Batch Inference (Asia/Jakarta WIB)."""
import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Optional
from ml.config import TIMEZONE
from ml.inference.batch_inference import BatchInferenceEngine
from ml.tracking.tracker import ExperimentTracker
from ml.training.train_runner import run_training_pipeline

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo(TIMEZONE)
except Exception:
    TZ = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [ML-Scheduler]: %(message)s",
)
logger = logging.getLogger("bakery.ml.scheduler")

# Configurable schedules from env vars
TRAIN_WEEKDAY = int(os.getenv("ML_TRAIN_WEEKDAY", "6"))  # 6 = Sunday (0=Mon, 6=Sun)
TRAIN_HOUR = int(os.getenv("ML_TRAIN_HOUR", "2"))        # 02:00 WIB
INFER_HOUR = int(os.getenv("ML_INFER_HOUR", "3"))        # 03:00 WIB


def get_current_time() -> datetime:
    return datetime.now(TZ) if TZ else datetime.now()


def run_training_job():
    logger.info("Executing scheduled Weekly ML Training...")
    try:
        res = run_training_pipeline()
        logger.info(f"Training completed: {res.get('status')}")
    except Exception as e:
        logger.error(f"Training job error: {e}", exc_info=True)


def run_inference_job():
    logger.info("Executing scheduled Daily ML Batch Inference...")
    try:
        engine = BatchInferenceEngine()
        res = engine.run_inference()
        logger.info(f"Inference completed: {res.get('status')}")
    except Exception as e:
        logger.error(f"Inference job error: {e}", exc_info=True)


def check_and_run_catchup():
    """Catch-up policy: Triggers missed jobs if laptop or containers were down."""
    tracker = ExperimentTracker()
    reg = tracker.get_registry()
    last_promoted = reg.get("last_promoted_at")

    now = get_current_time()

    # If never trained or last training > 7 days ago, run training
    should_train = False
    if not last_promoted:
        should_train = True
    else:
        try:
            dt = datetime.fromisoformat(last_promoted)
            if (now.replace(tzinfo=None) - dt.replace(tzinfo=None)) > timedelta(days=7):
                should_train = True
        except Exception:
            should_train = True

    if should_train:
        logger.info("Catch-up Policy: Training was missed or stale. Running catch-up training...")
        run_training_job()

    # Run inference catch-up
    run_inference_job()


def start_scheduler_loop(interval_sec: int = 60):
    logger.info("ML Scheduler started. Timezone: Asia/Jakarta.")
    logger.info(f"Weekly Training scheduled on Sunday at {TRAIN_HOUR:02d}:00 WIB.")
    logger.info(f"Daily Inference scheduled daily at {INFER_HOUR:02d}:00 WIB.")

    # Run catch-up check on initial startup
    check_and_run_catchup()

    last_trained_day = None
    last_inferred_day = None

    while True:
        now = get_current_time()
        current_date = now.date()

        # Weekly training trigger: Sunday at 02:00
        if now.weekday() == TRAIN_WEEKDAY and now.hour == TRAIN_HOUR:
            if last_trained_day != current_date:
                run_training_job()
                last_trained_day = current_date

        # Daily inference trigger: Every day at 03:00
        if now.hour == INFER_HOUR:
            if last_inferred_day != current_date:
                run_inference_job()
                last_inferred_day = current_date

        time.sleep(interval_sec)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bakery ML Scheduler & Execution CLI")
    parser.add_argument(
        "--mode",
        choices=["schedule", "train", "infer", "both", "catchup"],
        default="both",
        help="Execution mode (default: both runs train + infer once)",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run continuous scheduler loop instead of single run",
    )
    args = parser.parse_args()

    if args.loop or args.mode == "schedule":
        start_scheduler_loop()
    elif args.mode == "train":
        run_training_job()
    elif args.mode == "infer":
        run_inference_job()
    elif args.mode == "catchup":
        check_and_run_catchup()
    else:  # both
        run_training_job()
        run_inference_job()
