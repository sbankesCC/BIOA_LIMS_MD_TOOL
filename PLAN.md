# Build plan: LabVantage Consumable Type Extractor pilot (BioA)

After approval, this plan is saved as `PLAN.md` at the repo root. It is the first commit of milestone 1.

## Context
BioA lab staff create LabVantage Consumable Types by hand from methods, study plans and worksheets.
This pilot reads those documents, proposes records with their sources, guides a user through fixing
problems, and writes the DFD loader plus an audit workbook. The design is complete: `docs/`
(ARCHITECTURE, CONTRACTS, UI_SPEC, mockups) and `clients/bioa/` (config). This plan sets the build
order, file layout, interfaces, tests and how each milestone is checked.

Rules the plan follows:
- Contracts, config loaders and deterministic code are built and tested before any LLM code.
- Every milestone ends with passing tests, a commit, and a stop for review. Each starts in a fresh session.
- The back end comes first. Its OpenAPI schema is reviewed and locked before front-end work starts.

## Decisions taken in the interview
1. **Settings and what blank means.** The app starts with every blank setting.
   - Blank means no limit: `MAX_FILE_SIZE_MB`, `MAX_FILES_PER_RUN`, `MAX_INPUT_TOKENS`, `MAX_DUPLICATE_JUDGE_CALLS`.
   - Blank keeps everything: `LLM_TRACE_RETENTION_DAYS`.
   - `MAX_REEXTRACT=1` (the documented default).
   - No usable blank meaning: `LLM_PROVIDER`, `OPENAI_API_KEY`, `EXTRACTION_MODEL`, `VERIFICATION_MODEL`,
     `DUPLICATE_JUDGE_MODEL`, `LLM_RETRIES`, `PILOT_USER`, `PILOT_USER_ROLES` (comma list, e.g. `user,admin`).
     The app still starts. The feature that needs one fails with a plain message naming it
     ("Set PILOT_USER in .env, then restart the app").
   - `REVIEW_DB=./data/review.sqlite` (a path value, like `CHECKPOINT_DB`).
   - The committed `env.example` lists only `CLIENT_CONFIG_DIR`, `STORAGE_DIR`, `CHECKPOINT_DB` and the LLM settings.
     M1 adds the others with the meanings above: the limits, retention, `LLM_RETRIES` and `PILOT_USER*` blank,
     `MAX_REEXTRACT=1`, and `REVIEW_DB` as above. Each gets a comment saying what blank means.
     Tests set their own values.
2. **Issue catalogue: one-time edit allowed.** In milestone 5 I add the missing codes to
   `clients/bioa/issue_catalogue.yaml`, bump it to `0.5` and show you the diff. Proposed codes:

   | Code | Level | Severity | Flags | Message (draft) |
   |---|---|---|---|---|
   | `POSSIBLE_DUPLICATE_IN_RUN` | record | warning | | "This may be the same material as {other}. Exclude one, or confirm they are different." |
   | `UNREPORTED_CONFLICT` | field | warning | individual_review | "Another source may give a different {field}. Open the source and check." |
   | `RECORD_DROPPED_ON_REEXTRACTION` | record | warning | | "Re-extraction did not return this record. Check it, or exclude it." |
   | `EXCLUDED_ITEM_CHALLENGED` | run | warning | individual_review, note_required | "These left-out items may be consumables: {items}. Add them outside the tool or confirm, and note what you did." |
   | `REFERENCE_DATA_MISSING` | run | warning | | "No existing Consumable Types were uploaded, so the check against LabVantage was skipped. Upload them in Admin, or check names in LabVantage." |
   | `NO_READABLE_DOCUMENTS` | run | error | | "None of the files could be read. Check the files and start a new run." |
   | `EXTRACTION_FAILED` | run | error | | "The extraction could not be completed. Retry the run; if it fails again, contact support." |

## Proposals (approve or change with the plan)
- **PDF library: `pypdfium2`** (Apache-2.0/BSD): per-page text extraction, plus rendering of scanned
  pages to PNG (with Pillow). Not PyMuPDF, because its AGPL license is a risk for a client tool.
- **Word: `python-docx`**. **Excel: `openpyxl`**. **Checkpointer: `langgraph-checkpoint-sqlite`**.
  **Multipart: `python-multipart`**. **OpenAI: `openai`**. Dev only: `fpdf2` (writes synthetic text PDFs
  for tests), `httpx` (TestClient).
- **Layout:** `pyproject.toml` and `uv.lock` at the repo root, with the package in `backend/app`
  (hatchling `packages = ["backend/app"]`). `uv run pytest` and the eval command work from the root,
  and `uv run uvicorn app.main:app` works from `backend/`. CLAUDE.md commands are updated to match.
- **Front end:** plain React + TypeScript + Vite. No component library. Hand-written components with
  global CSS variables taken from the mockups (`tokens.css`) and one CSS file per component. Dependencies:
  `react`, `react-dom`, `react-router-dom`, `openapi-fetch`. Dev: `openapi-typescript`, `vitest`,
  `@testing-library/react`, `jsdom`. The searchable dropdown, dialogs and grid are built by hand.
