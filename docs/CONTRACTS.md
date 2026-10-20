# Contracts

The defined contracts for the pilot. Build to these exactly.
These are the shapes Claude Code builds against. Change them only with a version bump and a note here.

All contracts are Pydantic models in code. JSON Schemas sent to OpenAI are generated from the models plus `field_rules.yaml`, never written by hand.

Conventions:
- Values in examples are illustrative, not confirmed BioA data.
- Field keys are snake_case and map to DFD column names in `field_rules.yaml`.
- Timestamps are ISO 8601 UTC.
- IDs are strings with a prefix: `run_`, `doc`, `rec_`, `iss_`, `chg_`, `blk_`, `llm_`, `exp_`.

---

## 1. Chunk (what the model sees and cites)

```json
{
  "chunk_id": "doc02-p04-c007",
  "document_id": "doc02",
  "page": 4,
  "section": "6.2 Reagents",
  "sheet": null,
  "row_range": null,
  "kind": "table_rows",
  "is_scanned": false,
  "text": "...",
  "image_ref": null
}
```

- PDF: `page` set. Word: `page` null, `section` holds the heading path. Excel: `sheet` and `row_range` set (e.g. `doc03-sReagents-r12-20`).
- `kind`: `paragraph`, `table_rows`, `sheet_rows`, `page_image`.
- `page_image` (a scanned PDF page): `is_scanned` true, `text` null, `image_ref` points to the PNG in the run store. Sent to the LLM as an image labeled with its chunk ID. Citations to it are `not_checkable`.
- In prompts each text chunk appears as `[chunk_id] text`; each `page_image` chunk as `[chunk_id] (scanned page image)` followed by the image. The model cites chunk IDs only.
- Chunk IDs never change within a run. Code resolves them to document, section and page for display.

## 2. Extraction output (LLM, one call per run)

Values are copied exactly as written in the documents. The LLM does no formatting, conversion,
inference or lookup matching. Transformation (code) does that.

```json
{
  "records": [
    {
      "record_ref": "R1",
      "found_in": ["doc02-p04-c007", "doc03-p01-c002"],
      "record_summary": "Purchased antibody from the Section 6.2 reagent table",
      "record_warning": null,
      "fields": {
        "expected_amount": {
          "status": "found", "value": "1",
          "evidence": [ { "chunk_id": "doc02-p04-c007", "quote": "Anti-drug antibody, 1 mL vial, Vendor A, Cat. R0137S or R0137L" } ],
          "alternatives": [], "allows_equivalent": false, "warning": null
        },
        "catalog_no": {
          "status": "found", "value": ["R0137S", "R0137L"],
          "evidence": [ { "chunk_id": "doc02-p04-c007", "quote": "Anti-drug antibody, 1 mL vial, Vendor A, Cat. R0137S or R0137L" } ],
          "alternatives": [], "allows_equivalent": false, "warning": null
        },
        "manufacturer": {
          "status": "found", "value": "Vendor A",
          "evidence": [
            { "chunk_id": "doc02-p04-c007", "quote": "Anti-drug antibody, 1 mL vial, Vendor A, Cat. R0137S or R0137L" },
            { "chunk_id": "doc03-p01-c002", "quote": "Coating antibody (Vendor A or equivalent)" }
          ],
          "alternatives": [], "allows_equivalent": true, "warning": null
        },
        "storage_condition": {
          "status": "conflicting", "value": null, "evidence": [],
          "alternatives": [
            { "value": "-20 °C", "evidence": [ { "chunk_id": "doc02-p05-c003", "quote": "Store at -20 °C until use." } ] },
            { "value": "2–8 °C", "evidence": [ { "chunk_id": "doc03-p01-c002", "quote": "Keep refrigerated (2–8 °C)." } ] }
          ],
          "allows_equivalent": false,
          "warning": "Method and worksheet give different storage conditions"
        },
        "description": {
          "status": "not_found", "value": null, "evidence": [],
          "alternatives": [], "allows_equivalent": false, "warning": null
        }
      }
    }
  ],
  "excluded_items": [
    { "item": "Plate reader", "reason": "Instrument, not a material", "chunk_ids": ["doc02-p09-c001"] }
  ]
}
```

