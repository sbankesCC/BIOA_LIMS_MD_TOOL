# Redesign build prompt (Claude Code)

How to use:

1. Copy this package to the repo root. It adds `REDESIGN_BUILD_PROMPT.md`, `clients/bioa/business_rules.md`, and six files in `clients/bioa/prompts/` (three replace existing prompts, three are new).
2. Start Claude Code in plan mode and paste the prompt below.
3. Claude Code updates `PLAN.md` with the milestones and waits for approval. It then builds one milestone per session.

---

## Prompt

We are changing the pipeline design of the LabVantage Consumable Type Extractor (build v0.13.1). The design below is final. Build to it. Follow `CLAUDE.md` in full; where this prompt and `CLAUDE.md` section 5 or `docs/` disagree, this prompt wins and you update those files (milestone 1).

### Before you plan

1. Read `CLAUDE.md`, `PLAN.md`, `docs/ARCHITECTURE.md`, `docs/CONTRACTS.md`, `docs/UI_SPEC.md`.
2. Read `clients/bioa/business_rules.md` and every file in `clients/bioa/prompts/`.
3. Ask me only about blockers. Add the milestones in section 8 to `PLAN.md` and wait for my approval.

### 1. What changes, in one paragraph

Transformation becomes four steps: Normalization (code), Matching (model), Naming (model), Assembly (code). Validation gains a plausibility review (model). Extraction and verification get contract changes. `clients/bioa/business_rules.md` replaces `clients/bioa/field_rules.yaml` as the only source of field and business rules. The loader's field list changes.

### 2. Design rules (must always hold)

1. A model reports, suggests or judges. It never writes a loader value. Only code and people write values.
2. Each step writes only its own section of the stored record.
3. Only Validation creates issues. Validation never changes a value.
4. Never invent data. A value the documents do not give is `not_found`.
5. BioA rules and values live only in `clients/bioa/`. None in `backend/` or `frontend/`. The no-client-literals test must still pass.
6. Prompt files never contain BioA rules. The prompt builder inserts rule lines from `business_rules.md` by step tag.
7. A rule or table row with status `Open` is inactive: not inserted into prompts, ignored by code.
8. Routing stays in `graph/routing.py`. Every model step is one constrained call: strict structured output, one retry, cached, call-limited. No agent loops, no tools, no new frameworks.
9. A value set by a person is never overwritten.
10. A run uses the config versions captured at its start.
11. Do not build a general rules engine. Each derivation in section 4 is a small named function that reads its table from `business_rules.md`.

### 3. The pipeline

| # | Step | Purpose | Engine | Writes |
|---|---|---|---|---|
| 1 | Ingest | Store the files as citable chunks | Code | Chunks |
| 2 | Extraction | Report candidate Consumable Types and what the documents say, as written | Model | Raw values, context attributes, excluded items |
| 3 | Verification | Check that extraction read the documents faithfully and completely | Code + model | Citation results, findings |
| 4 | Normalization | Resolve every value rules can resolve with certainty | Code | Normalized values, notes |
| 5 | Matching | Suggest a list value for lookup values rules could not resolve | Code + model | Suggestions |
| 6 | Naming | Suggest each record's name in BioA's naming format | Model + code | Suggestions |
| 7 | Assembly | Derive the remaining fields and write the loader values | Code | Loader values |
| 8 | Validation | Decide what needs the reviewer's attention | Code + model | Issues |
| 9 | Review | A person confirms, corrects and accepts | Person | Changes |
| 10 | Export | Write the reviewed state to the DFD loader and audit workbook | Code | Files |

Graph: Ingest → Extraction ⇄ Verification → Normalization → Matching → Naming → Assembly → Validation → finish. Review and Export stay services outside the graph.

### 4. Steps and substeps

**Step 1. Ingest.** No change.

**Step 2. Extraction** (prompt `extraction.md` v0.5)