- **Token estimate (no network):** characters / 3.5 for text, plus a fixed cost per page image based
  on the OpenAI image-tile formula. It is conservative on purpose. The constants live in one module.
- **OpenAI call shape:** Responses API with structured outputs (strict JSON schema generated from
  Pydantic plus `field_rules.yaml`). Text and images go in one user message.

## Repository layout (target)
```
pyproject.toml, uv.lock, env.example, PLAN.md
backend/
  app/
    main.py                 # FastAPI app factory, startup config validation
    settings.py             # env settings; require_setting(name) helper
    logging_setup.py        # JSON-lines logger (CONTRACTS §11)
    ids.py                  # prefixed IDs, issue_id key hash
    config/                 # loaders + validators: field_rules, issue_catalogue, lookup_lists,
                            #   dfd_template, reference_mapping, prompts; ConfigBundle with versions
    contracts/              # Pydantic models: chunk, extraction, verification, judge, record,
                            #   issue, changes, run, export, trace, api (request/response)
    llm_schema.py           # JSON Schemas for the LLM, from models + field rules
    status_rules.py         # CONTRACTS §2 status table check
    storage/                # run_store.py (files), review_db.py (SQLite, schema + queries)
    ingest/                 # docx.py, pdf.py, xlsx.py, chunking.py, loader_detection.py, ingest.py
    transform/              # cleaning.py, lookup_matching.py, numbers.py, transform.py
    verification/           # citation_check.py
    validation/             # field_checks.py, conditions.py, findings_to_issues.py,
                            #   duplicates.py (exact/normalized/shortlist), judge_cache.py,
                            #   action_needed.py, service.py
    llm/                    # client.py (interface), fake_client.py, openai_client.py,
                            #   tracing.py, prompt_builder.py, token_estimate.py
    agents/                 # extraction.py, extraction_verification.py, duplicate_judge.py
    graph/                  # state.py, nodes.py, routing.py (only routing), build.py
    review/                 # service.py (changes, recheck, verify, undo), view.py (flattened grid)
    export/                 # loader.py, audit_workbook.py, service.py
    admin/                  # lookup_lists.py, reference_data.py
    api/                    # auth.py (placeholder dependency), errors.py, routes_*.py
    evals/                  # __main__.py, case_loader.py, scoring.py, report.py
  tests/                    # unit/, integration/, fixtures/ (all synthetic), conftest.py
  openapi.json              # locked schema (milestone 9)
frontend/                   # Vite app (milestones 11–14)
evals/cases/synthetic_001/  # one synthetic case so the harness runs
```

## Milestones

### M1: Project skeleton, settings, config loaders, startup validation
- `pyproject.toml` (ruff with `D` docstring and `N` naming rules, pyright strict on `backend/app`),
  `uv add` the approved packages, `.gitignore` additions, `env.example` gets the new blank settings.
- `settings.py`: every setting optional. Blank limit settings give `None`, meaning no limit. `require_setting()` raises
  `MissingSettingError` with a message naming the setting, for settings with no usable blank meaning.
- `config/`: Pydantic models and loaders for every file in CONTRACTS §12. Validation covers 22 fields
  in order, roles, lookup sheets exist, DFD headers equal field-rule columns, catalogue severities,
  prompt headers and placeholders, and the `_metadata` version. `ConfigBundle` holds a version per file.
- `main.py` + `GET /health`. Startup loads and validates config and fails with a clear message if it is broken.
- `logging_setup.py`: JSON lines, with ID, count and duration fields only.
- **Tests:** loader happy paths. Broken-config cases (built in tmp dirs from copies). **Config consistency
  test** against `source/BAL_Consumable_Type_Definitions.xlsx`: field list, order, type, M/O, limits,
  List/Boolean, defaults, seed lookup values, with an explicit allowed-differences list and reasons
  (blank_for_now fields; "Fields to add" rows; the removed blank Consumable Class entry; the leading
  line break removed from Manufacturer and Supplier; the Mandatory/conditional mapping). **No-client-literals
  test**: no file under `backend/` contains a lookup value or a field column name from `clients/bioa/`.
  The app starts with every setting blank.
- **Verify:** `uv run pytest`, `ruff check`, `ruff format --check`, `pyright`. Start uvicorn and `GET /health`.

### M2: Contracts and LLM schema generation
- All Pydantic models for CONTRACTS §1–§11, plus the stored record with all 22 fields.
- `llm_schema.py`: builds the extraction schema with one property per `extracted` field (list for
  `multi_value`), plus the verification and judge schemas. All are strict-mode compatible.
- `status_rules.py`: the §2 table, `found_in` ≥ 1, chunk IDs exist, every extracted field present,
  and no non-extracted fields.
- `ids.py`: `rec_0001` counters, and `issue_id` = `iss_` + a short stable hash of (code, record_id, field, value).
- **Tests:** CONTRACTS examples parse. The schema has exactly the 17 extracted fields. Each status-rule
  violation is reported (`test_conflicting_without_two_alternatives_is_violation`, …). Issue IDs are stable.

