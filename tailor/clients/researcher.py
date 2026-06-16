"""Client for the general-purpose Researcher API.

Prefers the batch endpoint so the composer makes one call per request rather
than one per keyword/emphasis.
"""
import os

from .base import DownstreamError, get_json, post_json


class ResearcherClient:
    def __init__(self, base_url: str, api_key: str | None = None, timeout: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "ResearcherClient | None":
        url = os.environ.get("RESEARCHER_API_URL")
        if not url:
            return None
        return cls(url, os.environ.get("RESEARCHER_API_KEY"))

    def batch(self, requests: list[dict]) -> list[dict]:
        """Each request is {intent, params}. Returns one envelope per request,
        in order. A single failed sub-request does not fail the batch."""
        body = post_json("researcher", f"{self.base_url}/v1/research/batch",
                         {"requests": requests}, api_key=self.api_key, timeout=self.timeout)
        results = body.get("results")
        if not isinstance(results, list):
            raise DownstreamError("researcher", "batch response missing 'results' array")
        return results

    def research(self, intent: str, params: dict) -> dict:
        return post_json("researcher", f"{self.base_url}/v1/research",
                         {"intent": intent, "params": params},
                         api_key=self.api_key, timeout=self.timeout)

    def health(self) -> dict:
        return get_json("researcher", f"{self.base_url}/v1/health",
                        api_key=self.api_key, timeout=self.timeout)
