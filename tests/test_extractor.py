from pathlib import Path

from tailor.extraction.extractor import extract_keywords, keywords_by_category
from tailor.extraction.normalize import normalize_phrase, split_segments

FIXTURE = Path(__file__).parent / "fixtures" / "sample_posting.txt"
POSTING = FIXTURE.read_text(encoding="utf-8")


def canonicals(keywords):
    return {k.canonical for k in keywords}


def test_tokenizer_preserves_tech_terms():
    segments = split_segments("Experience with C++, C#, .NET and Node.js.")
    tokens = [t.surface for seg in segments for t in seg]
    assert "C++" in tokens
    assert "C#" in tokens
    assert ".NET" in tokens
    assert "Node.js" in tokens


def test_normalize_phrase_handles_separators():
    assert normalize_phrase("CI/CD") == "ci cd"
    assert normalize_phrase("Cross-Functional Teams") == "cross functional teams"


def test_canonical_casing():
    keywords = extract_keywords("we want javascript and postgres experience")
    assert "JavaScript" in canonicals(keywords)
    assert "PostgreSQL" in canonicals(keywords)


def test_multiword_and_symbol_matches():
    keywords = extract_keywords(POSTING)
    found = canonicals(keywords)
    assert "C#" in found
    assert ".NET" in found
    assert "Node.js" in found
    assert "CI/CD" in found
    assert "Infrastructure as Code" in found
    assert "Stakeholder Management" in found
    assert "AWS Certified Solutions Architect" in found


def test_categories_present():
    grouped = keywords_by_category(extract_keywords(POSTING))
    assert "technology" in grouped
    assert "tool_platform" in grouped
    assert "methodology" in grouped
    assert "soft_skill" in grouped


def test_requirements_section_weighted_above_nice_to_have():
    # Docker appears once in Requirements (x2); Python once in Nice to have.
    keywords = {k.canonical: k for k in extract_keywords(POSTING)}
    assert keywords["Docker"].score > keywords["Python"].score


def test_deterministic():
    first = extract_keywords(POSTING)
    second = extract_keywords(POSTING)
    assert first == second


def test_sorted_by_score_then_name():
    keywords = extract_keywords(POSTING)
    sort_keys = [(-k.score, k.canonical.lower()) for k in keywords]
    assert sort_keys == sorted(sort_keys)