### M3: Run store and ingestion
- `run_store.py`: `STORAGE_DIR/runs/<run_id>/{uploads,chunks.json,pages/,llm/,exports/}` with a SHA-256 per file.
- Ingest: `.docx` paragraphs grouped by heading path, tables as `table_rows` (row groups keep a table
  whole; very large tables are split into header-repeated groups). `.pdf` text per page. A page with no
  text is rendered to PNG and becomes a `page_image` chunk, with run issue `SCANNED_PAGES`. `.xlsx` is split
  per sheet and row range (`doc03-sReagents-r12-20`). Loader detection: header row matches the DFD
  columns, so the file is skipped with `LOADER_FILE_UPLOADED`. An unreadable file gets `FILE_UNREADABLE`.
  Stable chunk IDs.
- Synthetic fixtures are generated by `tests/fixtures/make_documents.py` (python-docx, openpyxl, fpdf2,
  Pillow image-only PDF), each labeled `synthetic` in its content and file name.
- **Tests:** chunk IDs and kinds for each format. A reagent table stays in one chunk. A scanned page becomes
  an image chunk with no text in state. Loader detection. Rejected extensions. Chunk IDs are the same on re-ingest.

### M4: Transformation and citation check
- Cleaning (trim, collapse spaces, remove control characters). Lookup matching (exact, then one case-insensitive
  match, then a normalized match ignoring case/spaces/°), which gives `FORMAT_CORRECTED` or `NOT_IN_LOOKUP`. Boolean Y/N.
  Numbers from text (`1e4 cps/uL` → `10000`, giving `NUMBER_READ_FROM_TEXT`; unreadable → kept as written and later `WRONG_TYPE`).
  Catalog No joined with ", ". Defaults only on empty fields (`DEFAULT_APPLIED`). `blank_for_now`/`system` origins. The output section only.
- Citation check per CONTRACTS §2: `verified` / `not_verified` / `not_checkable`.
- Transformation records its notes (FORMAT_CORRECTED etc.) as "transform notes" in the output section's
  `changes`. Validation turns them into issues, so only validation creates issues.
- **Tests:** every rule above, plus `test_transformation_never_overwrites_user_value` and
  `test_container_tracking_default_is_applied_literally`.

### M5: Validation service (deterministic) + catalogue edit
- Add the 7 catalogue codes (diff shown, version 0.5).
- Field checks: required, type, max length, lookup, disallowed characters (Greek, control). Condition groups.
  Verification findings become issues (verdict → code map). Name unique in run. Reference data: exact match gives
  `EXISTS_IN_LABVANTAGE` (ignoring the active flag). Normalized match gives `POSSIBLE_DUPLICATE`. Shortlist of up to `shortlist_size`.
  A `DuplicateJudge` protocol plus a cache keyed on identifying fields + reference version + prompt version.
  Over `MAX_DUPLICATE_JUDGE_CALLS` gives `DUPLICATE_CHECK_SKIPPED`. No reference data gives `REFERENCE_DATA_MISSING`.
  `OR_EQUIVALENT` once per record. Not-found optionals give `OPTIONAL_NOT_FOUND`. `action_needed`.
- Issue lifecycle: same key keeps the same ID and its accepted state. A changed value resolves the old issue.
- **Tests:** one test per issue code; cache hit/miss; judge limit; validation never changes a value.
  Expected and documented: every record gets `TOO_LONG` on Container Tracking Method ("Individual" vs limit 1), as the workbook says.

### M6: Review database and review service
- `review_db.py`: the tables in CONTRACTS §7 plus `duplicate_judgments`, `lookup_versions`,
  `reference_versions`, `admin_events`. Plain `sqlite3` with a schema version.
- Review service: store changes as pending (dedupe by `change_id`; `set_value` reason rule; list values must
  be current lookup values; an individual-review accept needs `source_viewed` and a note when required).
  Re-check applies the pending changes and calls Validation. Undo bulk. Exclude and restore. Verify: re-check, then
  blockers or the label; other warnings are accepted by the verifier. Any change clears the label. Audit events.
- Flattened review view (grid rows, cells with display value, "TEST VALUE" placeholder, color, sources, alternatives).
- **Tests:** each change type; resend is ignored; bulk accept of an individual-review issue is rejected; Verify
  blocked or allowed; the label is removed by a later change; undo bulk.

### M7: Export and admin services
- Export: re-check if changes are pending. The loader comes from the template, with 22 columns, `output.value` only, and excluded records left out.
  The audit workbook has its 5 sheets. Numbered file names with en dashes and "– draft".
- Lookup admin: download current (with `_metadata`), upload checks (all from ARCHITECTURE §4.11), diff,
  pending version, apply as the next `vN`, restore. The seed in `clients/bioa/` is never written; admin versions are
  stored under `STORAGE_DIR/lookup_lists/`. New runs pick up the current version.
- Reference data admin: `.xlsx`/`.csv`, column check via the mapping, versioned snapshot, apply.
- **Tests:** the loader round-trips through openpyxl with the right headers and rows; audit sheet columns;
  every upload check failure (stale version, case-only duplicates, renamed used sheet…); restore.

### M8: LLM client, agents and LangGraph flow
- `LLMClient` protocol: `complete(request) -> response` with text and image parts and a JSON schema.
  `FakeLLMClient` returns fixtures by node and attempt. `OpenAIClient` needs `OPENAI_API_KEY` and the model setting
  for that node (via `require_setting`). Every call is traced to the run store (CONTRACTS §10). Retries use `LLM_RETRIES`.
