from __future__ import annotations

from typing import Any

import requests


class ApiClientError(RuntimeError):
    """Raised when the frontend cannot get a usable response from FastAPI."""


class ApiClient:
    def __init__(self, base_url: str, timeout_seconds: float = 4.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = requests.request(
                method,
                f"{self.base_url}{path}",
                timeout=self.timeout_seconds,
                **kwargs,
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ApiClientError(str(exc)) from exc

    def get_gantt_data(self) -> list[dict]:
        payload = self._request("GET", "/dashboard/gantt")
        if not isinstance(payload, list):
            raise ApiClientError("Unexpected response from /dashboard/gantt.")
        return payload

    def get_alerts(self) -> list[dict]:
        payload = self._request("GET", "/alerts/")
        return payload if isinstance(payload, list) else []

    def get_audit_logs(self) -> list[dict]:
        payload = self._request("GET", "/audit-logs/")
        return payload if isinstance(payload, list) else []

    def propose_schedule(self) -> dict:
        payload = self._request("POST", "/schedule/propose")
        if not isinstance(payload, dict):
            raise ApiClientError("Unexpected response from /schedule/propose.")
        return payload

    def update_job_status(self, job_id: int, payload: dict) -> dict:
        result = self._request("PATCH", f"/checklist/{job_id}", json=payload)
        if not isinstance(result, dict):
            raise ApiClientError("Unexpected checklist response.")
        return result

    def submit_approval(self, job_id: int, payload: dict) -> dict:
        result = self._request("POST", f"/approval/{job_id}", json=payload)
        if not isinstance(result, dict):
            raise ApiClientError("Unexpected approval response.")
        return result
