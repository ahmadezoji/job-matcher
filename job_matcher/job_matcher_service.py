from __future__ import annotations

import queue
import threading
import time
from typing import Dict, List, Optional, Any

from .freelancer_api_helper import FreelancerJob, search_jobs
from .job_state_store import JobStateStore
from .profile_store import ProfileStore


class JobMatcherService:
    """
    Background worker that polls freelancing platforms and pushes new jobs
    into a queue that the Telegram bot can consume.
    """

    def __init__(
        self,
        profile_store: ProfileStore,
        job_state_store: JobStateStore,
        fetch_interval_seconds: int = 120,
        max_jobs_per_user: int = 5,
    ):
        self.profile_store = profile_store
        self.job_state_store = job_state_store
        self.fetch_interval_seconds = max(fetch_interval_seconds, 30)
        self.max_jobs_per_user = max_jobs_per_user

        self._active_users: Dict[int, float] = {}
        self._queue: "queue.Queue[tuple[int, FreelancerJob]]" = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._stopped = threading.Event()

    @property
    def queue(self) -> "queue.Queue[tuple[int, FreelancerJob]]":
        return self._queue

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self) -> None:
        self._stopped.set()
        if self._thread.is_alive():
            self._thread.join(timeout=5)

    def enable_user(self, user_id: int) -> None:
        # Reset last fetch timestamp so we fetch immediately.
        self._active_users[user_id] = 0

    def disable_user(self, user_id: int) -> None:
        self._active_users.pop(user_id, None)

    def _run(self) -> None:
        while not self._stopped.is_set():
            now = time.time()
            for user_id, last_fetch in list(self._active_users.items()):
                if now - last_fetch < self.fetch_interval_seconds:
                    continue
                self._fetch_for_user(user_id)
                self._active_users[user_id] = time.time()
            time.sleep(5)

    def _fetch_for_user(self, user_id: int) -> None:
        profile = self.profile_store.get_profile(user_id)
        if not profile:
            return
        query = self._build_query(profile)
        skills = self._extract_skills(profile)
        currency = profile.get("currency")
        hourly_rate = profile.get("hourly_rate")
        min_hourly = None
        max_hourly = None
        if hourly_rate:
            try:
                hourly_value = float(hourly_rate)
                min_hourly = hourly_value * 0.8
                max_hourly = hourly_value * 1.2
            except ValueError:
                pass

        jobs = search_jobs(
            query=query,
            skills=skills,
            min_hourly_rate=min_hourly,
            max_hourly_rate=max_hourly,
            currency=currency,
            limit=self.max_jobs_per_user,
        )

        for job in jobs:
            already_tracked = self.job_state_store.get_job(user_id, job.project_id)
            if already_tracked:
                continue
            self.job_state_store.record_job(user_id, job.project_id, job.to_dict(), "fetched")
            self._queue.put((user_id, job))

    @staticmethod
    def _build_query(profile: Dict[str, Any]) -> str:
        positions = profile.get("positions")
        if isinstance(positions, list) and positions:
            return positions[0]
        if isinstance(positions, str) and positions.strip():
            return positions.strip()
        skills = profile.get("skills", "")
        if isinstance(skills, str) and skills.strip():
            return skills.split(",")[0]
        return "Freelancer"

    @staticmethod
    def _extract_skills(profile: Dict[str, Any]) -> Optional[List[str]]:
        skills = profile.get("skills")
        if isinstance(skills, list):
            return skills
        if isinstance(skills, str):
            parts = [skill.strip() for skill in skills.split(",") if skill.strip()]
            return parts or None
        return None
