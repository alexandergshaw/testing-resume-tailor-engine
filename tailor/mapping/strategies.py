"""Turn scanned placeholders into proposed values using the resolved strategy."""
import json
import re
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

from ..docxio.scanner import Placeholder
from ..extraction.extractor import Keyword
from ..library.scoring import score_entries
from ..library.store import LibraryEntry
from ..paths import OUTCOME_PHRASES_PATH
from .registry import Strategy, resolve
from .skill_groups import build_group_plan

# Legacy fallback when the posting can't fill all five skills rows from groups.
SKILLS_CATEGORY_ORDER = ("technology", "tool_platform", "methodology", "soft_skill", "domain")
SKILLS_PER_LINE = 8

PHRASE_NOTE = "generated from posting wording — verify it reflects real work"

# Topics that are really the job title / role wording, not a system or domain.
_ROLE_WORD_RE = re.compile(
    r"\b(senior|junior|lead|principal|staff|engineer|engineers|engineering"
    r"|developer|developers|manager|managers|director|analyst|analysts"
    r"|architect|architects|consultant|specialist|candidate)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Proposal:
    value: str
    strategy: Strategy
    note: str = ""  # where the value came from, shown on the review screen
    candidates: tuple[str, ...] = ()  # ranked bank alternatives for this slot


@lru_cache(maxsize=1)
def load_outcome_phrases(path: Path = OUTCOME_PHRASES_PATH) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        "by_keyword": {str(k): v for k, v in data.get("by_keyword", {}).items()},
        "by_category": {str(k): v for k, v in data.get("by_category", {}).items()},
    }


def _midcase(phrase: str) -> str:
    """Lower-case Title-Case words for mid-sentence use, but leave acronyms
    and mixed-case tokens (BI, PowerBI) alone."""
    return " ".join(
        word.lower() if re.fullmatch(r"[A-Z][a-z]+", word) else word
        for word in phrase.split(" ")
    )