Record rules:
- `record_ref` is temporary. Code replaces it with a permanent `record_id` (§4a). Nothing downstream uses `record_ref`.
- `found_in` is required with at least one chunk. It is the "Found in" column in the review grid.
- `fields` contains every field with role `extracted` in `field_rules.yaml` (17 today). Fields with other roles are never sent to or returned by the LLM.
- Each serial dilution level is its own record (SOP v1.0 §7.4.3).

Field status rules (checked by code after parsing; violation = retry, then step failure):

| status | value | evidence | alternatives | warning |
|---|---|---|---|---|
| `found` | required, copied exactly | ≥ 1 pair | empty | optional |
| `conflicting` | null | empty | ≥ 2, each with value and ≥ 1 evidence pair | required: the conflict |
| `not_found` | null | empty | empty | optional |

Evidence:
- `evidence` is a list of `{chunk_id, quote}` pairs, one per place the value is found. Each quote is
  the sentence or table row from that chunk, copied exactly (as read, for a `page_image` chunk).
- Citation check (code), per pair: the quote must appear in its chunk (case- and whitespace-insensitive).
  Per field: the value must appear in at least one quote. Failure: yellow `CITATION_NOT_VERIFIED`.
  Pairs on a `page_image` chunk are `not_checkable` (yellow `SCANNED_SOURCE`).

Value rules:
- Every value is a string, copied as written (units, symbols, notation and capitalization kept). `multi_value` fields (Catalog No) are a list of strings.
- No inference: a value not written in the documents is `not_found`.
- If only one vendor is named, it goes in both `manufacturer` and `supplier`.
- "Or equivalent" with one named product: `found` with the named product, `allows_equivalent: true`. Code raises one yellow `OR_EQUIVALENT` issue per record.
- Two named products, or sources that disagree: `conflicting`.

What transformation (code) does with these values:
- List fields: match to the lookup list ignoring case, spaces and "°". Boolean fields accept Y or N. Matched with a change: grey `FORMAT_CORRECTED`. No match: red `NOT_IN_LOOKUP`; the user picks from the list.
- Number fields: read the number from the text ("1e4 cps/uL" becomes 10000). Changed: grey `NUMBER_READ_FROM_TEXT`. Unreadable: red `WRONG_TYPE`.
- Catalog No: list joined with ", ".
- The value as written stays in the `extraction` section and in the audit file.

## 3. Extraction verification output (LLM)

The agent receives records with permanent `record_id`s. It reports only problems; anything not listed is treated as supported.

```json
{
  "field_findings": [
    { "record_id": "rec_0007", "field": "description", "verdict": "unsupported", "sources": ["doc02-p04-c007"], "note": "Cited row does not mention plate coating" }
  ],
  "record_findings": [
    { "record_id": "rec_0012", "verdict": "should_be_split", "note": "Covers three serial dilution levels" }
  ],
  "missed_candidates": [
    { "name_as_written": "...", "sources": ["doc01-p07-c004"], "reason": "Listed in the plan but not extracted" }
  ],
  "excluded_item_challenges": [
    { "item": "...", "reason": "This is a prepared buffer, not equipment" }
  ],
  "unreported_conflicts": [
    { "record_id": "rec_0007", "field": "storage_condition", "sources": ["doc03-p01-c005"], "note": "Worksheet gives a different temperature" }
  ]
}
```

- Field verdicts: `contradicted`, `unsupported`, `present_missed`.
- Record verdicts: `not_a_consumable_type`, `duplicate_within_run`, `should_be_split`.
- The agent never returns corrected values.

Citation check result (code, per field): `verified`, `not_verified`, `not_checkable` (scanned or image-only source).

## 3a. Duplicate judge output (LLM)

