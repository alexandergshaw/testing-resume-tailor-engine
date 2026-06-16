"""Map Parser API output into the local Keyword model the mapping layer expects.

The Parser is general-purpose: it types terms by domain emphasis (field/sector),
not by resume skill class. So the composer classifies each keyword here, using
the local taxonomy as a classification lexicon (canonical/alias -> category).
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


def classify_keyword(display: str, related_emphasis_id: str | None = None) -> str:
    category = default_taxonomy().classify(display)
    if category:
        return category
    return _EMPHASIS_CATEGORY.get(related_emphasis_id or "", "domain")


def keywords_from_parser(parse: dict) -> tuple[list[Keyword], dict]:
    """Returns (keywords, emphases). Keywords use the Parser's canonical
    `display` casing and a locally-assigned skill category; ordering is the
    deterministic (-score, canonical)."""
    best: dict[str, Keyword] = {}
    for raw in parse.get("keywords", []):
        display = (raw.get("display") or raw.get("term") or "").strip()
        if not display:
            continue
        category = classify_keyword(display, raw.get("related_emphasis_id"))
        score = round(float(raw.get("score", 0.0)), 4)
        existing = best.get(display)
        if existing is None or score > existing.score:
            best[display] = Keyword(canonical=display, category=category,
                                    score=score, count=1)
    keywords = sorted(best.values(), key=lambda k: (-k.score, k.canonical.lower()))

    emphases = {
        "primary": parse.get("primary"),
        "secondary": parse.get("secondary"),
        "list": parse.get("emphases", []),
    }
    return keywords, emphases
