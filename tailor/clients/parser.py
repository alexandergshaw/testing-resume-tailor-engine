"""Client for the general-purpose Parser API (text -> emphases + keywords)."""
import os

from .base import get_json, post_json


class ParserClient:
    def __init__(self, base_url: str, api_key: str | None = None, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "ParserClient | None":
        url = os.environ.get("PARSER_API_URL")
        if not url:
            return None
        return cls(url, os.environ.get("PARSER_API_KEY"))

    def parse(self, text: str, max_keywords: int = 30) -> dict:
        return post_json("parser", f"{self.base_url}/api/parse",
                         {"text": text, "max_keywords": max_keywords},
                         api_key=self.api_key, timeout=self.timeout)

    def health(self) -> dict:
        return get_json("parser", f"{self.base_url}/api/health",
                        api_key=self.api_key, timeout=self.timeout)
