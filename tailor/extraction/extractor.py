"""Deterministic keyword extraction pipeline.

Pass 1: taxonomy n-gram matching (canonical casing, categories).
Pass 2: RAKE-lite phrases from whatever the taxonomy didn't consume.
Pass 3: section weighting (title lines x3, requirements-style sections x2).

Output is sorted by (-score, canonical) so repeated runs are identical.
"""
import re
from dataclasses import dataclass

from .normalize import split_segments
from .rake_lite import RakeAccumulator, load_stopwords
from .taxonomy import Taxonomy, default_taxonomy

_SECTION_RE = re.compile(
    r"requirement|qualification|must.have|what.you.ll|responsibilit|skills|who.you.are",
    re.IGNORECASE,
)

_BULLET_PREFIXES = ("-", "*", "•", "·", "–", "—")

TITLE_WEIGHT = 3.0
SECTION_WEIGHT = 2.0
BASE_WEIGHT = 1.0


@dataclass(frozen=True)
class Keyword:
    canonical: str
    category: str
    score: float
    count: int


def _is_header_like(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 60:
        return False
    if stripped.startswith(_BULLET_PREFIXES):
        return False
    if stripped.endswith((".", "!", "?")) and not stripped.endswith(("etc.", "+.")):
        return False
    return len(stripped.split()) <= 8


def extract_keywords(text: str, taxonomy: Taxonomy | None = None) -> list[Keyword]:
    taxonomy = taxonomy or default_taxonomy()
    stopwords = load_stopwords()

    tax_score: dict = {}
    tax_count: dict = {}
    rake = RakeAccumulator()

    weight = BASE_WEIGHT
    nonempty_seen = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        nonempty_seen += 1
        if _is_header_like(line):
            weight = SECTION_WEIGHT if _SECTION_RE.search(line) else BASE_WEIGHT
        line_weight = TITLE_WEIGHT if nonempty_seen <= 3 else weight

        for segment in split_segments(line):
            matches, consumed = taxonomy.match_segment(segment)
            for entry in matches:
                tax_score[entry] = tax_score.get(entry, 0.0) + line_weight
                tax_count[entry] = tax_count.get(entry, 0) + 1

            # Unconsumed, non-stopword runs become RAKE candidates.
            run = []
            for token, used in zip(segment, consumed):
                if used or token.lower in stopwords or token.lower.isdigit():
                    if run:
                        rake.add_candidate(run, line_weight)
                        run = []
                else:
                    run.append(token)
            if run:
                rake.add_candidate(run, line_weight)

    keywords = [
        Keyword(canonical=e.canonical, category=e.category,
                score=round(score, 4), count=tax_count[e])
        for e, score in tax_score.items()
    ]
    # RAKE phrases go in their own 'topic' category: useful context on the
    # review screen, but too noisy to auto-insert into a resume.
    for display, score, count in rake.top_phrases():
        keywords.append(Keyword(canonical=display, category="topic",
                                score=round(score, 4), count=count))

    keywords.sort(key=lambda k: (-k.score, k.canonical.lower()))
    return keywords


def keywords_by_category(keywords: list[Keyword]) -> dict[str, list[Keyword]]:
    grouped: dict[str, list[Keyword]] = {}
    for kw in keywords:
        grouped.setdefault(kw.category, []).append(kw)
    return grouped
