from tailor.extraction.extractor import Keyword
from tailor.mapping.skill_groups import (MAX_KEYWORDS_PER_GROUP, SkillGroupDef,
                                         build_group_plan, default_group_defs)

DEFS = [
    SkillGroupDef(heading="Alpha Tools", keywords=frozenset({"jenkins", "ci/cd"}),
                  categories=frozenset()),
    SkillGroupDef(heading="Methods", keywords=frozenset(),
                  categories=frozenset({"methodology"})),
    SkillGroupDef(heading="People", keywords=frozenset(),
                  categories=frozenset({"soft_skill"})),
]


def test_explicit_listing_beats_category_group():
    keywords = [
        Keyword("CI/CD", "methodology", 6.0, 3),
        Keyword("Jenkins", "tool_platform", 4.0, 2),
        Keyword("Scrum", "methodology", 5.0, 2),
        Keyword("Agile", "methodology", 5.0, 2),
    ]
    plan = build_group_plan(keywords, DEFS)
    by_heading = {g.heading: [k.canonical for k in g.keywords] for g in plan}
    # CI/CD is methodology but explicitly listed in Alpha Tools, so the
    # category group may not claim it.
    assert by_heading["Alpha Tools"] == ["CI/CD", "Jenkins"]
    assert by_heading["Methods"] == ["Scrum", "Agile"]


def test_groups_below_minimum_drop_out():
    keywords = [Keyword("Jenkins", "tool_platform", 4.0, 2),
                Keyword("Leadership", "soft_skill", 5.0, 2),
                Keyword("Mentoring", "soft_skill", 2.0, 1)]
    plan = build_group_plan(keywords, DEFS)
    headings = [g.heading for g in plan]
    assert "Alpha Tools" not in headings  # only 1 matching keyword
    assert headings == ["People"]


def test_rows_capped():
    keywords = [Keyword(f"Soft Skill {i}", "soft_skill", 10.0 - i, 1) for i in range(12)]
    plan = build_group_plan(keywords, DEFS)
    assert len(plan[0].keywords) == MAX_KEYWORDS_PER_GROUP


def test_topics_excluded_and_deterministic():
    keywords = [
        Keyword("Scrum", "methodology", 5.0, 2),
        Keyword("Agile", "methodology", 5.0, 2),
        Keyword("policy administration platform", "topic", 19.0, 3),
    ]
    plan = build_group_plan(keywords, DEFS)
    assert [g.heading for g in plan] == ["Methods"]
    assert plan == build_group_plan(keywords, DEFS)


def test_bundled_group_defs_load_and_reference_known_categories():
    defs = default_group_defs()
    assert len(defs) >= 10
    valid = {"technology", "tool_platform", "methodology", "soft_skill",
             "certification", "domain"}
    for group in defs:
        assert group.categories <= valid, f"{group.heading} has unknown categories"
