from __future__ import annotations

import html
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import requests

from .config import load_settings


logger = logging.getLogger(__name__)
settings = load_settings()
API_BASE = settings.freelancer.api_base.rstrip("/")


def load_token() -> str:
    return settings.freelancer.api_token


@dataclass
class FreelancerJob:
    project_id: int
    title: str
    preview_description: str
    full_description: str
    currency: str
    budget_min: Optional[float]
    budget_max: Optional[float]
    job_type: str
    bid_count: int
    duration: Optional[int]
    skills: List[str] = field(default_factory=list)
    url: Optional[str] = None
    time_submitted: Optional[int] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FreelancerJob":
        budget = data.get("budget") or {}
        currency = budget.get("currency") or {}
        jobs = data.get("jobs") or []
        upgrades = data.get("upgrades") or {}
        return cls(
            project_id=data.get("id"),
            title=data.get("title", "Untitled project"),
            preview_description=data.get("preview_description", "").strip(),
            full_description=data.get("description", "").strip(),
            currency=currency.get("code") or currency.get("sign") or "USD",
            budget_min=budget.get("minimum"),
            budget_max=budget.get("maximum"),
            job_type="hourly" if upgrades.get("is_hourly", False) else "fixed",
            bid_count=data.get("bid_stats", {}).get("bid_count", 0),
            duration=data.get("period"),
            skills=[job.get("name") for job in jobs if job.get("name")],
            url=data.get("seo_url"),
            time_submitted=data.get("submitdate"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def summary_html(self) -> str:
        parts = [
            f"<b>{html.escape(self.title)}</b>",
            html.escape(self.preview_description) if self.preview_description else "<i>No preview available.</i>",
            f"<b>Bids:</b> {self.bid_count}",
        ]
        price = self._format_price()
        if price:
            parts.append(f"<b>Budget:</b> {price}")
        if self.duration:
            parts.append(f"<b>Duration:</b> {self.duration} days")
        if self.skills:
            skills = ", ".join(self.skills[:8])
            parts.append(f"<b>Skills:</b> {html.escape(skills)}")
        if self.url:
            parts.append(f'<a href="{self.url}">View on Freelancer</a>')
        return "\n".join(parts)

    def details_html(self) -> str:
        return (
            f"<b>{html.escape(self.title)}</b>\n"
            f"<b>Job ID:</b> <code>{self.project_id}</code>\n"
            f"{html.escape(self.full_description or self.preview_description)}\n\n"
            f"<b>Budget:</b> {self._format_price()}\n"
            f"<b>Job type:</b> {html.escape(self.job_type.title())}\n"
            f"<b>Duration:</b> {self.duration or 'n/a'} days\n"
            f"<b>Skills:</b> {html.escape(', '.join(self.skills)) if self.skills else 'not provided'}\n"
        )

    def _format_price(self) -> str:
        if self.budget_min and self.budget_max:
            return html.escape(f"{self.currency} {self.budget_min}-{self.budget_max}")
        if self.budget_min:
            return html.escape(f"{self.currency} {self.budget_min}+")
        if self.budget_max:
            return html.escape(f"{self.currency} up to {self.budget_max}")
        return "not listed"


def get_profile_id(access_token: str) -> Optional[int]:
    headers = {"freelancer-oauth-v1": access_token}
    url = f"{API_BASE}/users/0.1/self/"
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code != 200:
        logger.error("Failed to fetch Freelancer profile id: %s %s", resp.status_code, resp.text)
        return None
    data = resp.json()
    result = data.get("result") or {}
    return result.get("id")


def search_jobs(
    query: str = "Flutter developer",
    skills: Optional[List[str]] = None,
    budget_minimum: Optional[float] = None,
    budget_maximum: Optional[float] = None,
    min_hourly_rate: Optional[float] = None,
    max_hourly_rate: Optional[float] = None,
    limit: int = 10,
    currency: Optional[str] = None,
    full_description: bool = True,
    sort_field: str = "bid_count",
    reverse_sort: bool = True,
) -> List[FreelancerJob]:
    token = load_token()
    headers = {"Authorization": f"Bearer {token}"}

    params: Dict[str, Any] = {
        "query": query,
        "limit": limit,
        "full_description": str(full_description).lower(),
        "sort_field": sort_field,
        "reverse_sort": str(reverse_sort).lower(),
    }

    if budget_minimum is not None:
        params["min_price"] = budget_minimum
    if budget_maximum is not None:
        params["max_price"] = budget_maximum
    if min_hourly_rate is not None:
        params["min_hourly_rate"] = min_hourly_rate
    if max_hourly_rate is not None:
        params["max_hourly_rate"] = max_hourly_rate
    if skills:
        params["jobs[]"] = skills
    if currency:
        params["currency"] = currency

    url = f"{API_BASE}/projects/active/"
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    results: List[FreelancerJob] = []
    if resp.status_code != 200:
        logger.error("Error searching jobs: %s %s", resp.status_code, resp.text)
        return results

    data = resp.json()
    projects = []
    if "projects" in data:
        projects = data["projects"]
    elif "result" in data and "projects" in data["result"]:
        projects = data["result"]["projects"]

    for project in projects:
        upgrades = project.get("upgrades", {})
        if upgrades.get("NDA") or upgrades.get("fulltime"):
            continue
        job_obj = FreelancerJob.from_dict(project)
        results.append(job_obj)
    return results[:limit]


def create_bid(
    project_id: int,
    amount: float,
    period: int,
    milestone_percentage: float,
    description: str = "",
) -> (bool, str):
    """
    Create a bid on Freelancer project. Returns tuple(success flag, message).
    """

    access_token = load_token()
    profile_id = get_profile_id(access_token)
    if not profile_id:
        return False, "Unable to resolve Freelancer profile id"

    url = f"{API_BASE}/bids/"
    headers = {
        "freelancer-oauth-v1": access_token,
        "Content-Type": "application/json",
    }
    payload = {
        "project_id": project_id,
        "amount": amount,
        "period": period,
        "milestone_percentage": milestone_percentage,
        "description": description,
        "bidder_id": profile_id,
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    data = resp.json() if resp.content else {}

    if resp.status_code == 200 and data.get("status") == "success":
        return True, "success"
    logger.error("Failed to place bid: %s %s", resp.status_code, resp.text)
    return False, resp.text or "Unknown error"