- 2.1 Identify candidate records and excluded items.
- 2.2 Copy each field's value whole and as written, including words such as "or equivalent".
- 2.3 Capture the context attributes (`source_heading`, `serial_dilution`) once per record, in a `context` section with the same shape as a field.
- 2.4 Set a status per field and context attribute: `found`, `not_found`, `conflicting`, `unclear`.
- Removed: the `allows_equivalent` flag.

**Step 3. Verification** (prompt `extraction_verification.md` v0.5)

- 3.1 Citation check (code), on fields and context attributes.
- 3.2 Verification call. New: field verdict `incomplete`; findings and unreported conflicts carry `section` (`fields` or `context`).
- 3.3 Routing. Re-extract on: field findings (all four verdicts, fields and context), `not_verified` citations, unreported conflicts, `should_be_split`, missed candidates. Status `unclear` alone does not trigger re-extraction.

**Step 4. Normalization** (code). Per field, in this order; for a conflicting field, per alternative:

- 4.1 Clean text (as built).
- 4.2 Translate characters with the character translation table.
- 4.3 Apply the field's translation table. Phrase rows match ignoring case, spaces and the degree sign. Range rows match a stated temperature within Min–Max. A row with "Reviewer chooses" leaves the value blank and notes the choices.
- 4.4 Lookup match in tiers (as built), after removing excluded lookup values.
- 4.5 Read numbers (as built). Never convert units.
- 4.6 Classify Target Concentration with the concentration units table: a number followed by a concentration unit gives the number; anything else is left blank with a note.
- 4.7 Collect unresolved lookup values of fields with `Matching allowed = yes` for step 5.

**Step 5. Matching** (prompt `matching.md` v0.1)

- 5.1 De-duplicate items by (field, normalized value).
- 5.2 Build each shortlist in code: the `MATCHING_SHORTLIST_SIZE` most similar list values (difflib, as in the duplicate shortlist); the whole list if it is that size or smaller; excluded values removed.
- 5.3 Use the cache. Key: field, value, shortlist, business rules version, prompt version, model.
- 5.4 One model call for the uncached items.
- 5.5 Reject any choice not on the item's shortlist.
- 5.6 Store each answer as a suggestion on the field. Do not set the value.

**Step 6. Naming** (prompt `naming.md` v0.1)

- 6.1 One model call for all included records. Cache per record: its values, business rules version, prompt version, model.
- 6.2 Code checks each suggested name: character translation applied, max length, disallowed characters, unique within the run. A failing suggestion is dropped and the reason kept.
- 6.3 Store the suggestion on the record name field. Do not set the value.

**Step 7. Assembly** (code)

- 7.1 Close conflicts whose alternatives are identical after normalization; note it.
- 7.2 Write each extracted field's loader value from its normalized value; join multi-value fields.
- 7.3 Derive, in this order, each from its table in `business_rules.md`:
  - Critical, from `source_heading` and the critical headings table;
  - Consumable Class, from the Manufacturer value, the BAL vendor names and the class table;
  - Approval Type, from the approval type table;
  - Worksheet Template, from the worksheet template table.
- 7.4 Apply defaults to empty fields (as built). Never on conflicting fields.
- 7.5 Leave `system` and `blank_for_now` fields blank.
- 7.6 Record how each value was produced: extracted, normalized, derived, default, from suggestion, set by a person.

**Step 8. Validation** (code + model)

- 8.1 Field checks and condition groups (as built), read from `business_rules.md`.
- 8.2 Turn findings and notes into issues (section 6). A finding on a context attribute is raised on the field named in its `Drives` attribute.
- 8.3 Name checks. Name not set: `NAME_NOT_SET` with the suggestion. In-run duplicates (as built).
- 8.4 Duplicate check against reference data (as built), with two changes: the shortlist also includes existing types with the same catalog number; while the name is not set, use the suggested name and the name as written.
- 8.5 Derived-value check: a person-set derived value that differs from its derivation raises `DERIVED_VALUE_MISMATCH`.
- 8.6 Plausibility review (prompt `plausibility.md` v0.1): only when `business_rules.md` has an active `[Plausibility]` rule; only on values that passed 8.1; findings with an unknown check ID are dropped. Cached per record.
- 8.7 Action needed (as built).

