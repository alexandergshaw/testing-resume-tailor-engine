from tailor.docxio.scanner import Placeholder
from tailor.extraction.extractor import Keyword
from tailor.library.store import LibraryEntry
from tailor.mapping.registry import Strategy, normalize_name, resolve
from tailor.mapping.strategies import Proposer

# Every placeholder present in the real Template Resume.docx, normalized.
REAL_TEMPLATE_EXPECTATIONS = {
    "RANK": Strategy.PROFILE,
    "TOP_RANK": Strategy.PROFILE,
    "MEDIUM_RANK": Strategy.PROFILE,
    "LOW_RANK": Strategy.PROFILE,
    "PRIMARY_FUNCTION": Strategy.PROFILE,
    "FUNCTION": Strategy.PROFILE,
    "SPECIALIZATION": Strategy.PROFILE,
    "YEARS_OF_EXPERIENCE": Strategy.PROFILE,
    "SCALE_DESCRIPTOR": Strategy.PROFILE,
    "USER_SCALE": Strategy.PROFILE,
    "EVENT_SCALE": Strategy.PROFILE,
    "ENVIRONMENT_TYPES": Strategy.PROFILE,
    "LEADERSHIP_LEVEL": Strategy.PROFILE,
    "LEADERSHIP_SCOPE": Strategy.PROFILE,
    "ROLE_SPECIFIC_EXPERTISE": Strategy.SKILLS_HEADER,
    "CORE_PROFESSIONAL_CAPABILITIES": Strategy.SKILLS_HEADER,
    "METHODS_SYSTEMS_TECHNOLOGIES": Strategy.SKILLS_HEADER,
    "LEADERSHIP_DELIVERY_COLLABORATION": Strategy.SKILLS_HEADER,
    "SUPPORTING_TOOLS_KNOWLEDGE": Strategy.SKILLS_HEADER,
    "LEADERSHIP_CAPABILITIES": Strategy.KEYWORD_JOIN,
    "JOB_RELEVANT_TECHNOLOGIES": Strategy.KEYWORD_JOIN,
    "TECHNICAL_CAPABILITIES": Strategy.KEYWORD_JOIN,
    "JOB_RELEVANT_SOLUTIONS": Strategy.KEYWORD_JOIN,
    "TECHNICAL_APPROACH": Strategy.KEYWORD_JOIN,
    "DELIVERY_PRACTICES": Strategy.KEYWORD_JOIN,
    "DOMAIN_CAPABILITIES": Strategy.KEYWORD_JOIN,
    "SOLUTION_TYPES": Strategy.KEYWORD_JOIN,
    "AREA_OF_EMPHASIS": Strategy.KEYWORD_JOIN,
    "AREAS_OF_EMPHASIS": Strategy.KEYWORD_JOIN,
    "LIST_OF_3_COURSE_TOPICS_RELEVANT_TO_JOB_POSTING_PRIORITIZE_TECHNOLOGIES_PEOPLE_SKILLS": Strategy.KEYWORD_JOIN,
    "LIST_OF_4_COURSE_TOPICS_RELEVANT_TO_JOB_POSTING_PRIORITIZE_TECHNOLOGIES_PEOPLE_SKILLS": Strategy.KEYWORD_JOIN,
    "2_LINES_OF_COMMA_SEPARATED_SKILLS": Strategy.SKILLS_DISTRIBUTE,
    "ACTION": Strategy.LIBRARY_MATCH,
    "ACTION_OR_IMPLEMENTATION": Strategy.LIBRARY_MATCH,
    "ACTION_RESULT": Strategy.LIBRARY_MATCH,
    "INITIATIVE_TYPE": Strategy.LIBRARY_MATCH,
    "INITIATIVE_OR_RESPONSIBILITY": Strategy.LIBRARY_MATCH,
    "SOLUTION_OR_INITIATIVE": Strategy.LIBRARY_MATCH,
    "SOLUTION_OR_PROCESS": Strategy.LIBRARY_MATCH,
    "SOLUTION_OR_CAPABILITY": Strategy.LIBRARY_MATCH,
    "TECHNICAL_OR_BUSINESS_RESULT": Strategy.LIBRARY_MATCH,
    "MEASURABLE_IMPACT": Strategy.LIBRARY_MATCH,
    "SCOPE_OR_STAKEHOLDERS": Strategy.LIBRARY_MATCH,
    "SCOPE_OR_TEAM": Strategy.LIBRARY_MATCH,
    "USERS_OR_STAKEHOLDERS": Strategy.LIBRARY_MATCH,
    "STRATEGIC_OUTCOMES": Strategy.LIBRARY_MATCH,
    "RESULTING_CAPABILITY": Strategy.LIBRARY_MATCH,
    "PROBLEM_OR_REQUIREMENT": Strategy.LIBRARY_MATCH,
    "BUSINESS_OR_TECHNICAL_OUTCOME": Strategy.LIBRARY_MATCH,
    # Projects slots are posting-driven; only metric slots stay library-backed.
    "STRATEGIC_OUTCOME": Strategy.KEYWORD_PHRASE,
    "PROJECT_SCOPE": Strategy.KEYWORD_PHRASE,
    "PROJECT_TYPE": Strategy.KEYWORD_PHRASE,
    "PROJECT_SOLUTION": Strategy.KEYWORD_PHRASE,
    "PRIMARY_CAPABILITY": Strategy.KEYWORD_PHRASE,
    "NEW_CAPABILITY": Strategy.KEYWORD_PHRASE,
    "EXISTING_SYSTEM_OR_PROCESS": Strategy.KEYWORD_PHRASE,
    "PERFORMANCE_OR_BUSINESS_METRIC": Strategy.LIBRARY_MATCH,
}


