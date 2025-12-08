import json
import threading
from pathlib import Path
from typing import Dict, Any, Optional


class ProfileStore:
    """
    Simple thread-safe persistence for Telegram user profiles.
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

    def get_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            data = self._load()
            return data.get(str(user_id))

    def upsert_profile(self, user_id: int, profile: Dict[str, Any]) -> None:
        with self._lock:
            data = self._load()
            data[str(user_id)] = profile
            self._save(data)

    def delete_profile(self, user_id: int) -> None:
        with self._lock:
            data = self._load()
            data.pop(str(user_id), None)
            self._save(data)

    def list_profiles(self) -> Dict[str, Any]:
        with self._lock:
            return self._load()