- Prompt builder fills `{field_section}`, `{reextraction_section}`, `{chunks}`, `{citation_results}`,
  `{records}`, `{excluded_items}`, `{record}`, `{candidates}`. Static text comes first. HTML comments are removed.
  Prompt-version bumps are reported to you.
- Agents: extraction (token estimate gate, schema and status checks with a retry), verification, duplicate judge (plugged into M5's protocol).
- Graph: nodes with state limited to references; `routing.py` holds every edge rule; re-extract only affected
  records and missed candidates, keeping `record_id`s and flagging dropped ones. The SQLite checkpointer uses
  `thread_id = run_id`. The end node writes to the review DB, and the status becomes `in_review`. Status is updated per node.
- **Tests (fake LLM only):** happy path; re-extract loop and limit; schema violation retry then failure; too large
  with no call; dropped record kept; no readable document leads to failed; state never contains chunk text; logs hold no values.
  A manual `openai` smoke test is skipped unless the env is set.

### M9: API layer, then **STOP for OpenAPI review and lock**
- Every endpoint in CONTRACTS §13. Placeholder auth dependency (`PILOT_USER`/`PILOT_USER_ROLES`; 403
  for non-admin). One error shape with plain messages. Upload limits (413) only when the limit is set. The background graph runs in a thread.
  Retry creates `retry_of`.
- Export `backend/openapi.json`. A test fails if the generated schema differs from the committed file (this is the lock).
- **Tests:** every endpoint through TestClient with the fake LLM, end to end from upload to export download.
- **Verify:** you review `openapi.json` and approve it. It is then locked.

### M10: Eval harness foundation
- `python -m app.evals run --suite cases`: loads cases, flags a field-rules version mismatch, runs the same graph
  3 times, scores records, fields, status, citations and seeded errors, and writes JSON + CSV to `evals/reports/`.
- One synthetic case (`evals/cases/synthetic_001/`) with fake-LLM fixtures.
- **Tests:** scoring functions; an unlabeled key is not counted as wrong; description excluded; report shape.

### M11: Front end foundation
- Vite + React + TS in `frontend/`; `npm run generate:api` (openapi-typescript from `backend/openapi.json`);
  `openapi-fetch` client; `tokens.css` (Clarkston blue, gold, neutrals, status colors, fonts with fallbacks, spacing).
  Top bar, router, "How it works" popup (first visit in localStorage). The `StatusBadge` component always shows icon + word.
- Screens: Start a run (name pre-fill, upload rules, file list, recent runs) and Processing (6 steps mapped from status, failed + Retry).
- **Tests:** vitest component tests; `npm run typecheck`, `npm run build`.

### M12: Review screen: grid and resolution panel
- Header, run banner (dismissal remembered per run in localStorage), summary strip and filters. A read-only grid with sticky
  header, pinned columns, "Found in" links, source viewer with highlight, "as written → exported" pairs, and "TEST VALUE".
- Panel: issue navigation across records, issue list, one expanded issue, an action component per issue type (UI_SPEC table),
  searchable dropdown (closest matches first), Save and next, re-check when the user moves to another record.

### M13: Bulk actions, exclude, Verify, export
- Change all, Fill missing, Accept all of a type, Resolve repeated conflicts (bulk-preview with a confirmation list);
  undo; exclude dialog with a reason; restore; Verify dialog (three cases); export and post-export state with downloads.

### M14: Admin screens and finish
- Lookup lists (current card, upload report, diff, Apply as vN, history, Restore) and Reference data (same pattern).
- Possible-duplicate side-by-side comparison. A final pass against the mockups. A manual end-to-end run with the fake provider and screenshots.

## Verification (every milestone)
`uv run pytest`, `uv run ruff check . && uv run ruff format --check .`, `uv run pyright`; front-end milestones also
`npm run typecheck`, `npm test`, `npm run build`. Real command output is shown, then a commit, then a stop.
The real OpenAI path stays unverified until you fill in `.env` and run the smoke test. Extraction quality stays
unverified until labeled BioA cases exist (ARCHITECTURE §9).

## Confirmed in review
- Container Tracking Method stays literal: limit 1 vs "Individual"/"Together", so every record is red `TOO_LONG`
  until BioA edits the workbook.
- A vendor not on the Manufacturer/Supplier list is red `NOT_IN_LOOKUP` (intended).
- Source "Mandatory" for Expected Amount Unit and Expected No of Containers is read as conditional.
- Issue message wording is a draft and is fine for the pilot.
- Fonts: the fallbacks (Libre Franklin from Google Fonts, as in the mockups).
- The first admin lookup apply after the seed (`v0-seed-3` since 2026-10-20) becomes `v1`.

## Open questions
- None open.

## Decisions made during the build
- **M1: "N/A" in Manufacturer and Supplier (reversed 2026-10-20).** M1 left BioA's "N/A" entry out of
  the seed. Reversed by your decision: "N/A" is back in both seed lists at its source position, the
  allowed difference is removed from the consistency test, and the seed version is `v0-seed-3`.
- **M7 lookup upload vs length limits (decided 2026-10-20).** A lookup value longer than its field's
  length limit is a warning in the upload report, not a rejection. Records still get `TOO_LONG`.
- **M5 issue catalogue edit approved** as listed above (7 codes, version 0.5); diff reviewed after commit.
- **M1: blank `CLIENT_CONFIG_DIR`.** The app starts with no config loaded; `/health` names the setting.
  A set but broken config stops startup with the list of problems.
- **M1: DFD template version** is a short SHA-256 of the file (`sha256:…`), since the file has no version.
- **M1: no-client-literals test** compares whole string constants (Python) and JSON strings with the
  lookup values and column names. One-character values (`Y`, `%`, `L`) are left out as generic tokens.
- **M1: packages.** `pydantic-settings` (reads env and `.env`) and dev `types-pyyaml` were added
  beyond the approved list.
- **M3: run store layout.** Besides the planned folders, each run has `documents.json` (file name,
  type, SHA-256, size, page count, ingest status). Uploads are stored as `uploads/<document_id>/<name>`,
  so repeated names never clash. Stored references (`image_ref`, `upload_ref`) are relative to
  STORAGE_DIR, like the trace file paths in CONTRACTS §10.
- **M3: chunk sizes.** A Word section is split at 4000 characters on paragraph boundaries. A table stays
  whole up to 50 data rows; larger tables are split into groups of 50 with the header row repeated.
  Sheets: 50 data rows per chunk, the first non-blank row is the header and is repeated. PDF: one
  chunk per page (kind `paragraph`, since PDF text has no table structure). Constants in `ingest/chunking.py`.
- **M3: loader detection.** A workbook is a loader when the first non-blank row of any sheet contains
  every DFD template header (extra columns allowed).
- **M4: transform notes format.** `output.changes` holds plain clean-up notes ("trimmed whitespace",
  "collapsed spaces", "removed control characters") and coded notes for validation, written as
  `CODE: {"original": ..., "value": ...}` (codes FORMAT_CORRECTED, NOT_IN_LOOKUP, NUMBER_READ_FROM_TEXT,
  DEFAULT_APPLIED). `transform/notes.py` reads them back (`find_transform_notes`).
- **M4: lookup matching never guesses.** The normalized match must also be unique: two list values
  that match after removing case, spaces and "°" (the seed Container Type list has such a pair) give
  NOT_IN_LOOKUP. Booleans accept only Y or N in any case; words such as "Yes" are kept as written.
- **M4: defaults** fill not-found fields (and found values that clean to empty), never conflicting
  fields, and are applied literally (no lookup matching). An empty extracted field has origin `extracted`.
- **M5: record name field.** The record's name (for DUPLICATE_IN_RUN, EXISTS_IN_LABVANTAGE,
  POSSIBLE_DUPLICATE and the judge shortlist) is the first field in `field_rules.yaml` (the first
  DFD column, the LabVantage key). The config has no explicit "name" flag; this keeps names out of code.