def test_registry_covers_every_real_template_placeholder():
    for name, expected in REAL_TEMPLATE_EXPECTATIONS.items():
        strategy, _ = resolve(name)
        assert strategy is expected, f"{name}: expected {expected}, got {strategy}"


def test_unknown_name_is_manual():
    strategy, _ = resolve("SOMETHING_NOBODY_PLANNED_FOR")
    assert strategy is Strategy.MANUAL


def test_course_topics_count_comes_from_name():
    _, params = resolve("LIST_OF_4_COURSE_TOPICS_RELEVANT_TO_JOB_POSTING")
    assert params["n"] == 4


def _ph(name, occurrence=0):
    return Placeholder(name=name, occurrence=occurrence, raw="{{" + name + "}}",
                       context="", single_brace=False)


KEYWORDS = [
    Keyword("Python", "technology", 10.0, 5),
    Keyword("C#", "technology", 8.0, 4),
    Keyword("AWS", "tool_platform", 7.0, 3),
    Keyword("Docker", "tool_platform", 4.0, 2),
    Keyword("CI/CD", "methodology", 6.0, 3),
    Keyword("Leadership", "soft_skill", 5.0, 2),
    Keyword("Mentoring", "soft_skill", 3.0, 1),
    Keyword("Insurance", "domain", 4.0, 2),
    Keyword("Cloud Migration", "domain", 3.0, 1),
]

PROFILE = {"RANK": "Senior", "YEARS_OF_EXPERIENCE": "7"}

LIBRARY = [
    LibraryEntry(id="a-cicd", slots=("ACTION",), text="Automated",
                 tags=("CI/CD", "Docker")),
    LibraryEntry(id="b-led", slots=("ACTION",), text="Led",
                 tags=("Leadership",)),
    LibraryEntry(id="c-impact", slots=("MEASURABLE_IMPACT",), text="70% faster deploys",
                 tags=("CI/CD",)),
]


def make_proposer():
    return Proposer(KEYWORDS, PROFILE, LIBRARY)


def test_profile_lookup_and_manual_fallback():
    proposer = make_proposer()
    assert proposer.propose(_ph("RANK")).value == "Senior"
    missing = proposer.propose(_ph("LEADERSHIP_SCOPE"))
    assert missing.strategy is Strategy.MANUAL
    assert missing.value == ""


def test_keyword_join_order_and_shared_pool():
    proposer = make_proposer()
    first = proposer.propose(_ph("AREA_OF_EMPHASIS", 0))
    second = proposer.propose(_ph("AREA_OF_EMPHASIS", 1))
    assert first.value == "Insurance"        # top domain keyword
    assert second.value == "Cloud Migration" # pool advanced, no repeat


def test_keyword_join_categories():
    proposer = make_proposer()
    tech = proposer.propose(_ph("JOB_RELEVANT_TECHNOLOGIES"))
    assert tech.value == "Python, C#, AWS, Docker"  # tech + tool_platform by score


