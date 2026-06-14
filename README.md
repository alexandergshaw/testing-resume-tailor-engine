# Resume Tailor Engine

A deterministic resume-tailoring engine — **no LLM anywhere** — exposed as a small HTTP API
(`/api/v1`) with a bundled web UI that is itself just a client of that API. Other apps submit
a job posting plus a `.docx` resume template with `{{PLACEHOLDERS}}` and receive back a
tailored `.docx`.

## How it works

1. The posting is parsed with a curated skills taxonomy + RAKE-style phrase scoring
   (requirements sections weighted higher). Everything is rule-based and reproducible.
2. Every `{{placeholder}}` found in the template is routed through a strategy table:
   posting keywords, posting-driven phrase patterns, your profile facts, or your
   insertion bank (scopes/metrics/outcomes ranked by relevance to the posting).
3. The caller (UI or API client) can review/override any value, then the template is
   filled in-memory — original formatting preserved, even when Word split a
   placeholder across runs.

## Run locally

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py        # UI + API at http://127.0.0.1:5000
pytest               # full suite
```

## API

All behavior is behind `/api/v1`. The UI pages (`/` and `/bank`) call these same endpoints —
use them as a live tester; each page has a request/response log panel and a copy-as-curl button.

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/proposals` | Scan the template + parse the posting; returns every slot with its proposed value, strategy, note, and ranked bank candidates, plus extracted keywords. `template` is **optional** — omit it to use the bundled `data/resume_template.docx`. |
| `POST /api/v1/tailor` | Same inputs + optional `values` overrides; returns the tailored docx (binary by default, JSON+base64 with `Accept: application/json`). `template` optional (bundled default). Optional `remember` list persists values to the bank (local only). |
| `POST /api/v1/cover-letter` | Tailors a cover letter. `template` is **optional** — omit it to use the bundled `data/cover_letter_template.docx`. Adds `target_role` / `target_organization` fields that fill every `{{TARGET_ROLE}}` / `{{TARGET_ORGANIZATION}}` occurrence. Same output modes, overrides, and `remember` as `/tailor`; downloads as `Cover Letter.docx`. |
| `GET /api/v1/bank` / `POST /api/v1/bank/entries` / `PUT,DELETE /api/v1/bank/entries/<id>` / `POST /api/v1/bank/profile` | Insertion bank CRUD (disabled when read-only). |
| `GET /api/v1/health` | Version, read-only flag, bank size. |

### Inputs

Both `proposals` and `tailor` accept either:

- `multipart/form-data`: `posting` (text), `template` (file), and optional JSON-string fields
  `values`, `profile`, `library`, `remember`
- `application/json`: `posting`, `template_b64` (base64 docx), and the same optional fields

`values` maps slot keys (`"MEASURABLE_IMPACT::0"`, from the proposals response) to final text.
An empty value leaves the `{{placeholder}}` in the document and reports it as unfilled.
`profile` (object) and `library` (entry list) override the bundled data files per request,
so multi-tenant callers can bring their own facts.

### Examples

```bash
# Get proposals
curl -X POST https://<deployment>/api/v1/proposals \
  -H "X-API-Key: $KEY" \
  -F "posting=<posting text>" \
  -F "template=@Template Resume.docx"

# Tailor with overrides, save the docx
curl -X POST https://<deployment>/api/v1/tailor \
  -H "X-API-Key: $KEY" \
  -F "posting=<posting text>" \
  -F "template=@Template Resume.docx" \
  -F 'values={"MEASURABLE_IMPACT::0": "a 70% reduction in deployment time"}' \
  -o "Tailored Resume.docx"

# Cover letter from the bundled template (no file needed)
curl -X POST https://<deployment>/api/v1/cover-letter \
  -H "X-API-Key: $KEY" \
  -F "posting=<posting text>" \
  -F "target_role=Digital Content Director" \
  -F "target_organization=Franklin & Marshall College" \
  -o "Cover Letter.docx"
```

