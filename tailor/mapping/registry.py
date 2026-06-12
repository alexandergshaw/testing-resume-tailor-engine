"""Placeholder name normalization and the name-pattern -> fill-strategy table."""
import re
from enum import Enum


class Strategy(Enum):
    PROFILE = "profile"
    KEYWORD_JOIN = "keywords"
    KEYWORD_PHRASE = "phrase"
    LIBRARY_MATCH = "library"
    SKILLS_DISTRIBUTE = "skills"
    SKILLS_HEADER = "header"
    MANUAL = "manual"


def normalize_name(raw: str) -> str:
    """'{{Role-Specific Expertise }}' -> 'ROLE_SPECIFIC_EXPERTISE'.
    Strips braces, uppercases, collapses every non-alphanumeric run to '_'."""
    name = re.sub(r"^\{+|\}+$", "", raw.strip())
    name = re.sub(r"[^A-Za-z0-9]+", "_", name.upper())
    return name.strip("_")


def _course_topics(match: re.Match) -> dict:
    return {"categories": ("technology", "soft_skill"), "n": int(match.group(1))}


# First match wins. Anything that falls through is MANUAL.
_RULES = [
    (r"^(TOP_|MEDIUM_|LOW_)?RANK$", Strategy.PROFILE, None),
    (r"^YEARS_OF_EXPERIENCE$", Strategy.PROFILE, None),
    (r"^(PRIMARY_FUNCTION|FUNCTION|SPECIALIZATION|SCALE_DESCRIPTOR|USER_SCALE"
     r"|EVENT_SCALE|ENVIRONMENT_TYPES|LEADERSHIP_LEVEL|LEADERSHIP_SCOPE)$",
     Strategy.PROFILE, None),
    (r"^(ROLE_SPECIFIC_EXPERTISE|CORE_PROFESSIONAL_CAPABILITIES"
     r"|METHODS_SYSTEMS_TECHNOLOGIES|LEADERSHIP_DELIVERY_COLLABORATION"
     r"|SUPPORTING_TOOLS_KNOWLEDGE)$", Strategy.SKILLS_HEADER, None),
    (r"^LEADERSHIP_CAPABILITIES$", Strategy.KEYWORD_JOIN,
     {"categories": ("soft_skill",), "n": 3}),
    (r"^(JOB_RELEVANT_TECHNOLOGIES|TECHNICAL_CAPABILITIES|JOB_RELEVANT_SOLUTIONS"
     r"|TECHNICAL_APPROACH)$", Strategy.KEYWORD_JOIN,
     {"categories": ("technology", "tool_platform"), "n": 4}),
    (r"^DELIVERY_PRACTICES$", Strategy.KEYWORD_JOIN,
     {"categories": ("methodology",), "n": 3}),
    (r"^AREA_OF_EMPHASIS$", Strategy.KEYWORD_JOIN,
     {"categories": ("domain",), "n": 1}),
    (r"^(AREAS_OF_EMPHASIS|DOMAIN_CAPABILITIES|SOLUTION_TYPES)$", Strategy.KEYWORD_JOIN,
     {"categories": ("domain",), "n": 2}),
    (r"^LIST_OF_(\d+)_COURSE_TOPICS", Strategy.KEYWORD_JOIN, _course_topics),
    (r"^2_LINES_OF_COMMA_SEPARATED_SKILLS$", Strategy.SKILLS_DISTRIBUTE, None),
    # Posting-driven Projects slots. Exact-anchored so they win over the
    # LIBRARY prefix rule below; metric slots stay with the library.
    (r"^PROJECT_SCOPE$", Strategy.KEYWORD_PHRASE, {"kind": "scope"}),
    (r"^PROJECT_TYPE$", Strategy.KEYWORD_PHRASE, {"kind": "type"}),
    (r"^PRIMARY_CAPABILITY$", Strategy.KEYWORD_PHRASE, {"kind": "capability_kw"}),
    (r"^STRATEGIC_OUTCOME$", Strategy.KEYWORD_PHRASE, {"kind": "outcome"}),
    (r"^PROJECT_SOLUTION$", Strategy.KEYWORD_PHRASE, {"kind": "solution"}),
    (r"^EXISTING_SYSTEM_OR_PROCESS$", Strategy.KEYWORD_PHRASE, {"kind": "existing_system"}),
    (r"^NEW_CAPABILITY$", Strategy.KEYWORD_PHRASE, {"kind": "capability"}),
    (r"^(ACTION|SOLUTION|MEASURABLE|SCOPE|INITIATIVE|STRATEGIC|RESULTING|USERS"
     r"|PROBLEM|BUSINESS|TECHNICAL_OR|PROJECT_|NEW_CAPABILITY|EXISTING_SYSTEM"
     r"|PERFORMANCE_|PRIMARY_CAPABILITY)", Strategy.LIBRARY_MATCH, None),
]

RULES = [(re.compile(rx), strat, params) for rx, strat, params in _RULES]


def resolve(name: str) -> tuple[Strategy, dict]:
    for rx, strategy, params in RULES:
        match = rx.match(name)
        if match:
            if callable(params):
                return strategy, params(match)
            return strategy, dict(params) if params else {}
    return Strategy.MANUAL, {}