def test_skills_rows_follow_group_plan():
    # Groups by summed fixture scores: Programming (Python+C#=18),
    # Cloud & Infrastructure (AWS+Docker=11), Leadership & Collaboration (8),
    # Industry & Domain (Insurance+Cloud Migration=7). CI/CD is alone in its
    # group (< 2 keywords) so DevOps drops and CI/CD goes unclaimed.
    proposer = make_proposer()
    assert proposer.propose(_ph("2_LINES_OF_COMMA_SEPARATED_SKILLS", 0)).value == "Python, C#"
    assert proposer.propose(_ph("2_LINES_OF_COMMA_SEPARATED_SKILLS", 1)).value == "AWS, Docker"
    assert proposer.propose(_ph("2_LINES_OF_COMMA_SEPARATED_SKILLS", 2)).value == "Leadership, Mentoring"
    assert proposer.propose(_ph("2_LINES_OF_COMMA_SEPARATED_SKILLS", 3)).value == "Insurance, Cloud Migration"
    # Beyond the planned groups: legacy fixed-category fallback (index 4 = domain).
    fallback = proposer.propose(_ph("2_LINES_OF_COMMA_SEPARATED_SKILLS", 4))
    assert fallback.value == "Insurance, Cloud Migration"


def test_skills_headers_follow_group_plan_then_profile():
    proposer = make_proposer()
    h0 = proposer.propose(_ph("ROLE_SPECIFIC_EXPERTISE"))
    h1 = proposer.propose(_ph("CORE_PROFESSIONAL_CAPABILITIES"))
    h2 = proposer.propose(_ph("METHODS_SYSTEMS_TECHNOLOGIES"))
    h3 = proposer.propose(_ph("LEADERSHIP_DELIVERY_COLLABORATION"))
    h4 = proposer.propose(_ph("SUPPORTING_TOOLS_KNOWLEDGE"))
    assert [h.value for h in (h0, h1, h2, h3)] == [
        "Programming & Frameworks", "Cloud & Infrastructure",
        "Leadership & Collaboration", "Industry & Domain Knowledge"]
    assert all(h.strategy is Strategy.SKILLS_HEADER for h in (h0, h1, h2, h3))
    # Only 4 groups qualified; the 5th heading falls back to profile.json,
    # which doesn't define it in this fixture -> manual.
    assert h4.strategy is Strategy.MANUAL


def test_phrase_project_type_and_capability():
    proposer = make_proposer()
    # domain+methodology pool in fixture order: CI/CD, Insurance, Cloud Migration.
    assert proposer.propose(_ph("PROJECT_TYPE")).value == "CI/CD Initiative"
    assert proposer.propose(_ph("PRIMARY_CAPABILITY")).value == "Python"


def test_phrase_outcome_walks_curated_map():
    proposer = make_proposer()
    # First keyword with a curated outcome is Docker, then CI/CD.
    assert proposer.propose(_ph("STRATEGIC_OUTCOME", 0)).value == "Consistent Environments"
    assert proposer.propose(_ph("STRATEGIC_OUTCOME", 1)).value == "Faster, Safer Releases"


def test_phrase_solution_uses_topic_when_available():
    topical = KEYWORDS + [
        Keyword("policy administration platform", "topic", 6.0, 2),
        Keyword("Senior Software Engineering Lead", "topic", 19.0, 1),  # role-y, filtered
    ]
    proposer = Proposer(topical, PROFILE, LIBRARY)
    solution = proposer.propose(_ph("PROJECT_SOLUTION"))
    assert solution.value == "a Python-based solution supporting the policy administration platform"
    # Topics never repeat: the only eligible one is spent, so the next
    # topic-hungry slot falls back to the domain-keyword pattern.
    existing = proposer.propose(_ph("EXISTING_SYSTEM_OR_PROCESS"))
    assert existing.value == "legacy insurance workflows"


def test_phrase_solution_without_topics():
    proposer = make_proposer()
    assert proposer.propose(_ph("PROJECT_SOLUTION")).value == "a Python and C# solution"
    assert proposer.propose(_ph("EXISTING_SYSTEM_OR_PROCESS")).value == "legacy insurance workflows"


def test_phrase_scope_defaults_enterprise():
    proposer = make_proposer()
    assert proposer.propose(_ph("PROJECT_SCOPE")).value == "Enterprise"


def test_library_no_repeat_and_relevance():
    proposer = make_proposer()
    first = proposer.propose(_ph("ACTION", 0))
    second = proposer.propose(_ph("ACTION", 1))
    third = proposer.propose(_ph("ACTION", 2))
    # 'a-cicd' tags overlap the keywords more strongly than 'b-led'.
    assert first.value == "Automated"
    assert second.value == "Led"
    assert third.strategy is Strategy.MANUAL  # exhausted