- **M5: judge cache key** uses every `extracted` field's current output value (not only the six
  identifying fields ARCHITECTURE §4.8 lists, which exist only in a prompt comment). Safe: it can only
  cause extra judge calls, never a stale result. A config flag could narrow it later.
- **M5: duplicate judge limit** applies per validation pass (graph end, each re-check); cached
  results do not count. The service takes the limit and returns `judge_calls_made`.
- **M5: shortlist** = existing types whose normalized name (case, spaces, "°" removed) has a difflib
  ratio ≥ 0.6 with the record's, closest first, up to `shortlist_size`. A normalized name match
  gives POSSIBLE_DUPLICATE without a judge call. No shortlist, no call.
- **M5: findings apply to extracted values.** Citation and verification-agent issues (and
  OR_EQUIVALENT, UNREPORTED_CONFLICT) are not raised once a person set the value (origin
  `user_edited` or `fixed`), so they resolve. Transform notes always apply to the current value.
- **M5: excluded records** are not validated: they keep their earlier issues unchanged and get
  `action_needed = excluded`; they are left out of the in-run name check and the reference check.
- **M6: lookup values in review** are checked against the run's own lookup version (captured at
  its start), not the admin's latest, because validation checks the same version (ARCHITECTURE §6).
  Y/N fields only take Y or N. Only `extracted` fields can be changed.
- **M6: a picked alternative** gets origin `user_edited` (as in the CONTRACTS §4 example) and is
  formatted with `transform_value`, so FORMAT_CORRECTED or NOT_IN_LOOKUP apply to the picked value.
  `set_value` stores the value as typed (blank text = empty) and clears `output.changes`.
- **M6: undo bulk** puts back each change's stored `before_state`, newest first, but only where the
  target still holds what the change wrote; a value changed again later keeps the later change.
  Undo cannot itself be undone, and a bulk action can be undone once.
- **M6: Verify** accepts every remaining open warning of included records (closed by the verifier);
  grey issues stay open and never block. The verified label is removed when a change is saved
  (a resent, ignored change does not remove it).

## Progress log

