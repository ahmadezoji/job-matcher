import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


class JobStateStore:
    """
    Persists fetched jobs per user so the bot can resume the last state and avoid duplicates.
    """

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        if not self.path.exists():
            self.path.write_text("{}", encoding="utf-8")

    def _load(self) -> Dict[str, Any]:
        with self.path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def _save(self, data: Dict[str, Any]) -> None:
        tmp_path = self.path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        tmp_path.replace(self.path)

    def _ensure_user(self, user_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        user_data = data.setdefault(str(user_id), {})
        user_data.setdefault("jobs", {})
        return user_data

    def record_job(self, user_id: int, job_id: int, payload: Dict[str, Any], status: str) -> None:
        with self._lock:
            data = self._load()
            user_data = self._ensure_user(user_id, data)
            user_data["jobs"][str(job_id)] = {
                "status": status,
                "payload": payload,
                "updated_at": _now_iso(),
            }
            self._save(data)

    def update_status(self, user_id: int, job_id: int, status: str) -> None:
        with self._lock:
            data = self._load()
            user_data = self._ensure_user(user_id, data)
            job = user_data["jobs"].get(str(job_id))
            if not job:
                return
            job["status"] = status
            job["updated_at"] = _now_iso()
            self._save(data)

    def get_job(self, user_id: int, job_id: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            data = self._load()
            user_data = data.get(str(user_id), {})
            return user_data.get("jobs", {}).get(str(job_id))

    def mark_bid_result(self, user_id: int, job_id: int, status: str, note: Optional[str] = None) -> None:
        with self._lock:
            data = self._load()
            user_data = self._ensure_user(user_id, data)
            job = user_data["jobs"].setdefault(str(job_id), {})
            job["status"] = status
            job["updated_at"] = _now_iso()
            if note:
                job["note"] = note
            self._save(data)