Called once per new record with a shortlist of up to 10 similar existing Consumable Types (code builds the shortlist; exact name matches are handled by code as `EXISTS_IN_LABVANTAGE`).

```json
{
  "judgments": [
    { "candidate_id": "ref_0182", "verdict": "different", "reason": "100uM vs 10uM concentration" },
    { "candidate_id": "ref_0045", "verdict": "same", "reason": "Same name apart from spacing and same catalog number" }
  ]
}
```

- Verdicts: `same`, `different`, `unsure`. One judgment per candidate.
- `same` or `unsure` on any candidate: yellow `POSSIBLE_DUPLICATE`, listing those candidates with reasons.

## 4. Stored record (sectioned)

Each layer writes only its own section. Earlier sections are read-only.

```json
{
  "record_id": "rec_0007",
  "found_in": ["doc02-p04-c007", "doc03-p01-c002"],
  "extraction": { "record_ref": "R1", "record_summary": "...", "record_warning": null },
  "verification": { "findings": [], "re_extracted": false },
  "exclusion": null,
  "fields": {
    "storage_condition": {
      "extraction": { "status": "conflicting", "value": null, "evidence": [], "alternatives": ["..."], "allows_equivalent": false, "warning": "..." },
      "verification": { "citation_check": "verified", "verdict": null, "note": null },
      "output": { "value": "-20C", "origin": "user_edited", "changes": [], "selected_alternative": 0 },
      "issue_ids": ["iss_0042"]
    },
    "approval_type": {
      "extraction": null,
      "verification": null,
      "output": { "value": null, "origin": "blank_for_now", "changes": [], "selected_alternative": null },
      "issue_ids": []
    }
  },
  "issue_ids": [],
  "action_needed": "none"
}
```

| Section | Written by |
|---|---|
| `extraction` | Extraction (wrapped by code). Null for non-extracted roles |
| `verification` | Citation check (`citation_check`) and verification agent (`verdict`, `note`) |
| `output` | Transformation, then user changes |
| `issue_ids` | Validation |

- `origin`: `extracted`, `default`, `fixed`, `user_edited`, `blank_for_now`, `system`.
- `changes`: transformation clean-ups applied, e.g. `"trimmed whitespace"`.
- `exclusion`: null, or `{ "by": "...", "at": "...", "reason": "..." }`.
- `action_needed`: `fix`, `check`, `none`, `excluded` (computed from open issues).
- All 22 fields are present in every stored record.

## 4a. Stable IDs

IDs connect user changes, bulk actions, accepted warnings, the audit trail and the UI, so they must survive re-runs.

- `record_id`: assigned by code once, when a record first appears (`rec_0001`, ...), and never reused in the run.
  - Re-extraction sends the affected records with their `record_id`; the response must return the same `record_id` for them. Code replaces only those records' `extraction` sections.
  - Records the re-extraction adds (missed candidates) get new IDs. A record re-extraction drops is kept and flagged for the user, never deleted silently.
  - Re-extraction happens before review starts, so no user change can be lost by it.
- `issue_id`: derived from a key of `code`, `record_id`, `field` and the current output value. Validation re-runs produce the same `issue_id` for the same problem.
  - An accepted warning stays accepted while its key is unchanged. When the value changes, the old issue closes (`resolved`) and any new problem gets a new ID.
  - Issue history (opened, accepted, resolved, by whom) is kept for the audit trail.
- `change_id`, `bulk_id`: created by the UI; the API ignores a change whose `change_id` it already stored (safe to resend).

## 5. Issue

```json
{
  "issue_id": "iss_0042",
  "code": "CONFLICT_UNRESOLVED",
  "severity": "error",
  "record_id": "rec_0007",
  "field": "storage_condition",
  "message": "The documents give different values for Storage Condition. Choose one.",
  "individual_review": false,
  "details": {},
  "status": "open",
  "closed_by": null
}
```

