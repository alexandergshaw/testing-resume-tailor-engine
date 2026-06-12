from tailor.extraction.extractor import Keyword
from tailor.library.scoring import score_entries
from tailor.library.store import LibraryEntry, load_library, load_profile

KEYWORDS = [
    Keyword("Kubernetes", "tool_platform", 9.0, 4),
    Keyword("CI/CD", "methodology", 6.0, 3),
    Keyword("Leadership", "soft_skill", 3.0, 1),
]


def test_relevant_entry_outranks_unrelated():
    entries = [
        LibraryEntry(id="devops", slots=("ACTION",),
                     text="Containerized services with Kubernetes",
                     tags=("Kubernetes", "CI/CD")),
        LibraryEntry(id="unrelated", slots=("ACTION",),
                     text="Wrote quarterly marketing newsletters",
                     tags=("Digital Marketing",)),
    ]
    scores = score_entries(entries, KEYWORDS)
    assert scores["devops"] > scores["unrelated"]


def test_deterministic_scores():
    entries = [
        LibraryEntry(id="x", slots=("ACTION",), text="Led Kubernetes rollout",
                     tags=("Kubernetes",)),
    ]
    assert score_entries(entries, KEYWORDS) == score_entries(entries, KEYWORDS)


def test_no_keywords_gives_zero_cosine():
    entries = [LibraryEntry(id="x", slots=("ACTION",), text="Led things", tags=())]
    scores = score_entries(entries, [])
    assert scores["x"] == 0.0


def test_bundled_data_files_load():
    profile = load_profile()
    assert "RANK" in profile
    library = load_library()
    assert library, "content_library.json should have seed entries"
    ids = [e.id for e in library]
    assert len(ids) == len(set(ids))
