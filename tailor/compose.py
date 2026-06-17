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
# company.news is volatile; only clearly-favorable items (tone at/above this)
# are surfaced. Tunable. The Researcher also filters server-side via min_tone.
FAVORABLE_MIN_TONE = 2.0
NEWS_LIMIT = 8


def _news_request(identifier: str) -> dict:
    return {"intent": "company.news",
            "params": {"name": identifier, "limit": NEWS_LIMIT,
                       "min_tone": FAVORABLE_MIN_TONE, "sort": "tone"}}


def _news_from_envelope(envelope: dict) -> dict:
    """Extract a compact, attributed, favorable news payload from a company.news
    envelope. Articles are headline + link + metadata only (no body text)."""
    data = envelope.get("data") or {}
    articles = []
    for item in data.get("articles", []):
        tone = item.get("tone")
        if tone is not None and tone < FAVORABLE_MIN_TONE:
            continue  # belt-and-suspenders: enforce favorable client-side too
        articles.append({
            "title": item.get("title"), "source": item.get("source"),
            "url": item.get("url"), "published": item.get("published"),
            "tone": tone,
        })
    if not articles:
        return {}
    return {
        "as_of": data.get("as_of"),
        "articles": articles,
        "attributions": [s["attribution"] for s in envelope.get("sources", [])
                         if s.get("attribution")],
        "attribution_required": envelope.get("attribution_required", False),
    }


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
        primary = emphases.get("primary")
        return keywords, {"workflow": "composed", "degraded": False,
                          "emphases": emphases,
                          "low_confidence": bool(primary and primary.get("low_confidence")),
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


def company_news_suggestions(target_organization: str | None, researcher_client=None
                             ) -> tuple[dict, list[str]]:
    """Advisory, clearly-favorable company news for the review UI (resume path).
    Volatile and never auto-inserted. Resilient to outages and a disabled
    gdelt source (501 source_disabled)."""
    if not target_organization:
        return {}, []
    if researcher_client is None:
        return {}, ["researcher not configured"]
    request = _news_request(target_organization)
    try:
        envelope = researcher_client.research(request["intent"], request["params"])
    except DownstreamError as exc:
        return {}, [f"company news unavailable: {exc}"]
    news = _news_from_envelope(envelope)
    warnings = list(envelope.get("warnings", [])) if not news else []
    return news, warnings


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
    if target_organization:
        requests.append(_news_request(target_organization))  # favorable recent items
        kinds.append("news")
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
        if envelope.get("degraded"):
            warnings.extend(envelope.get("warnings", []))
        if kind == "news":
            news = _news_from_envelope(envelope)
            if news:
                research["news"] = news
                research["attributions"].extend(news["attributions"])
            continue
        data = envelope.get("data") or {}
        if data:
            research[kind] = data
        for source in envelope.get("sources", []):
            attribution = source.get("attribution")
            if attribution and attribution not in research["attributions"]:
                research["attributions"].append(attribution)
    # de-dup attributions while preserving order
    research["attributions"] = list(dict.fromkeys(research["attributions"]))
    return research, warnings


def _skill_label(skill) -> str | None:
    if isinstance(skill, dict):
        return skill.get("title") or skill.get("label") or skill.get("name")
    return skill or None


def _role_focus(role: dict | None) -> str | None:
    skills = [_skill_label(s) for s in (role or {}).get("essential_skills", [])]
    skills = [s for s in skills if s][:3]
    if not skills:
        return None
    if len(skills) == 1:
        return skills[0]
    if len(skills) == 2:
        return f"{skills[0]} and {skills[1]}"
    return f"{skills[0]}, {skills[1]}, and {skills[2]}"


def _org_context(company: dict | None) -> str | None:
    industry = (company or {}).get("industry")
    return f"your work in {industry}" if industry else None


def cover_letter_field_values(research: dict) -> dict:
    """Deterministic framing sentences for the cover-letter's research slots,
    composed from STRUCTURED fields (not third-party prose). Returns only the
    slots it can fill; missing ones stay MANUAL/visible in the document.

    News stays advisory (research['news']) — deterministic paraphrase of
    arbitrary headlines isn't safe, so it isn't auto-inserted."""
    field_values = {}
    org = _org_context(research.get("company"))
    if org:
        field_values["ORGANIZATION_CONTEXT"] = org
    focus = _role_focus(research.get("role"))
    if focus:
        field_values["ROLE_FOCUS"] = focus
    return field_values


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
