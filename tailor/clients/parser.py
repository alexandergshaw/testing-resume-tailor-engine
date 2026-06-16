"""Client for the general-purpose Parser API (v1.0.0, lens-based)."""
import os

from .base import get_json, post_json

# `targets` is restrictive (only requested lenses are returned) and the
# `technologies` lexicon is NOT a default lens, so request all four explicitly.
DEFAULT_TARGETS = ["field", "sector", "technologies", "keywords"]


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

    def parse(self, text: str, targets: list[str] | None = None,
              max_keywords: int = 40) -> dict:
        return post_json("parser", f"{self.base_url}/api/parse",
                         {"text": text, "max_keywords": max_keywords,
                          "targets": list(targets or DEFAULT_TARGETS)},
                         api_key=self.api_key, timeout=self.timeout)

    def health(self) -> dict:
        return get_json("parser", f"{self.base_url}/api/health",
                        api_key=self.api_key, timeout=self.timeout)
