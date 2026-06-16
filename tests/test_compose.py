"""Composed-workflow orchestration: keyword mapping, fallback, research batching."""
from tailor.clients.base import DownstreamError
from tailor.compose import (compare_proposals, cover_letter_research, get_keywords,
                            research_suggestions)
from tailor.extraction.source import classify_keyword, keywords_from_parser
from tests.fakes import PARSE_FIXTURE, FakeParser, FakeResearcher
from tests.test_service import POSTING, TEMPLATE


def test_classification_uses_canonical_casing_and_categories():
    keywords, emphases = keywords_from_parser(PARSE_FIXTURE)
    by_name = {k.canonical: k.category for k in keywords}
    # Canonical casing + categories from both the keywords and technologies lenses.
    assert by_name["ETL"] == "technology"
    assert by_name["Spark"] == "technology"
    assert by_name["AWS"] == "tool_platform"
    assert by_name["Kubernetes"] == "tool_platform"
    # Unknown RAKE phrase is classified (not dropped): falls back to domain.
    assert by_name["Build scalable Data pipelines"] == "domain"
    assert emphases["primary"]["id"] == "data_science"
    assert emphases["secondary"]["id"] == "software_industry"


def test_classify_unknown_falls_back_to_domain():
    assert classify_keyword("Totally Novel Phrase", None) == "domain"
    assert classify_keyword("Totally Novel Phrase", "web_development") == "technology"


def test_get_keywords_legacy_matches_local_extraction():
    from tailor.extraction.extractor import extract_keywords
    keywords, meta = get_keywords(POSTING, "legacy", FakeParser())
    assert meta == {"workflow": "legacy", "degraded": False, "emphases": None}
    assert keywords == extract_keywords(POSTING)


def test_get_keywords_composed_uses_parser():
    parser = FakeParser()
    keywords, meta = get_keywords(POSTING, "composed", parser)
    assert parser.calls == 1
    assert meta["degraded"] is False
    assert meta["parser_version"] == "1.0.0"
    assert {"ETL", "Spark", "AWS"} <= {k.canonical for k in keywords}


def test_get_keywords_composed_falls_back_on_parser_error():
    parser = FakeParser(error=DownstreamError("parser", "boom"))
    keywords, meta = get_keywords(POSTING, "composed", parser)
    assert meta["workflow"] == "composed"
    assert meta["degraded"] is True
    assert "used local extraction" in meta["reason"]
    assert keywords  # still produced something


def test_get_keywords_composed_without_client_degrades():
    keywords, meta = get_keywords(POSTING, "composed", None)
    assert meta["degraded"] is True
    assert "not configured" in meta["reason"]


def test_research_suggestions_one_batch_per_emphasis():
    _, emphases = keywords_from_parser(PARSE_FIXTURE)
    researcher = FakeResearcher(results_by_intent={
        "concept.overview": {"summary": "A field about data."}})
    suggestions, warnings = research_suggestions(emphases, researcher)
    assert researcher.batch_calls == 1
    # one request per distinct emphasis label, not per keyword
    # (field.top + sector.top + field.ranked, deduped: Data Science, Software
    # Industry, DevOps & Cloud Infrastructure)
    assert len(researcher.last_requests) == 3
    assert all(r["intent"] == "concept.overview" for r in researcher.last_requests)
    assert suggestions and suggestions[0]["attribution_required"] is True


def test_research_suggestions_resilient_to_outage():
    _, emphases = keywords_from_parser(PARSE_FIXTURE)
    researcher = FakeResearcher(error=DownstreamError("researcher", "down"))
    suggestions, warnings = research_suggestions(emphases, researcher)
    assert suggestions == []
    assert warnings and "unavailable" in warnings[0]


def test_cover_letter_research_returns_attribution():
    researcher = FakeResearcher(results_by_intent={
        "company.profile": {"name": "Acme", "industry": "Software"},
        "role.responsibilities": {"title": "Engineer", "essential_skills": ["Python"]}})
    research, warnings = cover_letter_research("Engineer", "Acme", researcher)
    assert research["company"]["name"] == "Acme"
    assert research["role"]["title"] == "Engineer"
    assert any("CC BY-SA" in a for a in research["attributions"])


def test_compare_proposals_diffs_workflows():
    diff = compare_proposals(POSTING, TEMPLATE, parser_client=FakeParser())
    assert diff["composed_meta"]["workflow"] == "composed"
    assert "slots" in diff and diff["slots"]
    # deterministic
    again = compare_proposals(POSTING, TEMPLATE, parser_client=FakeParser())
    assert [r["changed"] for r in diff["slots"]] == [r["changed"] for r in again["slots"]]