- `severity`: `error` (red, Fix), `warning` (yellow, Check), `info` (grey).
- `status`: `open`, `resolved` (fixed by a change), `accepted` (warnings only).
- Run-level issues: `record_id` and `field` null.
- Codes, severities and messages: `clients/bioa/issue_catalogue.yaml`.
- Red issues block the verified label. They never block export.
- `individual_review` (from the catalogue; true for `CITATION_NOT_VERIFIED` and `UNSUPPORTED_BY_SOURCE`): open ones also block the verified label. They can only be accepted one at a time, after the source was opened (see §6).

## 6. Changes request (UI → API → review service)

```json
{
  "user": "...",
  "timestamp": "2026-10-16T14:05:00Z",
  "changes": [
    { "change_id": "chg_0101", "type": "pick_alternative", "record_id": "rec_0007", "field": "storage_condition", "alternative_index": 0, "bulk_id": "blk_003" },
    { "change_id": "chg_0102", "type": "accept_warning", "issue_id": "iss_0050", "source_viewed": true, "note": null },
    { "change_id": "chg_0103", "type": "exclude_record", "record_id": "rec_0015", "reason": "Equipment, not a consumable" },
    { "change_id": "chg_0104", "type": "set_value", "record_id": "rec_0009", "field": "manufacturer", "value": "...", "reason": null }
  ]
}
```

- Sent to `POST /runs/{run_id}/changes`. Stored as pending until the next re-check or Verify.
- Change types: `set_value` (`reason` required when the field had no open issue), `pick_alternative`, `accept_warning`, `exclude_record` (reason required), `restore_record`, `undo_bulk` (`bulk_id`).
- List fields: `set_value` must be a current lookup value (UI offers a searchable dropdown; validation checks again).
- Bulk changes share a `bulk_id` and are undone together.
- `accept_warning` on an `individual_review` issue: no `bulk_id`, and `source_viewed: true` is required. When the catalogue sets `note_required`, `note` is required too. The API rejects it otherwise. Verify never accepts these issues.

## 7. Processing state (LangGraph) and review database

LangGraph state, during processing only (checkpointed):

| Item | Holds |
|---|---|
| `run_id`, config versions | Captured at start |
| `documents` | Document references and chunk references (never contents or images) |
| `records` | Records as processing builds them, keyed by `record_id` |
| `excluded_items` | From extraction |
| `findings` | Latest extraction-verification findings |
| `reextract_count` | For `MAX_REEXTRACT` |
| `issues` | Issues from the final Validation |

When processing ends, records, excluded items and issues are written to the review database. From then on the review database is the only copy that changes.

Review database (SQLite in the pilot), one set per run:

| Table | Holds |
|---|---|
| `runs` | `run_id`, name, created by/at, config versions used, `retry_of`, status, verified (`is_verified`, by, at) |
| `records` | Stored records (§4), keyed by `record_id` |
| `issues` | Issues (§5) with their history (opened, accepted, resolved; by whom, when) |
| `changes` | Every change (§6), with `status` pending or applied, and `bulk_id` |
| `exports` | `export_id`, number, is_draft, loader file, audit file, at, by |
| `audit_events` | Verification, exports, exclusions, admin actions (feeds the audit file) |

## 8. Audit workbook (with every export)

File: `[run name] – export [n] – audit.xlsx` (draft exports add "– draft").

| Sheet | One row per | Columns |
|---|---|---|
| Summary | Setting (label/value) | Run name, run ID, export number, draft or verified, exported by/at, verified by/at, documents (name + SHA-256), versions (field rules, issue catalogue, lookup lists, reference data, prompts, models), open issue counts |
| Values | Record × field (all 22, excluded records not included) | Record ID, Consumable Type, field (column name), value as written (blank if not found; a conflict lists its alternatives), exported value, origin, source document, location (section / page / sheet+rows), source quote, extraction status, citation check, verification verdict, issue codes, issue outcome |
| Edits | Applied change | Change ID, record ID, Consumable Type, field, type, old value, new value, reason, user, time, bulk ID |
| Excluded | Excluded record | Record ID, name, found in, excluded by, at, reason |
| Run issues | Run-level issue | Code, message |

