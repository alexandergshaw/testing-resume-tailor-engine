"""Map Parser API v1.0.0 (lens-based) output into the local Keyword model.

The Parser is general-purpose: its `field`/`sector` emphasis lenses type the doc
by domain axis, and its `technologies` lexicon lists curated tech terms. Neither
is the resume skill-class split the mapping layer needs, so the composer
classifies each keyword here, using the local taxonomy as a classification
lexicon (canonical/alias -> category).
"""
from .extractor import Keyword
from .taxonomy import default_taxonomy

# Fallback when a keyword isn't in the classification lexicon: nudge by the
# Parser's emphasis id, else treat as a domain term.
_EMPHASIS_CATEGORY = {
    "software_engineering": "technology",
    "web_development": "technology",
    "machine_learning": "technology",
    "devops": "tool_platform",
    "cybersecurity": "domain",
    "data_science": "domain",
}

# The technologies lexicon carries no score (it's ordered by frequency), so we
# synthesize a descending score: confirmed techs rank high without all tying,
# and max-dedup keeps a real keyword score where the two lenses overlap.
TECH_BASE = 0.85
TECH_STEP = 0.02
TECH_FLOOR = 0.30


def classify_keyword(display: str, related_emphasis_id: str | None = None) -> str:
    category = default_taxonomy().classify(display)
    if category:
        return category
    return _EMPHASIS_CATEGORY.get(related_emphasis_id or "", "domain")


def _related_id(item: dict) -> str | None:
    related = item.get("related")
    return related.get("id") if isinstance(related, dict) else None


def _emphasis_top(lens: dict | None) -> dict | None:
    return lens.get("top") if isinstance(lens, dict) else None


def _merge(best: dict, display: str, category: str, score: float) -> None:
    existing = best.get(display)
    if existing is None or score > existing.score:
        best[display] = Keyword(canonical=display, category=category,
                                score=score, count=1)


def keywords_from_parser(parse: dict) -> tuple[list[Keyword], dict]:
    """Returns (keywords, emphases). Keywords use the Parser's canonical
    `display` casing and a locally-assigned skill category, drawn from both the
    `keywords` and `technologies` lenses; ordering is the deterministic
    (-score, canonical)."""
    results = parse.get("results", {})
    best: dict[str, Keyword] = {}

    # keywords lens: RAKE/lexicon keyphrases with real [0,1] scores.
    for item in results.get("keywords", {}).get("items", []):
        display = (item.get("display") or item.get("term") or "").strip()
        if not display:
            continue
        score = round(float(item.get("score", 0.0)), 4)
        _merge(best, display, classify_keyword(display, _related_id(item)), score)

    # technologies lens: curated tech terms (no score) -> descending synthetic.
    for rank, item in enumerate(results.get("technologies", {}).get("matched", [])):
        display = (item.get("display") or item.get("term") or "").strip()
        if not display:
            continue
        score = round(max(TECH_FLOOR, TECH_BASE - TECH_STEP * rank), 4)
        _merge(best, display, classify_keyword(display, _related_id(item)), score)

    keywords = sorted(best.values(), key=lambda k: (-k.score, k.canonical.lower()))

    field = results.get("field")
    emphases = {
        "primary": _emphasis_top(field),                 # field.top (was "primary")
        "secondary": _emphasis_top(results.get("sector")),  # sector.top (was "secondary")
        "list": field.get("ranked", []) if isinstance(field, dict) else [],
    }
    return keywords, emphases