The bundled cover-letter template lives at `data/cover_letter_template.docx`; regenerate it
from `scripts/build_cover_letter_template.py` after editing the wording. The bundled resume
template is `data/resume_template.docx`; re-standardize any resume's placeholder casing with
`python scripts/standardize_resume_template.py <source.docx>` (rewrites every placeholder to
consistent `{{UPPER_SNAKE_CASE}}`, preserving formatting).

Errors are consistent JSON: `{"error": "...", "detail": "..."}` with 400 (bad input/docx),
401 (bad API key), 403 (write attempted on read-only deployment), 422 (no placeholders found).

## Deploy to Vercel

```bash
npm i -g vercel
vercel --prod
```

`vercel.json` is included: all routes go to the Flask app via `api/index.py`, and
`RESUME_TAILOR_READONLY=1` is set because Vercel's filesystem is read-only (the bank ships
bundled; callers needing their own pass `profile`/`library` per request). To require auth,
set `API_KEYS` (comma-separated) in the Vercel project env — clients then send `X-API-Key`.

## Make it yours (the data files)

| File | What it is |
|---|---|
| `data/profile.json` | Static facts about you (rank, years of experience, team size…), keyed by normalized placeholder name. Also holds fallback skills headings. |
| `data/content_library.json` | Your **insertion bank**: scopes, metrics, outcomes, and accomplishment fragments tagged with skills. Maintained from the **/bank** page (or by hand). Proposed best-match per slot; the rest offered as ranked dropdown choices. |
| `data/skills_taxonomy.json` | ~340 known skills/technologies with aliases and categories. Extraction quality lives here — add anything your field uses. |
| `data/skill_groups.json` | Themed skill groups ("Cloud & Infrastructure", "Data & Analytics"…). The 5 groups the posting's keywords hit hardest become your skills headings, and their matched keywords become the rows. |
| `data/outcome_phrases.json` | Curated keyword → outcome/capability phrasing used to compose posting-driven Projects slots (e.g. CI/CD → "Faster, Safer Releases"). |

### The insertion bank workflow

Details a posting can never supply (your scopes, metrics, outcomes) live in the bank:

1. **Pick** — on the review screen, any slot with banked entries shows an "insert from bank" dropdown, ranked by relevance to the current posting.
2. **Remember** — tick *remember* next to a value you typed and it's saved to the bank when you generate, auto-tagged via the skills taxonomy. (Local deployments only.)
3. **Manage** — the **Bank** page adds/edits/deletes entries and edits profile values through `/api/v1/bank`. Saves are atomic and keep a `.bak`.

### Placeholder name normalization

`{{Role-Specific Expertise }}`, `{{role specific expertise}}`, and `{ROLE_SPECIFIC_EXPERTISE}` all
normalize to `ROLE_SPECIFIC_EXPERTISE`: braces stripped, trimmed, uppercased, non-alphanumerics
collapsed to underscores. Use the normalized form in `profile.json`, library `slots`, and API `values` keys.

### How placeholders get filled

| Strategy | Applies to | Source |
|---|---|---|
| PROFILE | `{{RANK}}`, `{{YEARS_OF_EXPERIENCE}}`, … | `profile.json` |
| KEYWORD_JOIN | `{{JOB_RELEVANT_TECHNOLOGIES}}`, `{{DELIVERY_PRACTICES}}`, … | top extracted keywords of the relevant category |
| KEYWORD_PHRASE | Projects slots: `{{PROJECT_TYPE}}`, `{{PROJECT_SOLUTION}}`, `{{STRATEGIC_OUTCOME}}`, … | deterministic phrase patterns composed from posting keywords, the posting's own phrases, and `outcome_phrases.json` — **verify the wording reflects real work** |
| LIBRARY_MATCH | `{{ACTION}}`, `{{MEASURABLE_IMPACT}}`, … | best-scoring bank entry (TF-IDF cosine + tag overlap, no entry used twice). Metric slots stay here on purpose — numbers must be real. |
| SKILLS_HEADER | the five skills heading slots | top-ranked theme group from `skill_groups.json`; falls back to the static `profile.json` label |
| SKILLS_DISTRIBUTE | the five `{{2 lines of comma separated skills}}` slots | the matched keywords of the theme group paired with each heading |
| MANUAL | anything unrecognized | the caller, via `values` (highlighted on the review screen) |