### M2: Contracts and LLM schema generation (done)
- `backend/app/contracts/`: Pydantic models (unknown keys rejected) for CONTRACTS §1 `chunk.py`,
  §2 `extraction.py`, §3 `verification.py`, §3a `judge.py`, §4 `record.py` (stored record and
  `find_record_field_problems`, which checks all 22 field keys against the field rules), §5 `issue.py`
  (plus `IssueHistoryEntry`), §6 `changes.py` (one model per change type, chosen by `type`; `StoredChange`),
  §7 `run.py` (`RunInfo`, `RunStatus`, `AuditEvent`) and `export.py` (`ExportInfo`, one model per audit
  sheet row, §8), §9 `eval_case.py` (`case.yaml`), §10 `trace.py`, §11 `log_line.py`.
- `llm_schema.py`: `build_extraction_schema(field_rules)`, `build_verification_schema(field_rules)`,
  `build_judge_schema()`. Generated from the models, `$ref`s inlined, every object closed with all
  properties required; only `type/properties/items/anyOf/enum/const` kept from Pydantic.
- `status_rules.py`: `find_status_violations(output, field_rules, chunk_ids) -> list[StatusViolation]`.
- `ids.py`: `IdCounter`, `make_record_id_counter(existing_ids)`, `make_issue_id(code, record_id, field, value)`.
- Tests: 118 total, 65 new. CONTRACTS examples are parsed straight from `docs/CONTRACTS.md`.
- Decisions the docs did not cover:
  - Re-extraction returns an existing record's `record_id` in `record_ref` (as the extraction prompt
    says), so the §2 schema needs no extra key.
  - `output.value` is always text or null; numbers are stored as text (e.g. "10000"). Export converts.
  - The stored record's `verification.findings` holds record-level findings; field findings go to
    each field's `verification.verdict`/`note`.
  - `set_value` accepts a null value, which clears the field (the review service still applies the reason rule).
  - Issue ID: SHA-256 of the JSON list `[code, record_id, field, value]`, first 12 hex characters.
  - Extraction schema: each field's `description` is its DFD column name (read from config). The
    verification schema limits `field` to the extracted keys.
  - Extra status checks: duplicate `record_ref`, blank values count as missing, wrong value shape
    (list vs text), and excluded items' chunk IDs.
  - The §4 example's `"alternatives": ["..."]` shorthand is expanded by the test before parsing.
  - Left for later milestones: LangGraph state (§7) in M8 `graph/state.py`, the API error shape (§13)
    in M9, the expected-extraction model (§9) in M10. `AuditEvent.event` is free text until M6.

### M3: Run store and ingestion (done)
- `storage/run_store.py`: `RunStore(storage_dir)` with `create_run(run_id)`, `open_run(run_id)`,
  `resolve_ref(ref)`; `RunFolder` with `save_upload(file_name, content) -> DocumentInfo` (SHA-256,
  next `docNN`), `read_documents`/`write_documents`, `write_chunks`/`read_chunks`/`find_chunk`,
  `save_page_image(chunk_id, png) -> ref`, `upload_path`, `make_ref`. `DocumentInfo` (status
  `uploaded`/`ingested`/`unreadable`/`loader_skipped`). Plain `RunStoreError` messages.
- `ingest/`: `file_types.py` (`read_file_type`, `RejectedFileError`: only `.docx`/`.pdf`/`.xlsx`, case
  ignored, no folder parts in names; the run store checks before writing), `chunking.py`, `docx.py`,
  `pdf.py` (pypdfium2; scanned pages rendered at scale 2 to `pages/<chunk_id>.png`), `xlsx.py`,
  `loader_detection.py`, `ingest.py` (`ingest_run(folder, bundle) -> IngestResult` with documents,
  chunks, run issues and `readable_document_count()`; writes `chunks.json` and `documents.json`).
- `config/issue_catalogue.py`: `fill_message(message, values)` added (unknown placeholders stay as written).
- Fixtures: `backend/tests/fixtures/make_documents.py` generates every synthetic file into a temp
  folder at test time (session fixture `synthetic_documents`); no binary fixtures are committed.
- Tests: 169 total, 51 new (`unit/test_run_store.py`, `unit/test_chunking.py`, `integration/test_ingest.py`).
- Decisions the docs did not cover (significant ones also above):
  - Chunk IDs: Word `doc01-c001`, PDF `doc02-p04-c007` (one counter per document, page included),
    Excel `doc03-sReagents-r12-20` (sheet name letters and digits only; a clash adds the sheet position).
    Document IDs `doc01`, `doc02`, ... in upload order.
  - Word: headings are the built-in `Heading N` and `Title` styles; the heading path is in `section`,
    not in the chunk text. Headers, footers and text boxes are not read. Table cells are joined with
    ` | `, one row per line; line breaks inside a cell become spaces.
  - Excel: saved values are read (formulas not recalculated); whole floats lose `.0`; dates are ISO;
    blank rows and trailing blank cells are dropped; every worksheet is read, hidden ones too.
  - Ingest run issues: one per document; the issue key's value is the `document_id`; `details` holds
    `document_id` (and `pages` for SCANNED_PAGES). Any reader error means FILE_UNREADABLE.
  - Ingest returns chunk text in `IngestResult`; the graph (M8) must keep only document and chunk
    references from it.

