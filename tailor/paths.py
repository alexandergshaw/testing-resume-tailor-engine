from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

TAXONOMY_PATH = DATA_DIR / "skills_taxonomy.json"
STOPWORDS_PATH = DATA_DIR / "stopwords_en.txt"
PROFILE_PATH = DATA_DIR / "profile.json"
CONTENT_LIBRARY_PATH = DATA_DIR / "content_library.json"
OUTCOME_PHRASES_PATH = DATA_DIR / "outcome_phrases.json"
SKILL_GROUPS_PATH = DATA_DIR / "skill_groups.json"
DEFAULT_COVER_LETTER_TEMPLATE = DATA_DIR / "cover_letter_template.docx"
DEFAULT_RESUME_TEMPLATE = DATA_DIR / "resume_template.docx"
