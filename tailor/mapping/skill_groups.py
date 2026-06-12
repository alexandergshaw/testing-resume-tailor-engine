"""Posting-driven skills section: rank curated theme groups against the
extracted keywords; the winners supply both the heading and the row beneath it.
"""
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..extraction.extractor import Keyword
from ..paths import SKILL_GROUPS_PATH

MAX_KEYWORDS_PER_GROUP = 8
MIN_KEYWORDS_PER_GROUP = 2


@dataclass(frozen=True)
class SkillGroupDef:
    heading: str
    keywords: frozenset[str]   # lowercase canonical names
    categories: frozenset[str]


@dataclass(frozen=True)
class PlannedGroup:
    heading: str
    keywords: tuple[Keyword, ...]

    @property
    def row_text(self) -> str:
        return ", ".join(k.canonical for k in self.keywords)


def load_group_defs(path: Path = SKILL_GROUPS_PATH) -> list[SkillGroupDef]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        SkillGroupDef(
            heading=str(raw["heading"]),
            keywords=frozenset(str(k).lower() for k in raw.get("keywords", [])),
            categories=frozenset(str(c) for c in raw.get("categories", [])),
        )
        for raw in data["groups"]
    ]


@lru_cache(maxsize=1)
def default_group_defs() -> tuple[SkillGroupDef, ...]:
    return tuple(load_group_defs())


def _matches(group: SkillGroupDef, keyword: Keyword, defs: list[SkillGroupDef]) -> bool:
    """A keyword can match by explicit listing or by category — but if ANY
    group lists it explicitly, only explicitly-listing groups may take it."""
    name = keyword.canonical.lower()
    if name in group.keywords:
        return True
    if keyword.category in group.categories:
        return not any(name in other.keywords for other in defs)
    return False


def build_group_plan(keywords: list[Keyword],
                     defs: list[SkillGroupDef] | None = None) -> list[PlannedGroup]:
    """Deterministic: score groups, rank by (-score, file order), then greedily
    claim keywords in rank order. Groups left with fewer than
    MIN_KEYWORDS_PER_GROUP release their claims and drop out."""
    defs = list(defs) if defs is not None else list(default_group_defs())
    pool = [k for k in keywords if k.category != "topic"]

    scored = []
    for index, group in enumerate(defs):
        score = sum(k.score for k in pool if _matches(group, k, defs))
        if score > 0:
            scored.append((score, index, group))
    scored.sort(key=lambda item: (-item[0], item[1]))

    claimed: set[str] = set()
    planned: list[PlannedGroup] = []
    for _, index, group in scored:
        picked = []
        for kw in pool:  # pool keeps the extractor's (-score, name) order
            if kw.canonical.lower() in claimed:
                continue
            if _matches(group, kw, defs):
                picked.append(kw)
                if len(picked) == MAX_KEYWORDS_PER_GROUP:
                    break
        if len(picked) >= MIN_KEYWORDS_PER_GROUP:
            claimed.update(k.canonical.lower() for k in picked)
            planned.append(PlannedGroup(heading=group.heading, keywords=tuple(picked)))
    return planned