**Step 9. Review**

- New change type `use_suggestion`: sets the field to its suggestion and records "from suggestion".
- Re-check runs Assembly (7.1–7.6 on the current values) and then Validation. Derived fields are recomputed unless a person set them. Re-check never calls extraction, verification, Matching or Naming.

**Step 10. Export**

- Loader columns come from `business_rules.md`, in file order.
- Audit workbook additions in section 5.
- Draft export for unverified runs stays as built.

### 5. Contract changes

Update `docs/CONTRACTS.md` first (milestone 1), then the code.

| Contract | Change |
|---|---|
| Extraction field | Status adds `unclear`. Remove `allows_equivalent` |
| Extraction record | Add `context`: one field-shaped object per context attribute (single value, never a list) |
| Status rules | `unclear`: value null, `warning` required, alternatives empty, evidence optional. Context attributes follow the same table as fields |
| Verification | `field_findings` and `unreported_conflicts` add `section`. Verdict adds `incomplete` |
| Matching | Request items and response `answers` as in `matching.md` |
| Naming | Response `names` as in `naming.md` |
| Plausibility | Response `findings` as in `plausibility.md` |
| Stored record | Add `context` (extraction, citation and verification results; no output). Each field may hold one `suggestion`: value, source (`matching` or `naming`), reason, rule ID. Value origins add `derived` and `from_suggestion` |
| Issue | `details` may carry the suggestion, and the reviewer choices for a "Reviewer chooses" row |
| Changes | Add `use_suggestion` |
| Run | `models` adds `matching`, `naming`, `plausibility`. Config versions: `business_rules` replaces `field_rules` |
| Audit workbook | Values sheet: add "How set", "Suggestion" and "Suggestion reason". New sheet "Context": record, attribute, value as written, source. New sheet "Suggestions used": field, value as written, value chosen |
| Review database | Bump the schema version. Older files are refused, as today |
| OpenAPI | Regenerate; stop for my review; re-lock |

### 6. Issue catalogue changes

Edit `clients/bioa/issue_catalogue.yaml`, bump its version, and show me the diff. Message wording is a draft.

| Code | Level | Severity | Flags | Raised when |
|---|---|---|---|---|
| `VALUE_INCOMPLETE` (new) | field | error | | Verdict `incomplete`, unresolved after re-extraction |
| `VALUE_UNCLEAR` (new) | field | warning | individual_review | Extraction status `unclear`. Shows the extraction `warning` |
| `NAME_NOT_SET` (new) | field | error | | The record name is empty. Carries the Naming suggestion when there is one |
| `REVIEWER_CHOICE_NEEDED` (new) | field | warning | individual_review | A translation row with "Reviewer chooses" matched. Carries the choices |
| `NOT_A_CONCENTRATION` (new) | field | warning | | Step 4.6 left Target Concentration blank |
| `DERIVED_VALUE_MISSING` (new) | field | error | | A derivation could not run because an input is missing (class with no vendor; Critical with no `source_heading`) |
| `DERIVED_VALUE_MISMATCH` (new) | field | warning | individual_review, note_required | Step 8.5 |
| `CONFLICT_CLOSED` (new) | field | info | | Step 7.1 |
| `PLAUSIBILITY_CHECK` (new) | field | warning | individual_review | Step 8.6. Shows the check ID and reason |
| `MATCHING_SKIPPED`, `NAMING_SKIPPED`, `PLAUSIBILITY_SKIPPED` (new) | run | warning | | The step's model setting is blank, its call limit was reached, or its call failed after the retry |
| `NOT_IN_LOOKUP` | field | error | | Unchanged. Now carries the Matching suggestion when there is one |
| `CONFLICT_UNRESOLVED` | field | error | | Confirm it is an error |
| `OR_EQUIVALENT` | | | | **Remove** |

Matching, Naming and the plausibility review never fail a run: on failure they add their `_SKIPPED` issue and the run continues.

### 7. Config changes in `clients/bioa/`