## 9. Eval case folder

```
evals/cases/<case_id>/
  case.yaml                  # id, description, synthetic|bioa, tags, labeled_by, labeled_on, field_rules_version
  documents/                 # source files
  expected_extraction.json   # expected records and field values
  expected_loader.xlsx       # optional: expected final export rows
  seeded_errors.json         # optional: planted mistakes for verification evals
  notes.md                   # anything tricky
```

- Expected sources use document + page/section, not chunk IDs.
- A field key missing from `expected_extraction.json` = "not labeled", not wrong.
- Template: `evals/cases/_template/`.
- Reports: `evals/reports/<timestamp>_<suite>.json` (all versions, scores by record, field, case and tag) plus a CSV summary.

## 10. LLM trace record (one per LLM call)

```json
{
  "trace_id": "llm_0031", "run_id": "run_0012", "node": "extraction", "attempt": 1,
  "provider": "openai", "model": "TBD", "prompt_template": "extraction", "prompt_version": "0.1",
  "config_versions": { "field_rules": "0.1", "lookup_lists": "v0-seed" },
  "started_at": "2026-10-16T14:02:11Z", "duration_ms": 41250,
  "input_tokens": 0, "output_tokens": 0, "cost_estimate": null,
  "status": "ok", "error_message": null,
  "request_file": "runs/run_0012/llm/llm_0031_request.json",
  "response_file": "runs/run_0012/llm/llm_0031_response.json"
}
```

- `status`: `ok`, `retry`, `error`, `schema_violation`.
- Full prompt and response live only in the files. Retention follows `LLM_TRACE_RETENTION_DAYS` (blank keeps all).

## 11. Log line

```json
{ "timestamp": "2026-10-16T14:02:52Z", "level": "INFO", "event": "node_finished",
  "run_id": "run_0012", "node": "extraction", "attempt": 1, "duration_ms": 41250,
  "details": { "records_found": 18, "excluded_items": 2 } }
```

- Events: `run_started`, `node_started`, `node_finished`, `node_failed`, `retry_scheduled`, `route_decided` (with reason), `llm_call_finished`, `changes_saved`, `run_rechecked`, `run_verified`, `export_created`, `lookup_version_applied`, `reference_data_applied`.
- Only IDs, counts and durations. No document text, no field values.

## 12. Config file formats

| File | Format reference |
|---|---|
| `field_rules.yaml` | Header comments in the file (roles, requirement, `placeholder_value`, `multi_value`, `default`, `extraction_guidance`, `condition_groups`) |
| `issue_catalogue.yaml` | Codes with `severity` and `message` |
| `lookup_lists.xlsx` | One sheet per lookup field (sheet name = DFD column name), column A header `Lookup Value`, text cells. `_Instructions` (visible) and `_metadata` (hidden: `version_id`, `based_on_version`, `exported_at`, `exported_by`). Sheets starting with `_` are reserved and ignored |
| `dfd_template.xlsx` | `Sheet1`, row 1 = the 22 column names in field-rules order, nothing else |
| `reference_data_mapping.yaml` | Column mapping and duplicate-check settings |
| `prompts/*.md` | First line: `prompt`, `version`, `status`; placeholders in `{braces}` |
| `env.example` | Deployment settings; secrets only in the environment |

## 13. API endpoints

Request and response bodies use the models above. The OpenAPI schema generated by FastAPI is the contract for the front end.

