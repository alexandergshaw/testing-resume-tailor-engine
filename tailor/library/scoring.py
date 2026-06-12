"""Deterministic relevance scoring of content library entries against job keywords.

score = cosine(tfidf(entry text+tags), tfidf(job keywords weighted by extraction
score)) + 0.5 * tag-overlap fraction. IDF corpus = the library entries.
"""
import math
from collections import Counter

from ..extraction.extractor import Keyword
from ..extraction.normalize import normalize_phrase
from .store import LibraryEntry

TAG_BONUS = 0.5


def _entry_tokens(entry: LibraryEntry) -> list[str]:
    tokens = normalize_phrase(entry.text).split()
    for tag in entry.tags:
        tokens.extend(normalize_phrase(tag).split())
    return [t for t in tokens if t]


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(weight * b.get(term, 0.0) for term, weight in a.items())
    if dot == 0.0:
        return 0.0
    norm_a = math.sqrt(sum(w * w for w in a.values()))
    norm_b = math.sqrt(sum(w * w for w in b.values()))
    return dot / (norm_a * norm_b)


def score_entries(entries: list[LibraryEntry], keywords: list[Keyword]) -> dict[str, float]:
    """Returns entry id -> relevance score."""
    # IDF over the library corpus.
    doc_freq: Counter[str] = Counter()
    entry_tokens: dict[str, list[str]] = {}
    for entry in entries:
        tokens = _entry_tokens(entry)
        entry_tokens[entry.id] = tokens
        doc_freq.update(set(tokens))
    n_docs = max(len(entries), 1)

    def idf(term: str) -> float:
        return math.log((n_docs + 1) / (doc_freq.get(term, 0) + 1)) + 1.0

    query: dict[str, float] = {}
    keyword_names = set()
    for kw in keywords:
        norm = normalize_phrase(kw.canonical)
        keyword_names.add(norm)
        for term in norm.split():
            query[term] = query.get(term, 0.0) + kw.score * idf(term)

    scores: dict[str, float] = {}
    for entry in entries:
        counts = Counter(entry_tokens[entry.id])
        vector = {term: count * idf(term) for term, count in counts.items()}
        score = _cosine(query, vector)

        if entry.tags:
            tags_norm = {normalize_phrase(t) for t in entry.tags}
            overlap = len(tags_norm & keyword_names) / len(tags_norm)
            score += TAG_BONUS * overlap
        scores[entry.id] = round(score, 6)
    return scores
