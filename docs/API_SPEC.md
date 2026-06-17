# Resume Tailor API (Composer) — Integration Spec

The composer turns a job posting + a `.docx` template (with `{{UPPER_SNAKE_CASE}}`
placeholders) into a tailored résumé or cover letter. It owns the placeholder strategy
registry, the insertion bank, skill groups, the profile, occurrence-indexed filling, and
the review/override model. It optionally orchestrates three general-purpose downstream
services. **No LLM anywhere.**

## Workflows

Two pipelines, selectable per request (`workflow` field) or via the `DEFAULT_WORKFLOW`
env var. During integration the default is **`legacy`**.

| Workflow | Keyword source | Research | Determinism |
|---|---|---|---|
| `legacy` (default) | local taxonomy + RAKE, in-process | none | fully deterministic |
| `composed` | Parser API (canonical casing + emphases), classified locally into skill categories | advisory only (résumé) / framing content (cover letter) | deterministic for document output given (posting, template, profile, library, parser_version) — research excluded |

`composed` falls back to local extraction (and sets `meta.degraded=true`) if the Parser is
unconfigured or unreachable — résumé generation never hard-fails on a Parser outage.

## Auth & config

- This API authenticates UI→composer calls: if `API_KEYS` (comma-separated) is set, send
  `X-API-Key`. It holds downstream keys server-side.
- Env: `DEFAULT_WORKFLOW` (legacy|composed), `PARSER_API_URL`/`PARSER_API_KEY`,
  `RESEARCHER_API_URL`/`RESEARCHER_API_KEY`, `GENERATOR_API_URL`/`GENERATOR_API_KEY`,
  `RESUME_TAILOR_READONLY` (Vercel = read-only bank).

## Endpoints (`/api/v1`)

| Method | Path | Purpose |
|---|---|---|
| POST | `/proposals` | Scan template + parse posting → slots (proposed value, strategy, note, bank candidates), keywords, and (composed) advisory `research`. `template` optional → bundled default. |
| POST | `/tailor` | Fill the résumé. `values` overrides; returns docx (binary, or `{docx_b64, report}` with `Accept: application/json`). Research never affects output. |
| POST | `/cover-letter` | Like `/tailor` but for the cover letter; `target_role`/`target_organization` fill every occurrence; composed attaches `report.research` (company profile + role responsibilities, with attribution). |
| POST | `/compare` | Run legacy + composed on identical inputs → per-slot diff (`changed_count`, `slots[]`). The bug-finding tool for the composed path. |
| GET/POST/PUT/DELETE | `/bank*` | Insertion bank CRUD + profile (disabled when read-only). |
| GET | `/health` | Engine version, `default_workflow`, bank size, and downstream status/versions. |

### Common inputs (`/proposals`, `/tailor`, `/cover-letter`, `/compare`)
multipart or JSON. `posting` (required); `template`/`template_b64` (optional → bundled
default); optional `workflow`, `values`, `profile`, `library`, `remember`,
`target_role`, `target_organization`. `values` keys are slot keys `"NAME::occurrence"`
from the proposals response.

### Determinism boundary
`legacy` output and `composed` document output are reproducible from their inputs (plus
`parser_version` for composed). Cache on that tuple per workflow; **never** cache on
research. Research is advisory for résumés (surfaced in `/proposals.research`, never
folded into `values`) and is real, attributed content only on the cover-letter path
(`report.research`, with `sources[].attribution`).

## Downstream contracts

- **Parser API** (`/api/parse`, v1.0.0, lens-based): the composer requests
  `targets=[field, sector, technologies, keywords]` and reads `results.<lens>`. Keywords
  come from both the `keywords` lens (RAKE/lexicon, real scores) and the `technologies`
  lexicon (curated tech terms, assigned a descending synthetic score), merged and
  deduped by canonical `display` casing. `results.field.top` / `results.sector.top` seed
  the emphasis-driven research; `field.top.low_confidence` surfaces in `meta`. The composer
  classifies each keyword into its skill category (technology/tool_platform/methodology/
  soft_skill/certification/domain) using the local taxonomy — that classification is
  résumé-specific and stays here, not in the Parser.
- **Researcher API** (`/v1/research`, `/v1/research/batch`, contract 1.1.0): one batched
  call per request — one entry per emphasis (résumé `concept.overview`) or for
  company/role (cover letter). Honors `sources[].license` via the provided `attribution`
  strings. **`company.news`** (volatile) supplies clearly-favorable recent items
  (`min_tone ≥ 2.0`, tone-sorted) when a `target_organization` is given: advisory on the
  résumé (`proposals.company_news`, never inserted) and folded into `report.research.news`
  on the cover letter. News carries `as_of` + per-article dates; a disabled source
  (`501 source_disabled`) or outage degrades to no-news with a warning.
- **Document Generator API** (`/api/generate`): in the composed workflow the final `.docx`
  is rendered here. Because Jinja can't fill repeated identical placeholders
  (`{{SKILLS_LINE}}` ×5) with distinct values, the composer first rewrites each occurrence
  to a unique variable (`{{SKILLS_LINE__0}}`…) and sends a flat content map
  (`tailor.docxio.generator_render`). If the Generator is unavailable it falls back to the
  local filler (`report.meta.renderer` = `generator` | `local`). Legacy always renders
  locally.

## Failure / degradation matrix

| Downstream | State | Composer behavior |
|---|---|---|
| Parser | unconfigured / unreachable / no keywords | composed → local extraction, `meta.degraded=true` + reason |
| Researcher | unconfigured / down / degraded / 501 / 502 | résumé unaffected (advisory); cover letter still generates, `report.warnings` set |
| Generator | unconfigured / down | composed renders the docx locally instead (`report.meta.renderer=local`, warning on outage); legacy always local |

## Rollout

`legacy` is the integration-period default and the safe rollback (works with zero
downstream services). Use `/compare` to drive composed-vs-legacy diffs to zero unexpected
deltas, then flip `DEFAULT_WORKFLOW=composed`.