| Method | Path | Does |
|---|---|---|
| GET | /health | Liveness |
| GET | /runs | List runs: name, status, record count, open issue counts, verified |
| POST | /runs | Upload files (multipart) + run name; start the graph in the background; return `run_id` |
| GET | /runs/{run_id} | Status, current step, verified label, exports, run issues |
| PATCH | /runs/{run_id} | Rename the run |
| GET | /runs/{run_id}/records | Flattened review view: one row per record, cells with value, display value, origin, color, messages, sources, alternatives. For `blank_for_now` fields the value is empty and the display value is the placeholder ("TEST VALUE") |
| GET | /runs/{run_id}/fields | Every field of the run's config in loader order: key, column, role, requirement, type, max length, list or boolean, multi-value, and allowed values (lookup values from the run's own lookup list version; Y/N for booleans; none otherwise). For the review dropdowns |
| GET | /runs/{run_id}/records/{record_id} | One record with all sections, issues and resolved sources |
| GET | /runs/{run_id}/chunks/{chunk_id} | Source text for "Show source" (with document, section, page) |
| GET | /runs/{run_id}/chunks/{chunk_id}/image | The scanned page of a `page_image` chunk as `image/png`; a text chunk is 404 `PAGE_IMAGE_NOT_FOUND` |
| GET | /runs/{run_id}/bulk-preview?mode=&issue_id=&field=&alternative_index= | Records a bulk action would touch (included records only): `change_all` (`issue_id`: same field, issue code and current value), `fill_missing` (`field`: no value, not a conflict), `accept_type` (`issue_id`: same warning code, any field; not individual-review), `resolve_conflicts` (`issue_id` + `alternative_index`: same field, same set of alternatives in any order). Returns the selection, `count` and `matches` (record_id, name, issue_id, current value, and for conflicts the chosen value's `alternative_index` in that record) |
| POST | /runs/{run_id}/changes | Store changes as pending (§6); no re-check yet |
| POST | /runs/{run_id}/recheck | Apply pending changes and run the Validation service; return updated counts |
| POST | /runs/{run_id}/verify | Re-check, then set the verified label; or return the blocking issues |
| POST | /runs/{run_id}/retry | Failed runs only: start a new run from the same uploaded files, with `retry_of` set; the failed run is unchanged |
| POST | /runs/{run_id}/exports | Re-check if needed, then write loader + audit file; return export info (file names `loader_file_name`, `audit_file_name`; never storage paths) |
| GET | /runs/{run_id}/exports | List exports |
| GET | /runs/{run_id}/exports/{export_id}/loader | Download the loader |
| GET | /runs/{run_id}/exports/{export_id}/audit | Download the audit workbook |
| GET | /admin/lookup-lists/current | Download the current workbook |
| POST | /admin/lookup-lists | Upload; return check report and diff; create a pending version |
| POST | /admin/lookup-lists/{version_id}/apply | Make a pending version current, or restore an older one |
| GET | /admin/lookup-lists/versions | Version history (each version shows its uploaded `file_name`, never its storage path) |
| GET | /admin/lookup-lists/versions/{version_id}/download | Download any version |
| POST | /admin/reference-data | Upload existing Consumable Types; return check report; create a pending version |
| POST | /admin/reference-data/{version_id}/apply | Make a version current |
| GET | /admin/reference-data/versions | Version history |

Auth: placeholder sign-in (a configured user) with roles `user` and `admin`, behind one dependency so real sign-in can replace it. Admin endpoints require `admin`.

Errors: every error response has the same shape, with a plain-language message that says what to do next.

```json
{ "error": { "code": "RUN_NOT_IN_REVIEW", "message": "This run is still processing. Wait until it reaches review.", "details": {} } }
```

- 400 invalid request, 403 wrong role, 404 not found, 409 conflict (wrong run status, stale lookup upload, rejected bulk accept of an individual-review warning), 413 upload too large, 422 failed validation (Pydantic), 500 unexpected.
- At startup (config and `REVIEW_DB` set), a run left in a processing status is set to `failed` with the run issue `PROCESSING_INTERRUPTED`, so it can be retried.
- Changes are safe to resend: a repeated `change_id` is ignored (§4a). `POST /runs` and exports are not deduplicated in the pilot.
- Request and response models are Pydantic; the OpenAPI schema is generated from them. It is reviewed and locked before front-end work starts.

Config versions: a run uses the config versions captured when it started (field rules, issue catalogue, lookup lists, reference data, prompts). Admin updates apply to new runs only.