class Proposer:
    """Stateful: shared keyword pools and the no-repeat rule for library
    entries require proposing in document order."""

    def __init__(self, keywords: list[Keyword], profile: dict[str, str],
                 library: list[LibraryEntry]):
        self._keywords = keywords
        self._profile = profile
        self._library = library
        self._scores = score_entries(library, keywords)
        self._used_entry_ids: set[str] = set()
        self._pool_positions: dict[tuple[str, ...], int] = {}
        self._group_plan = build_group_plan(keywords)
        self._header_index = 0
        # Topics usable mid-sentence: 3+ words weeds out company/location
        # scraps ("Group Omaha") and bare gerunds ("software development").
        self._topics = [k.canonical for k in keywords
                        if k.category == "topic"
                        and len(k.canonical.split()) >= 3
                        and not _ROLE_WORD_RE.search(k.canonical)]
        self._topic_position = 0
        self._outcome_positions: dict[str, int] = {}

    def propose(self, placeholder: Placeholder) -> Proposal:
        proposal = self._dispatch(placeholder)
        candidates = self._bank_candidates(placeholder.name)
        if candidates:
            proposal = replace(proposal, candidates=candidates)
        return proposal

    def _bank_candidates(self, name: str, limit: int = 12) -> tuple[str, ...]:
        """Every bank entry offering this slot, most relevant to the posting
        first — surfaced as a dropdown on the review screen."""
        matching = [e for e in self._library if name in e.slots]
        matching.sort(key=lambda e: (-self._scores[e.id], e.id))
        return tuple(e.text for e in matching[:limit])

    def _dispatch(self, placeholder: Placeholder) -> Proposal:
        strategy, params = resolve(placeholder.name)
        if strategy is Strategy.PROFILE:
            return self._propose_profile(placeholder)
        if strategy is Strategy.KEYWORD_JOIN:
            return self._propose_keywords(params["categories"], params["n"])
        if strategy is Strategy.KEYWORD_PHRASE:
            return self._propose_phrase(params["kind"])
        if strategy is Strategy.SKILLS_DISTRIBUTE:
            return self._propose_skills(placeholder.occurrence)
        if strategy is Strategy.SKILLS_HEADER:
            return self._propose_header(placeholder)
        if strategy is Strategy.LIBRARY_MATCH:
            return self._propose_library(placeholder.name)
        return Proposal(value="", strategy=Strategy.MANUAL, note="no rule matched — fill in by hand")

    # ----- profile -----

    def _propose_profile(self, placeholder: Placeholder) -> Proposal:
        value = self._profile.get(placeholder.name)
        if value is None:
            return Proposal(value="", strategy=Strategy.MANUAL,
                            note=f"add '{placeholder.name}' to data/profile.json to autofill")
        return Proposal(value=value, strategy=Strategy.PROFILE, note="from profile.json")

    # ----- keyword pools -----

    def _category_pool(self, categories: tuple[str, ...]) -> list[Keyword]:
        wanted = set(categories)
        return [k for k in self._keywords if k.category in wanted]

    def _take_from_pool(self, categories: tuple[str, ...], n: int) -> list[Keyword]:
        pool = self._category_pool(categories)
        if not pool:
            return []
        position = self._pool_positions.get(categories, 0)
        if position >= len(pool):
            position = 0  # every keyword handed out once; start reusing
        picked = pool[position:position + n]
        self._pool_positions[categories] = position + len(picked)
        return picked

    def _propose_keywords(self, categories: tuple[str, ...], n: int) -> Proposal:
        picked = self._take_from_pool(categories, n)
        if not picked:
            return Proposal(value="", strategy=Strategy.MANUAL,
                            note=f"no {'/'.join(categories)} keywords found in posting")
        return Proposal(value=", ".join(k.canonical for k in picked),
                        strategy=Strategy.KEYWORD_JOIN,
                        note=f"top {'/'.join(categories)} keywords")

    # ----- posting-driven phrases (Projects section) -----

    def _next_topic(self) -> str | None:
        # Unlike keyword pools, topics never wrap: a posting phrase repeated
        # across project rows reads like copy-paste, so use each once.
        if self._topic_position >= len(self._topics):
            return None
        topic = self._topics[self._topic_position]
        self._topic_position += 1
        return _midcase(topic)

    def _next_outcome_phrase(self, field: str) -> str | None:
        """Walk the keyword list (already in score order) for the next keyword
        with a curated phrase; falls back to the top keyword's category default."""
        phrases = load_outcome_phrases()
        position = self._outcome_positions.get(field, 0)
        pool = [k for k in self._keywords if k.category != "topic"]
        for offset, kw in enumerate(pool[position:]):
            mapped = phrases["by_keyword"].get(kw.canonical)
            if mapped and mapped.get(field):
                self._outcome_positions[field] = position + offset + 1
                return mapped[field]
        if pool:
            default = phrases["by_category"].get(pool[0].category, {})
            return default.get(field)
        return None

    def _propose_phrase(self, kind: str) -> Proposal:
        value = self._build_phrase(kind)
        if value is None:
            return Proposal(value="", strategy=Strategy.MANUAL,
                            note="posting had too few keywords to compose this")
        return Proposal(value=value, strategy=Strategy.KEYWORD_PHRASE, note=PHRASE_NOTE)

    def _build_phrase(self, kind: str) -> str | None:
        if kind == "scope":
            haystack = " ".join(k.canonical.lower() for k in self._keywords)
            if "cross functional" in haystack.replace("-", " ") and "enterprise" not in haystack:
                return "Cross-Functional"
            return "Enterprise"

        if kind == "type":
            picked = self._take_from_pool(("domain", "methodology"), 1)
            return f"{picked[0].canonical} Initiative" if picked else None

        if kind == "capability_kw":
            picked = self._take_from_pool(("domain", "technology"), 1)
            return picked[0].canonical if picked else None

        if kind == "outcome":
            return self._next_outcome_phrase("outcome")

        if kind == "capability":
            return self._next_outcome_phrase("capability")

        if kind == "solution":
            tech = self._take_from_pool(("technology", "tool_platform"), 2)
            if not tech:
                return None
            topic = self._next_topic()
            if topic:
                return f"a {tech[0].canonical}-based solution supporting the {topic}"
            if len(tech) > 1:
                return f"a {tech[0].canonical} and {tech[1].canonical} solution"
            return f"a {tech[0].canonical}-based solution"

        if kind == "existing_system":
            topic = self._next_topic()
            if topic:
                return f"the {topic}"
            # Action-style domain keywords ("Legacy Modernization", "Cloud
            # Migration") read badly as the thing being modernized — skip them.
            for _ in range(len(self._category_pool(("domain",)))):
                picked = self._take_from_pool(("domain",), 1)
                if not picked:
                    break
                name = picked[0].canonical.lower()
                if not any(w in name for w in ("legacy", "modernization", "migration")):
                    return f"legacy {_midcase(picked[0].canonical)} workflows"
            return None

        return None

    # ----- skills section (groups with legacy fallback) -----

    def _propose_header(self, placeholder: Placeholder) -> Proposal:
        index = self._header_index
        self._header_index += 1
        if index < len(self._group_plan):
            return Proposal(value=self._group_plan[index].heading,
                            strategy=Strategy.SKILLS_HEADER,
                            note="heading driven by posting emphasis")
        return self._propose_profile(placeholder)  # legacy static label

    def _propose_skills(self, occurrence: int) -> Proposal:
        if occurrence < len(self._group_plan):
            group = self._group_plan[occurrence]
            return Proposal(value=group.row_text,
                            strategy=Strategy.SKILLS_DISTRIBUTE,
                            note=f"keywords matching '{group.heading}'")
        # Legacy fallback: fixed category order.
        if occurrence >= len(SKILLS_CATEGORY_ORDER):
            return Proposal(value="", strategy=Strategy.MANUAL,
                            note="more skills slots than groups or categories")
        category = SKILLS_CATEGORY_ORDER[occurrence]
        pool = [k for k in self._keywords if k.category == category][:SKILLS_PER_LINE]
        if not pool:
            return Proposal(value="", strategy=Strategy.MANUAL,
                            note=f"no {category} keywords found in posting")
        return Proposal(value=", ".join(k.canonical for k in pool),
                        strategy=Strategy.SKILLS_DISTRIBUTE,
                        note=f"top {category} keywords")

    # ----- content library -----

    def _propose_library(self, name: str) -> Proposal:
        candidates = [e for e in self._library
                      if name in e.slots and e.id not in self._used_entry_ids]
        if not candidates:
            return Proposal(value="", strategy=Strategy.MANUAL,
                            note=f"no unused content_library.json entry offers slot '{name}'")
        best = min(candidates, key=lambda e: (-self._scores[e.id], e.id))
        self._used_entry_ids.add(best.id)
        return Proposal(value=best.text, strategy=Strategy.LIBRARY_MATCH,
                        note=f"library entry '{best.id}'")


def propose_all(placeholders: list[Placeholder], keywords: list[Keyword],
                profile: dict[str, str], library: list[LibraryEntry]) -> dict[str, Proposal]:
    """Returns placeholder.key -> Proposal, processed in document order."""
    proposer = Proposer(keywords, profile, library)
    return {ph.key: proposer.propose(ph) for ph in placeholders}
