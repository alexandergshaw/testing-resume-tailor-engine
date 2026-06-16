"""Workflow orchestration: pick the keyword source, gather advisory research,
and diff the two workflows for bug-finding during integration.

Determinism boundary: legacy is fully deterministic; composed is deterministic
for document output given (posting, template, profile, library, parser_version).
Research is advisory only — it never enters resume `values`.
"""
from .clients.base import DownstreamError
from .extraction.extractor import Keyword, extract_keywords
from .extraction.source import keywords_from_parser
from .service import propose_for

MAX_RESEARCH_EMPHASES = 4


def get_keywords(posting: str, workflow: str, parser_client=None
                 ) -> tuple[list[Keyword], dict]:
    """Returns (keywords, meta). meta carries workflow, degraded flag + reason,
    and (composed) the Parser emphases. Composed falls back to local extraction
    if the Parser is unconfigured or unreachable, so resume generation never
    hard-fails on a Parser outage."""
    if workflow == "legacy":
        return extract_keywords(posting), {
            "workflow": "legacy", "degraded": False, "emphases": None}

    if parser_client is None:
        return extract_keywords(posting), {
            "workflow": "composed", "degraded": True,
            "reason": "parser not configured; used local extraction",
            "emphases": None}
    try:
        parse = parser_client.parse(posting)
        keywords, emphases = keywords_from_parser(parse)
        if not keywords:  # parser ran but found nothing usable
            return extract_keywords(posting), {
                "workflow": "composed", "degraded": True,
                "reason": "parser returned no keywords; used local extraction",
                "emphases": emphases}
        return keywords, {"workflow": "composed", "degraded": False,
                          "emphases": emphases,
                          "parser_version": parse.get("meta", {}).get("version")}
    except DownstreamError as exc:
        return extract_keywords(posting), {
            "workflow": "composed", "degraded": True,
            "reason": f"parser unavailable ({exc}); used local extraction",
            "emphases": None}


def _emphasis_labels(emphases: dict | None) -> list[str]:
    if not emphases:
        return []
    labels: list[str] = []
    for item in [emphases.get("primary"), emphases.get("secondary"),
                 *emphases.get("list", [])]:
        if item and item.get("label") and item["label"] not in labels:
            labels.append(item["label"])
    return labels[:MAX_RESEARCH_EMPHASES]


def research_suggestions(emphases: dict | None, researcher_client=None
                         ) -> tuple[list[dict], list[str]]:
    """Advisory context per emphasis for the review UI. One batch call.
    Never raises — research is best-effort enrichment."""
    labels = _emphasis_labels(emphases)
    if researcher_client is None:
        return [], (["researcher not configured"] if labels else [])
    if not labels:
        return [], []
    requests = [{"intent": "concept.overview", "params": {"term": label}}
                for label in labels]
    try:
        results = researcher_client.batch(requests)
    except DownstreamError as exc:
        return [], [f"research unavailable: {exc}"]

    suggestions, warnings = [], []
    for label, envelope in zip(labels, results):
        data = envelope.get("data") or {}
        if envelope.get("degraded"):
            warnings.extend(envelope.get("warnings", []))
        if not data:
            continue
        suggestions.append({
            "emphasis": label,
            "summary": data.get("summary") or data.get("definition") or data.get("title"),
            "sources": envelope.get("sources", []),
            "attribution_required": envelope.get("attribution_required", False),
        })
    return suggestions, warnings


def cover_letter_research(target_role: str | None, target_organization: str | None,
                          researcher_client=None) -> tuple[dict, list[str]]:
    """Real framing content for the cover-letter path: company profile + role
    responsibilities, with attribution. Best-effort; the letter still generates
    if research is unavailable."""
    requests, kinds = [], []
    if target_organization:
        requests.append({"intent": "company.profile", "params": {"name": target_organization}})
        kinds.append("company")
    if target_role:
        requests.append({"intent": "role.responsibilities", "params": {"title": target_role}})
        kinds.append("role")
    if not requests:
        return {}, []
    if researcher_client is None:
        return {}, ["researcher not configured"]
    try:
        results = researcher_client.batch(requests)
    except DownstreamError as exc:
        return {}, [f"research unavailable: {exc}"]

    research: dict = {"attributions": []}
    warnings: list[str] = []
    for kind, envelope in zip(kinds, results):
        data = envelope.get("data") or {}
        if envelope.get("degraded"):
            warnings.extend(envelope.get("warnings", []))
        if data:
            research[kind] = data
        for source in envelope.get("sources", []):
            attribution = source.get("attribution")
            if attribution and attribution not in research["attributions"]:
                research["attributions"].append(attribution)
    return research, warnings


def compare_proposals(posting: str, docx_bytes: bytes, profile=None, library=None,
                      parser_client=None) -> dict:
    """Run legacy and composed on identical inputs and return a per-slot diff.
    The integration tool for finding composed-workflow bugs against the legacy
    baseline. Deterministic (research excluded)."""
    legacy_kw, _ = get_keywords(posting, "legacy", None)
    composed_kw, composed_meta = get_keywords(posting, "composed", parser_client)

    legacy_slots, _ = propose_for(posting, docx_bytes, profile, library, keywords=legacy_kw)
    composed_slots, _ = propose_for(posting, docx_bytes, profile, library, keywords=composed_kw)

    legacy_map = {s.key: s for s in legacy_slots}
    composed_map = {s.key: s for s in composed_slots}
    keys = list(legacy_map) + [k for k in composed_map if k not in legacy_map]

    rows, changed = [], 0
    for key in keys:
        legacy_slot, composed_slot = legacy_map.get(key), composed_map.get(key)
        legacy_view = _slot_view(legacy_slot)
        composed_view = _slot_view(composed_slot)
        is_changed = legacy_view != composed_view
        changed += is_changed
        rows.append({"key": key, "legacy": legacy_view, "composed": composed_view,
                     "changed": is_changed})
    return {"composed_meta": composed_meta, "changed_count": changed, "slots": rows}


def _slot_view(slot) -> dict | None:
    if slot is None:
        return None
    return {"value": slot.value, "strategy": slot.strategy}
