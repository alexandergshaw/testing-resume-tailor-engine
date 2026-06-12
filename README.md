# Resume Tailor Engine

A small local web app that tailors a template resume to a job posting — **no LLM anywhere**. Everything is deterministic, rule-based keyword extraction and matching.

## How it works

1. Paste a job posting into the text box and upload your template `.docx` (placeholders like `{{JOB_RELEVANT_TECHNOLOGIES}}`).
2. The app extracts buzzwords from the posting using a curated skills taxonomy + RAKE-style phrase scoring, then proposes a value for every placeholder it finds in your document.
3. You review and edit every proposed value on the review screen.
4. Download the filled `.docx` — original formatting preserved.

## Run it

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000.

Run tests with `pytest`.

## Make it yours (the three data files)

| File | What it is |
|---|---|
| `data/profile.json` | Static facts about you (rank, years of experience, team size…), keyed by normalized placeholder name. |
| `data/content_library.json` | Your accomplishment bank. Sentence fragments tagged with skills; the app picks the entries whose tags best match the job posting's keywords. **Replace the seeded examples with your real accomplishments.** |
| `data/skills_taxonomy.json` | ~340 known skills/technologies with aliases and categories. Extraction quality lives here — add anything your field uses. |

### Placeholder name normalization

`{{Role-Specific Expertise }}`, `{{role specific expertise}}`, and `{ROLE_SPECIFIC_EXPERTISE}` all normalize to `ROLE_SPECIFIC_EXPERTISE`: braces stripped, trimmed, uppercased, spaces/hyphens collapsed to underscores. Use the normalized form as keys in `profile.json` and in `content_library.json` slots.

### How placeholders get filled

| Strategy | Applies to | Source |
|---|---|---|
| PROFILE | `{{RANK}}`, `{{YEARS_OF_EXPERIENCE}}`, … | `profile.json` |
| KEYWORD_JOIN | `{{JOB_RELEVANT_TECHNOLOGIES}}`, `{{DELIVERY_PRACTICES}}`, … | top extracted keywords of the relevant category |
| LIBRARY_MATCH | `{{ACTION}}`, `{{MEASURABLE_IMPACT}}`, … | best-scoring content library entry (TF-IDF cosine + tag overlap, no entry used twice) |
| SKILLS_DISTRIBUTE | the five `{{2 lines of comma separated skills}}` slots | keywords distributed across categories by occurrence order |
| MANUAL | anything unrecognized | you, on the review screen |
