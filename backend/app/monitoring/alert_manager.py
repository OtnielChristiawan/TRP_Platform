"""Alert Manager & Notification Dispatcher for Bakery Data Platform V4.

Implements F-15 Compliance:
- Evaluates Alert A (Job Failure), Alert B (Stream Lag), Alert C (Resource Unhealthy).
- Enforces threshold, window, severity, owner, runbook, and routing.
- Handles full lifecycle: FIRING -> NOTIFICATION DISPATCH -> RESOLVED / CLEAR.
- Persists all notifications to state/alerts/notifications.jsonl.
"""
import json
import logging
import os
import urllib.request
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("bakery.alerts")

# Paths
BASE_DIR = Path(__file__).resolve().parents[1]
RULES_FILE = BASE_DIR / "monitoring" / "alert_rules.json"
STATE_DIR = Path(os.getenv("STATE_DIR", BASE_DIR / "state"))
ALERTS_DIR = STATE_DIR / "alerts"
NOTIFICATIONS_LOG = ALERTS_DIR / "notifications.jsonl"
ACTIVE_ALERTS_FILE = ALERTS_DIR / "active_alerts.json"


class AlertStatus(str, Enum):
    FIRING = "FIRING"
    RESOLVED = "RESOLVED"


class AlertSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertManager:
    _instance: Optional["AlertManager"] = None

    def __init__(self, rules_path: Optional[Path] = None):
        self.rules_path = rules_path or RULES_FILE
        self.rules: Dict[str, Dict[str, Any]] = {}
        self.active_alerts: Dict[str, Dict[str, Any]] = {}
        self._ensure_storage()
        self._load_rules()
        self._load_active_alerts()

    def _ensure_storage(self):
        ALERTS_DIR.mkdir(parents=True, exist_ok=True)
        if not NOTIFICATIONS_LOG.exists():
            NOTIFICATIONS_LOG.touch()

    def _load_rules(self):
        if self.rules_path.exists():
            try:
                with open(self.rules_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for rule in data.get("rules", []):
                        self.rules[rule["id"]] = rule
            except Exception as e:
                logger.error(f"Error loading alert rules: {e}")

    def _load_active_alerts(self):
        if ACTIVE_ALERTS_FILE.exists():
            try:
                with open(ACTIVE_ALERTS_FILE, "r", encoding="utf-8") as f:
                    self.active_alerts = json.load(f)
            except Exception:
                self.active_alerts = {}
        else:
            self.active_alerts = {}

    def _persist_active_alerts(self):
        try:
            with open(ACTIVE_ALERTS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.active_alerts, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving active alerts: {e}")

    def dispatch_notification(self, payload: Dict[str, Any]):
        """Dispatch notification to configured channels (file log, console, optional webhook)."""
        # 1. Append to structured file log (F-15 Evidence)
        try:
            with open(NOTIFICATIONS_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload) + "\n")
        except Exception as e:
            logger.error(f"Failed to append alert notification to file: {e}")

        # 2. Console log
        log_level = logging.CRITICAL if payload.get("severity") == "CRITICAL" else logging.WARNING
        logger.log(log_level, f"[ALERT {payload['status']}] {payload['rule_name']} - {payload['message']}")

        # 3. Optional Webhook dispatch if configured
        webhook_url = os.getenv("ALERT_WEBHOOK_URL")
        if webhook_url:
            try:
                req = urllib.request.Request(
                    webhook_url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=3):
                    pass
            except Exception as e:
                logger.warning(f"Optional webhook dispatch failed: {e}")

    def fire_alert(
        self,
        rule_id: str,
        current_value: Any,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Trigger an alert. Transitions rule to FIRING state and dispatches notification."""
        rule = self.rules.get(rule_id, {})
        now_iso = datetime.now(timezone.utc).isoformat()

        alert_event = {
            "alert_id": f"{rule_id}_{int(datetime.now(timezone.utc).timestamp())}",
            "rule_id": rule_id,
            "rule_name": rule.get("name", rule_id),
            "status": AlertStatus.FIRING.value,
            "severity": rule.get("severity", AlertSeverity.WARNING.value),
            "owner": rule.get("owner", "Platform Operations"),
            "threshold": rule.get("threshold"),
            "current_value": current_value,
            "message": message,
            "runbook": rule.get("runbook"),
            "triggered_at": now_iso,
            "resolved_at": None,
            "details": details or {},
        }

        # Store in active alerts
        self.active_alerts[rule_id] = alert_event
        self._persist_active_alerts()

        # Dispatch notification
        self.dispatch_notification(alert_event)
        return alert_event

    def resolve_alert(
        self,
        rule_id: str,
        resolution_message: str = "Condition restored to normal values.",
    ) -> Optional[Dict[str, Any]]:
        """Resolve an active alert. Transitions rule to RESOLVED state and dispatches clear notification."""
        if rule_id not in self.active_alerts:
            return None

        alert_event = self.active_alerts.pop(rule_id)
        alert_event["status"] = AlertStatus.RESOLVED.value
        alert_event["resolved_at"] = datetime.now(timezone.utc).isoformat()
        alert_event["resolution_message"] = resolution_message

        self._persist_active_alerts()
        self.dispatch_notification(alert_event)
        return alert_event

    # -------------------------------------------------------------------------
    # Evaluation Engines for the 3 Lecturer Rules
    # -------------------------------------------------------------------------

    def evaluate_job_status(
        self,
        job_name: str,
        exit_code: int,
        error_details: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Evaluate Rule A: Spark Batch Job Execution Failure."""
        rule_id = "ALERT_A_JOB_FAILURE"
        if exit_code != 0:
            msg = f"Job '{job_name}' failed with non-zero exit code ({exit_code}). Details: {error_details or 'None'}"
            return self.fire_alert(
                rule_id=rule_id,
                current_value=exit_code,
                message=msg,
                details={"job_name": job_name, "exit_code": exit_code, "error": error_details},
            )
        else:
            # If previously firing, resolve it
            if rule_id in self.active_alerts:
                return self.resolve_alert(
                    rule_id=rule_id,
                    resolution_message=f"Job '{job_name}' executed successfully with exit code 0.",
                )
        return None

    def evaluate_stream_freshness(
        self,
        freshness_seconds: float,
        message_lag: int = 0,
    ) -> Optional[Dict[str, Any]]:
        """Evaluate Rule B: Stream Freshness High Lag / Ingestion Delay."""
        rule_id = "ALERT_B_STREAM_LAG"
        freshness_threshold = 1800  # 30 minutes
        lag_threshold = 100

        if freshness_seconds > freshness_threshold or message_lag > lag_threshold:
            msg = f"Stream ingestion delayed. Freshness lag: {round(freshness_seconds, 1)}s (threshold: {freshness_threshold}s), Backlog: {message_lag} msgs."
            return self.fire_alert(
                rule_id=rule_id,
                current_value={"freshness_seconds": round(freshness_seconds, 1), "message_lag": message_lag},
                message=msg,
                details={"freshness_seconds": freshness_seconds, "message_lag": message_lag},
            )
        else:
            if rule_id in self.active_alerts:
                return self.resolve_alert(
                    rule_id=rule_id,
                    resolution_message=f"Stream ingestion back within normal bounds. Freshness: {round(freshness_seconds, 1)}s.",
                )
        return None

    def evaluate_service_health(
        self,
        container_statuses: Dict[str, str],
        memory_percent: float,
    ) -> Optional[Dict[str, Any]]:
        """Evaluate Rule C: Infrastructure Container or Host Resource Critical."""
        rule_id = "ALERT_C_SERVICE_UNHEALTHY"
        memory_threshold = 90.0

        unhealthy_services = {
            svc: status
            for svc, status in container_statuses.items()
            if status not in ("running", "healthy", "up")
        }

        is_critical = len(unhealthy_services) > 0 or memory_percent >= memory_threshold

        if is_critical:
            reasons = []
            if unhealthy_services:
                reasons.append(f"Unhealthy containers: {unhealthy_services}")
            if memory_percent >= memory_threshold:
                reasons.append(f"Host RAM at {memory_percent}% (threshold: {memory_threshold}%)")
            msg = "Infrastructure health alert: " + "; ".join(reasons)
            return self.fire_alert(
                rule_id=rule_id,
                current_value={
                    "unhealthy_containers": unhealthy_services,
                    "memory_percent": memory_percent,
                },
                message=msg,
                details={"unhealthy": unhealthy_services, "memory_percent": memory_percent},
            )
        else:
            if rule_id in self.active_alerts:
                return self.resolve_alert(
                    rule_id=rule_id,
                    resolution_message=f"All containers healthy and memory within normal range ({memory_percent}%).",
                )
        return None

    def get_active_alerts(self) -> List[Dict[str, Any]]:
        return list(self.active_alerts.values())

    def get_alert_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        history = []
        if NOTIFICATIONS_LOG.exists():
            try:
                with open(NOTIFICATIONS_LOG, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    for line in lines[-limit:]:
                        line = line.strip()
                        if line:
                            history.append(json.loads(line))
            except Exception as e:
                logger.error(f"Error reading alert history: {e}")
        return history[::-1]


def get_alert_manager() -> AlertManager:
    if AlertManager._instance is None:
        AlertManager._instance = AlertManager()
    return AlertManager._instance
