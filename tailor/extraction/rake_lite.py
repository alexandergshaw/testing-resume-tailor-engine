"""Minimal RAKE: stopword-delimited candidate phrases scored by word degree/frequency.

Catches important multi-word topics the taxonomy doesn't know about.
"""
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

from .normalize import Token
from ..paths import STOPWORDS_PATH


@lru_cache(maxsize=1)
def load_stopwords(path: Path = STOPWORDS_PATH) -> frozenset[str]:
    words = Path(path).read_text(encoding="utf-8").split()
    return frozenset(w.strip().lower() for w in words if w.strip())


class RakeAccumulator:
    """Feed it candidate token runs (already split at stopwords/punctuation/
    taxonomy matches), then ask for the top-scored multi-word phrases."""

    def __init__(self):
        self._freq: Counter[str] = Counter()
        self._degree: Counter[str] = Counter()
        self._phrase_count: Counter[str] = Counter()
        self._phrase_weight: defaultdict[str, float] = defaultdict(float)
        self._surface_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
        self._first_seen: dict[str, int] = {}
        self._order = 0

    def add_candidate(self, tokens: list[Token], weight: float) -> None:
        words = [t.lower for t in tokens]
        if not words:
            return
        for w in words:
            self._freq[w] += 1
            self._degree[w] += len(words) - 1
        key = " ".join(words)
        surface = " ".join(t.surface for t in tokens)
        self._phrase_count[key] += 1
        self._phrase_weight[key] += weight
        self._surface_counts[key][surface] += 1
        if key not in self._first_seen:
            self._first_seen[key] = self._order
        self._order += 1

    def top_phrases(self, limit: int = 12, min_words: int = 2, max_words: int = 4):
        """Returns list of (display_text, score, count) for the best multi-word
        phrases, deterministically ordered."""
        results = []
        for key, count in self._phrase_count.items():
            words = key.split(" ")
            if not (min_words <= len(words) <= max_words):
                continue
            if any(w.isdigit() for w in words):
                continue
            rake_score = sum(self._degree[w] / self._freq[w] for w in words)
            avg_weight = self._phrase_weight[key] / count
            score = rake_score * avg_weight
            # Display casing: most frequent surface form (max keeps the
            # first-inserted on ties, i.e. the earliest-seen form).
            surfaces = self._surface_counts[key]
            display = max(surfaces, key=surfaces.__getitem__)
            results.append((display, score, count, key))
        results.sort(key=lambda r: (-r[1], r[3]))
        return [(d, s, c) for d, s, c, _ in results[:limit]]
