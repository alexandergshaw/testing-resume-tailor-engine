"""Curated skills taxonomy: longest-match n-gram scanning with canonical casing."""
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .normalize import Token, normalize_phrase
from ..paths import TAXONOMY_PATH

CATEGORIES = ("technology", "tool_platform", "methodology", "soft_skill", "certification", "domain")


@dataclass(frozen=True)
class TaxEntry:
    canonical: str
    category: str


class Taxonomy:
    def __init__(self, path: Path = TAXONOMY_PATH):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self._alias_map: dict[str, TaxEntry] = {}
        self.max_n = 1
        for raw in data["entries"]:
            entry = TaxEntry(canonical=raw["canonical"], category=raw["category"])
            aliases = list(raw.get("aliases", []))
            if raw.get("match_canonical", True):
                aliases.append(raw["canonical"])
            for alias in aliases:
                norm = normalize_phrase(alias)
                if norm:
                    self._alias_map[norm] = entry
                    self.max_n = max(self.max_n, norm.count(" ") + 1)

    def match_segment(self, tokens: list[Token]) -> tuple[list[TaxEntry], list[bool]]:
        """Find taxonomy entries in one segment, longest n-gram first.
        Returns (matched entries, per-token consumed flags)."""
        matches: list[TaxEntry] = []
        consumed = [False] * len(tokens)
        for n in range(min(self.max_n, len(tokens)), 0, -1):
            for i in range(len(tokens) - n + 1):
                if any(consumed[i:i + n]):
                    continue
                gram = " ".join(t.lower for t in tokens[i:i + n])
                entry = self._alias_map.get(gram)
                if entry is not None:
                    matches.append(entry)
                    for j in range(i, i + n):
                        consumed[j] = True
        return matches, consumed


@lru_cache(maxsize=1)
def default_taxonomy() -> Taxonomy:
    return Taxonomy()