You may edit the files listed here for this change set. Show me each diff.

**7.1 `business_rules.md` replaces `field_rules.yaml`. This is required, not optional.**

- Build a parser and a startup validator for `business_rules.md`.
- Switch every loader, schema builder, prompt builder, check and test that reads `field_rules.yaml` to it.
- Then delete `field_rules.yaml` and its loader. No fallback to the YAML file. No copy of its rules anywhere else.
- The app refuses to start if `business_rules.md` is missing or malformed.

Parser:

- Version: the `Version` row of the first table.
- Field sections: `## Field: <name>`, in file order. Attribute table, `### Rules` lines, and any other `###` table.
- Rule line: `- <ID> [<Step>] <text> (<Status>; <source>)`.
- Status: the first word of a rule's parentheses or of a Status cell. Anything after it is a note.
- Sections under `## General rules` and `## Business rules` are parsed the same way.

Validator (fail startup with a plain message):

- required attribute keys present; role, requirement, type and step tag from the allowed sets;
- rule IDs and table entry IDs unique;
- exactly one record name field, and it is sent to the duplicate judge;
- every lookup list named exists in the lookup value list;
- every translation target, table output and default exists in its lookup list (blank allowed);
- every `Drives` value and every condition group field is a field key;
- loader columns equal the DFD template headers, in order.

Prompt builder: fills each prompt's placeholders with active rule lines, inserted as written with their IDs, without the status and source.

| Placeholder | Filled with |
|---|---|
| `{general_rules}` | `[Extraction]` lines under General rules |
| `{candidate_rules}` | `[Extraction]` lines under Candidate criteria |
| `{field_section}` | For each field with role `extracted` or `generated`: key, column, its `[Extraction]` lines |
| `{context_section}` | For each field with role `context`: key, its `[Extraction]` lines |
| `{field_rules}` (Matching) | `[Matching]` lines of the fields that have items in the call |
| `{naming_rules}` | Every `[Naming]` line |
| `{checks}` | Every `[Plausibility]` line |

The other placeholders (`{chunks}`, `{records}`, `{items}` and so on) are filled as each prompt's developer notes say.

**7.2 Other files**

| File | Change |
|---|---|
| `dfd_template.xlsx` | Header row equals the loader columns in `business_rules.md`, in order. If I have not given you BioA's updated template, ask before editing; the three expiry column names are provisional |
| `lookup_lists.xlsx` | Container Tracking Method list becomes `i` and `t`. Remove the Container Type Unit and Consumable Params sheets if nothing else uses them |
| `issue_catalogue.yaml` | Section 6 |
| `prompts/` | Use the six files in this package. Keep the header format the loader expects |
| `source/BAL_Consumable_Type_Definitions.xlsx` | Do not edit. Update the config consistency test's allowed-differences list, each entry citing its rule ID in `business_rules.md` |

**7.3 Settings** (add to `env.example` as blank placeholders, with a comment each)

`MATCHING_MODEL`, `NAMING_MODEL`, `PLAUSIBILITY_MODEL`, `MAX_MATCHING_CALLS`, `MAX_NAMING_CALLS`, `MAX_PLAUSIBILITY_CALLS`, `MATCHING_SHORTLIST_SIZE`. A blank model setting skips that step with its `_SKIPPED` issue. A blank limit means no limit.

### 8. Milestones

Each ends with passing tests (`pytest`, `ruff`, `pyright`), a commit, and a stop for my review. One milestone per session. All model tests use the fake client.

**M1. Specs.** Update `docs/ARCHITECTURE.md` (flow, components, routing, Mermaid), `docs/CONTRACTS.md`, `docs/UI_SPEC.md`, `CLAUDE.md` section 5 (model-call list, gotchas, field counts) and `README.md` to this design. No code.

**M2. Business rules file.** Section 7.1 and 7.2. Delete `field_rules.yaml`. Tests: parser happy path; one test per validator rule; config consistency test; no-client-literals test.