### M4: Transformation and citation check (done)
- `transform/cleaning.py`: `clean_text(text) -> CleanedText(value, notes)` (control characters removed,
  ends trimmed, whitespace runs collapsed to one space). `transform/notes.py`: `TransformNote(code,
  original, value)` with `to_text()`, `parse_transform_note`, `find_transform_notes(changes)`.
- `transform/lookup_matching.py`: `match_lookup_value(value, allowed) -> MatchResult(value, note)`
  (exact, then one case-insensitive, then one normalized match), `match_boolean_value(value)` (Y/N).
- `transform/numbers.py`: `read_number(value) -> NumberResult(value, note)`.
- `transform/transform.py`: `transform_records`/`transform_record(record, field_rules, lookup_lists)`,
  `transform_field`, `build_field_output(rule, extraction, lookup_lists)`, and
  `transform_value(rule, raw_value, lookup_lists) -> TransformedValue(value, changes)` (for M6, e.g.
  a picked alternative). Writes only `output`; `user_edited` and `fixed` outputs are never touched.
- `verification/citation_check.py`: `check_field_citations(extraction, chunks) -> CitationCheck | None`,
  `check_record_citations(record, chunks)` (sets only `verification.citation_check`), `index_chunks`.
- Tests: 234 total, 65 new (`unit/test_cleaning.py`, `test_lookup_matching.py`, `test_numbers.py`,
  `test_transform.py`, `test_transform_notes.py`, `test_citation_check.py`).
