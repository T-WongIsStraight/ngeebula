from __future__ import annotations
from typing import Any
from urllib.parse import urlsplit
import requests

class ApiClientError(RuntimeError):
    """The frontend could not get a usable response from FastAPI."""

class ApiClient:
    def __init__(self, base_url: str, timeout_seconds: float = 15.0) -> None:
        self.base_url = base_url.strip().rstrip('/')
        self.timeout_seconds = timeout_seconds

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = urlsplit(self.base_url)
        if url.scheme not in ('http', 'https') or not url.netloc:
            raise ApiClientError('Enter a running FastAPI server URL beginning with http:// or https://.')
        timeout = kwargs.pop('timeout', (5, self.timeout_seconds))
        try:
            response = requests.request(method, self.base_url + path, timeout=timeout, **kwargs)
            if response.status_code >= 400:
                try:
                    detail = response.json().get('detail', 'Request failed.')
                except (ValueError, AttributeError):
                    detail = 'Backend returned an error. Check its server logs.'
                raise ApiClientError(f'Backend HTTP {response.status_code}: {detail}')
            return response.json()
        except requests.Timeout as exc:
            raise ApiClientError('Backend request timed out. For a scheduling request, refresh before retrying: the server may still be working.') from exc
        except requests.ConnectionError as exc:
            raise ApiClientError('Cannot connect to FastAPI. Start the backend and check its URL. On Streamlit Cloud, localhost points to Streamlit, not your laptop.') from exc
        except (requests.RequestException, ValueError) as exc:
            raise ApiClientError('Could not read a valid response from the backend.') from exc

    def get_gantt_data(self) -> list[dict]:
        data = self._request('GET', '/dashboard/gantt')
        if not isinstance(data, list):
            raise ApiClientError('Unexpected response from /dashboard/gantt.')
        return data

    def get_alerts(self) -> list[dict]:
        data = self._request('GET', '/alerts/')
        return data if isinstance(data, list) else []

    def get_audit_logs(self) -> list[dict]:
        data = self._request('GET', '/audit-logs/')
        return data if isinstance(data, list) else []

    def propose_schedule(self) -> dict:
        data = self._request('POST', '/schedule/propose', timeout=(5, 60))
        if not isinstance(data, dict):
            raise ApiClientError('Unexpected scheduling response.')
        return data

    def update_job_status(self, job_id: int, payload: dict) -> dict:
        return self._request('PATCH', f'/checklist/{job_id}', json=payload)

    def submit_approval(self, job_id: int, payload: dict) -> dict:
        return self._request('POST', f'/approval/{job_id}', json=payload)