**M3. Contracts and schemas.** Section 5: Pydantic models, `llm_schema.py`, `status_rules.py`. Tests: CONTRACTS examples parse; one test per new status rule.

**M4. Normalization and Assembly.** Replace `transform/` with `normalization/` and `assembly/`. Steps 4 and 7. Tests: one per substep and per table row type; `test_assembly_never_overwrites_person_value`; `test_derived_fields_recomputed_on_recheck`.

**M5. Validation.** Step 8 except 8.6; section 6. Remove `OR_EQUIVALENT` and `find_or_equivalent_issue`. Tests: one per issue code; context finding raised on its driven field; catalog-number shortlist.

**M6. Model steps and graph.** Updated extraction and verification agents; new matching, naming and plausibility agents; caches; new nodes and edges; re-extraction rules (3.3); fail-soft behavior; models captured per run. Tests: happy path through all nodes; re-extract loop; each `_SKIPPED` case; shortlist rejection; cache hit and miss; state holds no document text.

**M7. Review and export.** `use_suggestion`; re-check runs Assembly then Validation; audit workbook additions; loader columns. Tests: suggestion accepted and audited; re-check re-derives; export round trip.

**M8. API. Stop for OpenAPI review and re-lock.**

**M9. Front end.** Regenerate API types. Grid columns from the API. Suggestion shown with its reason and a "Use suggestion" action on `NOT_IN_LOOKUP` and `NAME_NOT_SET`. Choices shown on `REVIEWER_CHOICE_NEEDED`. Labels for every new code. Remove the "Accept the named product" action. Context attributes are not displayed.

**M10. Evals and cleanup.** Update `evals/cases/synthetic_001/` and its fake replies. Add seeded errors for `incomplete`, a wrong `source_heading` and a wrongly `unclear` value. Add labeled cases for Matching (expected list value or none) and Naming (expected name). Add the rule traceability test: every active rule in `business_rules.md` tagged for a code step is named by at least one test (use a `rule` pytest marker). Finish section 9.

### 9. Files to delete

List the files, ask me once, then remove them with `git rm`. Nothing in the repo may still import or mention them.

- `clients/bioa/field_rules.yaml`
- The `field_rules` config loader module and its tests (replaced in M2)
- `backend/app/transform/` (replaced by `normalization/` and `assembly/`) and its tests
- `OR_EQUIVALENT`: catalogue entry, `find_or_equivalent_issue`, its UI action, its tests and fixtures
- `allows_equivalent` in contracts, schemas, fixtures, fake replies and docs
- Container Type Size, Container Type Unit and Consumable Params: fields, columns, lookup sheets, fixtures, expected outputs
- `test_container_tracking_default_is_applied_literally` (the default is now the code `i`)
- Rendered diagrams and `docs/design_figures.pdf` that no longer match the Mermaid in `ARCHITECTURE.md`, unless you regenerate them. Tell me which
- Any fixture, fake reply or eval expected output that only served a deleted item

### 10. Not in this build

- An admin approval flow for new translation-table entries. The "Suggestions used" audit sheet is enough for now.
- Pre-filling suggestions.
- Inferring a class when no vendor is listed.
- Rules for the three expiry fields (exported blank).
- Active plausibility checks. Build the step; it makes no call until a `[Plausibility]` rule is active.
- A different model for verification.

### 11. Open items

`business_rules.md` lists open questions (BR-1 to BR-9, FL-1) and has rules marked `Open` or `Assumption`. Do not resolve them. Build `Assumption` rules as written; keep `Open` rules inactive. If an open item blocks a milestone, stop and ask.

### 12. Done means

- Every milestone's tests pass, with `ruff` and `pyright` clean.
- `field_rules.yaml` and everything in section 9 is gone, and `rg field_rules` finds nothing outside `PLAN.md` history.
- `docs/` and `CLAUDE.md` describe the pipeline in section 3.
- A fake-provider run goes from upload to export with: a Matching suggestion used, a Naming suggestion used, a derived Approval Type, and a re-check that re-derives after Manufacturer is changed.
- You have told me every decision you made that this prompt and the docs did not cover.