- Decisions the docs did not cover (significant ones also above):
  - Numbers: a plain number (`-20`, `2.50`) is kept unchanged. Text with exactly one number gives it
    as plain digits (thousands commas dropped, exponent expanded, written digits kept). No number or
    several (`2-8`, `1 x 10^4`) keeps the text unchanged with no note; validation flags WRONG_TYPE.
    A sign counts only at the start or after a space.
  - Multi-value parts are cleaned one by one; empty parts are dropped; each clean-up note appears once.
  - NOT_IN_LOOKUP is also recorded as a transform note (same issue key as validation's lookup check).
  - Citation check: comparisons drop all whitespace and ignore case. An unknown chunk ID or any quote
    missing from its chunk gives `not_verified`. A value found in a checked text quote is `verified`
    even when other pairs are on page images; a value found only in image quotes is `not_checkable`.
    A list value needs every entry in a checked quote. A conflict is checked per alternative (any
    `not_verified` wins, then `not_checkable`). A not-found field gets no result (null).
  - To watch in M8/M10: Word table cells are joined with ` | ` in chunk text, so a table-row quote
    without the pipes fails the citation check. The prompt shows the chunk text, so quotes should
    keep them; check this with the eval cases.

### M5: Validation service + catalogue edit (done)
- Catalogue: the 7 interview codes added to `clients/bioa/issue_catalogue.yaml`, version `0.5`
  (commit `9ed218b`, on its own). Record-level codes in `record_issues`, run-level in `run_issues`.
- `contracts/reference.py`: `ReferenceType` (`candidate_id`, name, version, description, class,
  active flag, version status) and `ReferenceData(version, types)`, for M7's reference admin.
- `validation/`: `codes.py` (code constants, `VALIDATION_CODES`), `issues.py` (`IssueDraft`,
  `make_issue`: catalogue severity, filled message with the column name, stable ID),
  `field_checks.py`, `conditions.py`, `findings_to_issues.py` (verdict → code maps), `duplicates.py`
  (name field, in-run duplicates, exact/normalized/shortlist, judge), `judge_cache.py`
  (`DuplicateJudge` and `JudgeCache` protocols, `JudgeRequest`, `InMemoryJudgeCache`,
  `make_judge_cache_key`, `JudgeRunner` with the call limit), `lifecycle.py` (`merge_issues`),
  `action_needed.py`, `service.py` (`validate_run(records, config, runner, reference, findings,
  previous_issues) -> ValidationResult`, `make_validation_config`, `ProcessingFindings`).
- Verdict → code: citation `not_verified` → CITATION_NOT_VERIFIED, `not_checkable` → SCANNED_SOURCE;
  `contradicted`/`unsupported`/`present_missed` → CONTRADICTED_BY_SOURCE/UNSUPPORTED_BY_SOURCE/
  VALUE_PRESENT_MISSED; `not_a_consumable_type`/`duplicate_within_run`/`should_be_split` →
  NOT_A_CONSUMABLE_TYPE/POSSIBLE_DUPLICATE_IN_RUN/SHOULD_BE_SPLIT; unreported conflicts →
  UNREPORTED_CONFLICT; missed candidates → MISSED_CANDIDATES_UNRESOLVED; excluded item challenges →
  EXCLUDED_ITEM_CHALLENGED; dropped records → RECORD_DROPPED_ON_REEXTRACTION.
- Tests: 290 total, 56 new (`unit/test_validation_issue_codes.py`, `unit/test_validation_service.py`,
  helpers in `unit/validation_helpers.py`). A test checks every catalogue code is raised by
  validation or listed as raised by ingest/graph (NO_READABLE_DOCUMENTS, EXTRACTION_FAILED,
  NO_RECORDS_FOUND, DOCUMENT_SET_TOO_LARGE are for M8).
- As documented, every record with Container Tracking Method not found gets TOO_LONG (plus
  DEFAULT_APPLIED) from the literal default "Individual" vs limit 1 (tested).
- Decisions the docs did not cover (significant ones also above):
  - Field issues are keyed by the current output value; record-level issues (condition groups,
    OR_EQUIVALENT, record verdicts) by null; name issues sit on the name field. Run issues listing
    items are keyed by the item text; DUPLICATE_CHECK_SKIPPED and REFERENCE_DATA_MISSING by null.
  - An empty field: unresolved conflict → CONFLICT_UNRESOLVED (instead of REQUIRED_MISSING or
    OPTIONAL_NOT_FOUND); required → REQUIRED_MISSING; optional → OPTIONAL_NOT_FOUND; conditional →
    only its condition groups. Booleans other than Y/N → NOT_IN_LOOKUP. Decimal = plain number,
    integer = digits with an optional sign. Greek = U+0370–03FF and U+1F00–1FFF; control = category Cc.
  - Two checks giving the same key (NOT_IN_LOOKUP from the lookup check and the transform note)
    give one issue. Codes validation does not own (ingest, graph) pass through `merge_issues` unchanged.
  - Resolved issues get `closed_by = null`; M6 records who triggered the re-check in issue history.
  - {other} in POSSIBLE_DUPLICATE_IN_RUN lists the run's record IDs named in the agent's note,
    else "another record in this run".
  - With `exact_match_ignores_active_flag: false`, an exact match on a type whose active flag is
    "N" is treated as a normalized match (POSSIBLE_DUPLICATE). BioA's config uses `true`.
  - Judge exceptions are not caught by validation (the M8 agent handles retries and errors).
  - For M6: store `ProcessingFindings` (verification output, dropped record IDs) per run so
    re-checks re-raise those issues; back `JudgeCache` with the `duplicate_judgments` table; clear
    coded notes from `output.changes` on `set_value` (else old FORMAT_CORRECTED notes reappear).

### M6: Review database and review service (done)
- `storage/review_db.py`: `ReviewDatabase(path)` (one sqlite3 connection, an RLock, nested
  `transaction()`), `open_review_db(settings)` (REVIEW_DB via `require_path`), `SCHEMA_VERSION = 1`
  in `schema_info` (another version is refused with a plain message). Tables: `runs` (RunInfo
  columns plus `findings` = ProcessingFindings and `excluded_items` as JSON), `records`, `issues`,
  `issue_history`, `changes` (status, `old_value`/`new_value`, `before_state`/`after_state`,
  `undone_by`), `exports`, `audit_events`, `duplicate_judgments`, `lookup_versions`,
  `reference_versions`, `admin_events`. `DatabaseJudgeCache` backs the M5 `JudgeCache`.
  `DataVersion` (upload_id, version_id, status pending/current/superseded, file_ref, by/at, summary).
- `review/`: `errors.py` (`ReviewError` with codes CHANGE_INVALID, BULK_ACCEPT_NOT_ALLOWED,
  RUN_NOT_IN_REVIEW), `state.py`, `change_checks.py` (CONTRACTS §6 rules), `apply_changes.py`
  (each change type, undo), `service.py` (`ReviewContext`, `save_changes`, `recheck_run`,
  `verify_run`), `view.py` (`build_review_view`, `count_review`).
- Tests: 333 total, 43 new (`unit/test_review_service.py`, `test_review_db.py`,
  `test_review_view.py`, helpers in `unit/review_helpers.py`). Verify tests that need a clean record
  drop the workbook's impossible Container Tracking Method limit in a test copy of the config only.
- Decisions the docs did not cover (significant ones also above):
  - Issue history is a child table `issue_history` of `issues`. "opened" steps have `by = null`
    (validation), written when processing is saved and on re-check; "resolved" steps and
    `closed_by` name the user whose re-check resolved the issue; "accepted" names the accepting user
    with the note. Undoing an accept writes "opened" with the note "acceptance undone".
  - A request with any invalid change saves nothing. A repeated `change_id` (stored or earlier in
    the same request) is ignored. Only warnings can be accepted; a resolved issue cannot be.
  - Changes are checked when saved, against the stored records and issues (the last re-check);
    the reason rule uses open issues only (an accepted warning does not count).
  - The `rechecking` status is not used: a re-check runs as one SQLite transaction under the lock,
    so no reader can see a half-applied state. Verify (re-check included) is one transaction too.
  - Audit events: `record_excluded`, `record_restored`, `bulk_undone`, `run_verified`,
    `verified_label_removed` (per run, `audit_events`); admin actions go to `admin_events`.
  - Data versions are keyed by `upload_id`; `version_id` (e.g. `v1`) is given on first apply and
    kept on restore. No current row means the seed in `clients/bioa/` is in use.
  - Review view: placeholder cells are grey; `written_value` only when it differs from the value;
    cell issues list open and accepted issues, and only open ones tint the cell.
  - Left for M9: `bulk-preview` (same field, code and value) and the API error mapping above.
