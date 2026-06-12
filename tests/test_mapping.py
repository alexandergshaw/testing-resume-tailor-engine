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
    "ROLE_SPECIFIC_EXPERTISE": Strategy.PROFILE,
    "CORE_PROFESSIONAL_CAPABILITIES": Strategy.PROFILE,
    "METHODS_SYSTEMS_TECHNOLOGIES": Strategy.PROFILE,
    "LEADERSHIP_DELIVERY_COLLABORATION": Strategy.PROFILE,
    "SUPPORTING_TOOLS_KNOWLEDGE": Strategy.PROFILE,
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
    "STRATEGIC_OUTCOME": Strategy.LIBRARY_MATCH,
    "RESULTING_CAPABILITY": Strategy.LIBRARY_MATCH,
    "PROBLEM_OR_REQUIREMENT": Strategy.LIBRARY_MATCH,
    "BUSINESS_OR_TECHNICAL_OUTCOME": Strategy.LIBRARY_MATCH,
    "PROJECT_SCOPE": Strategy.LIBRARY_MATCH,
    "PROJECT_TYPE": Strategy.LIBRARY_MATCH,
    "PROJECT_SOLUTION": Strategy.LIBRARY_MATCH,
    "PRIMARY_CAPABILITY": Strategy.LIBRARY_MATCH,
    "NEW_CAPABILITY": Strategy.LIBRARY_MATCH,
    "EXISTING_SYSTEM_OR_PROCESS": Strategy.LIBRARY_MATCH,
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


def test_skills_distribute_by_occurrence():
    proposer = make_proposer()
    assert proposer.propose(_ph("2_LINES_OF_COMMA_SEPARATED_SKILLS", 0)).value == "Python, C#"
    assert proposer.propose(_ph("2_LINES_OF_COMMA_SEPARATED_SKILLS", 1)).value == "AWS, Docker"
    assert proposer.propose(_ph("2_LINES_OF_COMMA_SEPARATED_SKILLS", 2)).value == "CI/CD"
    assert proposer.propose(_ph("2_LINES_OF_COMMA_SEPARATED_SKILLS", 3)).value == "Leadership, Mentoring"
    assert proposer.propose(_ph("2_LINES_OF_COMMA_SEPARATED_SKILLS", 4)).value == "Insurance, Cloud Migration"


def test_library_no_repeat_and_relevance():
    proposer = make_proposer()
    first = proposer.propose(_ph("ACTION", 0))
    second = proposer.propose(_ph("ACTION", 1))
    third = proposer.propose(_ph("ACTION", 2))
    # 'a-cicd' tags overlap the keywords more strongly than 'b-led'.
    assert first.value == "Automated"
    assert second.value == "Led"
    assert third.strategy is Strategy.MANUAL  # exhausted
