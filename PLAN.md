# Redesign plan: Consumable Type Extractor pipeline (after v0.13.1)

The approved milestones and open questions for the redesign. The finished v0.13.1 plan is archived in `docs/BUILD_HISTORY_v0.13.1.md`.

## Context

v0.13.1 is complete: Ingest → Extraction ⇄ Verification → Transformation → Validation → Review → Export. This redesign does five things:

- It splits Transformation into Normalization (code), Matching (model), Naming (model) and Assembly (code).
- It adds a plausibility review to Validation.
- It changes the extraction and verification contracts: adds `context` and `unclear`, adds `incomplete` and `section`, and drops `allows_equivalent`.
- It replaces `clients/bioa/field_rules.yaml` with `clients/bioa/business_rules.md` as the only source of field and business rules.
- It changes the loader's field list: three fields are removed and three blank expiry fields are added, so it stays at 22 columns.

The design comes from `docs/REDESIGN_BUILD_PROMPT.md`, with the user's changes below. Build history is in `docs/BUILD_HISTORY_v0.13.1.md`. Models only suggest or judge. Only code and people write loader values.

### User decisions in planning (override the prompt)

1. **Three fields are removed, three are added, and the removed ones are not referenced anywhere.**
   - **Removed (confirmed by Brad):** Container Type Size, Container Type Unit and Consumable Params.
     - Delete the "Removed fields" section of `business_rules.md`.
     - Reword the change log entries so that these three are not named.
     - Bump the version to 1.2.
     - From then on they are named only in the archived history (`docs/BUILD_HISTORY_v0.13.1.md`, git history).
   - **Added (BioA's updated field list):** Expiry Based On, Expiry Period and Expiry Period Units.
     - Role `blank_for_now`; exported blank until BioA defines the rules.
     - Their sections, EX-01 to EX-03 and BR-7 stay in `business_rules.md` as written.
2. **Loader has 22 columns:** the original 22, minus the three removed fields, plus the three expiry fields at the end. This is the order of `business_rules.md`.
   - M2 rewrites the `dfd_template.xlsx` header row to match and keeps the styling: it deletes three columns and appends the three expiry headers.
   - You have not given me BioA's updated template, so the three expiry header names stay provisional, as the prompt says. They are listed in Open questions.
3. **Seed the empty lookup lists.**
   - Approval Type gets `MixConsumableCritical`, `MixConsumableNonCritical`, `RecConsumableCritical` and `ReagentVersionApproval`. ReagentVersionApproval is excluded from every step but must exist for the exclusion row.
   - Worksheet Template gets the two names from WT-01 and WT-02.
   - These values are taken from `business_rules.md`. They go into a new seed version, `v0-seed-4`.
   - The consistency test gets an allowed difference that cites AT-01 and WT-01 to WT-03.
4. **Package files are copied into `clients/bioa/` in M1.**
   - The files are `business_rules.md` plus six prompts. Three prompts replace existing ones, and three are new.
   - Each prompt's first line is converted to the header the loader expects: `<!-- prompt: x | version: y | status: z -->`.
   - `claude_code_package/`, the zip and the root `REDESIGN_BUILD_PROMPT.md` stay untracked. The user deletes them. The prompt is committed as `docs/REDESIGN_BUILD_PROMPT.md` so the plan's pointer works.
5. **The Matching rules placeholder is `{matching_rules}`**, not `{field_rules}` as in prompt §7.1, so no `field_rules` name remains. `matching.md` is version 0.2.
6. **Rendered diagrams are deleted, not regenerated:** `docs/diagrams/*` and `docs/design_figures.pdf`. No `npx`.

### Field set after the redesign (22 loader columns + 2 context attributes)

| Role | Fields |
|---|---|
| generated (1) | consumable_type (record name, sent to judge) |
| extracted (12) | description, storage_condition, expected_amount, expected_amount_unit, expected_no_of_containers, container_tracking_method, manage_container_inventory_flag, container_type, manufacturer, supplier, catalog_no, target_concentration |
| derived (4) | consumable_class, critical, approval_type, worksheet_template |
| system (2) | version, status |
| blank_for_now (3) | expiry_based_on, expiry_period, expiry_period_units (exported blank, not validated; EX-01 to EX-03, BR-7) |
| context (not exported) | source_heading (drives critical), serial_dilution (drives approval_type) |

---

## Milestones

Every milestone does the following:

- It starts in a fresh session.
- It ends with `uv run pytest`, `uv run ruff check . && uv run ruff format --check .` and `uv run pyright` all clean. Milestone 9 also runs the front-end checks.
- It ends with a commit, a progress log entry and a stop for review.
- It uses only the fake LLM client.

### M1. Specs (no code)

**Moves and copies**
- `git mv PLAN.md docs/BUILD_HISTORY_v0.13.1.md`, with a first line saying it is the completed build this redesign changes: history, not instructions.
- Write the new `PLAN.md` (this file).
- Copy `business_rules.md` and the three new prompts (matching, naming, plausibility) into `clients/bioa/`, with converted headers (user decision 4). The three replacement prompts (extraction, extraction verification, duplicate judge) wait for M2: their new placeholders stop the current loader from starting.
- Make the `business_rules.md` edits in user decision 1 and show the diff.
- Add `docs/REDESIGN_BUILD_PROMPT.md`.

**Docs to update**

| File | Changes |
|---|---|
| `docs/ARCHITECTURE.md` | Glossary, the §3.1/§3.2 Mermaid (new nodes), §4 components (4.7 becomes Normalization, Matching, Naming and Assembly; 4.8 Validation adds plausibility; 4.9 re-check runs Assembly then Validation), §5 routing (re-extract triggers 3.3, linear chain after verification), §7 data rules (models suggest only; suggestions never applied), §8 config table (`business_rules.md` replaces `field_rules.yaml`), §6 config versions (`business_rules`) |
| `docs/CONTRACTS.md` | Every row of prompt §5. Also adds the stored-field `normalization` section (see Decisions), the `suggestion` object, value origins `derived` and `from_suggestion`, the `use_suggestion` change, audit sheets, `models.matching/naming/plausibility`, and §12 config formats (the `business_rules.md` grammar). Removes the "or equivalent" text and `allows_equivalent` |
| `docs/UI_SPEC.md` | Removes "Accept the named product" and TEST VALUE (Approval Type and Worksheet Template are now derived). Adds "Use suggestion" on NOT_IN_LOOKUP and NAME_NOT_SET, choices on REVIEWER_CHOICE_NEEDED, and labels for the new codes. Context attributes are not displayed |
| `CLAUDE.md` §5 | Pipeline paragraph; model-call list (extraction, verification, matching, naming, plausibility, duplicate judge); `business_rules.md` as the source of truth (replaces the "Import Example.xlsx is the only source of truth" gotcha and the TEST VALUE gotcha); field counts |
| `README.md` | Same pipeline and config file names |

**Rendered diagrams**
- `docs/diagrams/*.{png,svg}` and `docs/design_figures.pdf` no longer matched the Mermaid. Deleted (user decision 6); the Mermaid in `ARCHITECTURE.md` is the only diagram source. Not regenerated.
- The UI mockups stay. `UI_SPEC.md` says the spec wins where a mockup differs.

**Verify:** `uv run pytest` passes except the `CONTRACTS.md` example tests in `test_contracts.py`, which fail until M3 builds the contracts the doc now describes. `rg -n "allows_equivalent|OR_EQUIVALENT|field_rules" docs CLAUDE.md README.md` finds only the history file and the brief (`docs/REDESIGN_BUILD_PROMPT.md`, which names the removed items on purpose).

### M2. Business rules file (§7.1, §7.2)

**New: `backend/app/config/business_rules.py`**
- Contents:
  - Pydantic models `BusinessRules`, `FieldDefinition`, `RuleLine`, `RuleTable` and `RuleStatus`.
  - The parser `parse_business_rules(text) -> BusinessRules`, with `load_business_rules(path)`.
  - Small parsing helpers: Markdown table to rows, rule line regex, status as the first word.
- `FieldDefinition` keeps the methods callers use today: `extracted_fields()`, `columns()`, `record_name_field()`, `duplicate_judge_fields()`. It adds `context_fields()`, `derived_fields()`, `rules_for(step, field=None, active_only=True)` and `table(field_or_section, heading)`.

**New: `backend/app/config/business_rules_checks.py`**
- One validator function per rule in §7.1, each returning plain-language problems. `bundle.py` raises `ConfigError` if any are found.
- Moves `find_template_problems`, `find_lookup_problems` and `find_issue_code_problems` from field-rules-based to business-rules-based.
- The startup check requires `business_rules.md` and accepts no fallback.

**Switch all readers to the new module**
- Change `config/bundle.py` (`ConfigBundle.business_rules`, `ConfigVersions.business_rules`) and every reader listed by the backend map.
- This mostly means renaming `bundle.field_rules` to `bundle.business_rules`. The readers are the contracts, `llm_schema`, `status_rules`, `prompt_builder`, the agents, `graph/`, `transform/`, `validation/`, `review/`, `export/`, `runs/`, `admin/`, `evals/` (`case.yaml` `business_rules_version`) and the test helpers.
- Behavior is unchanged here: the old transform keeps working, reading the new model, until M4.

**Prompt builder (`llm/prompt_builder.py`)**
- Adds the placeholders `{general_rules}`, `{candidate_rules}`, `{field_section}`, `{context_section}`, `{matching_rules}`, `{naming_rules}` and `{checks}`, filled from active rule lines (ID + text, without the status and source).
- Replaces `prompts/extraction.md`, `extraction_verification.md` and `duplicate_judge.md` with the package versions (headers converted), and updates `EXPECTED_PLACEHOLDERS` in `config/prompts.py` for all six prompts.

**Config files**
- `lookup_lists.xlsx`:
  - The Container Tracking Method sheet becomes `i` and `t`.
  - The Container Type Unit and Consumable Params sheets are deleted.
  - Approval Type and Worksheet Template are seeded (user decision 3).
  - `_metadata` becomes `v0-seed-4`.
- `dfd_template.xlsx`: delete the three removed columns and append the three expiry headers (22 columns, `business_rules.md` order).
- `pyproject.toml`: register the `rule` marker now. It is used from M4 on.

**Delete** (see the deletion list below):
- `field_rules.yaml`, `config/field_rules.py`, and the field-rules sections of `test_config_loaders` and `test_broken_config`
- `test_container_tracking_default_is_applied_literally`
- the removed-field references in fixtures and fake replies

**Tests**
- `test_business_rules_parser.py`: happy path on the real file; `Open` rules are inactive; the status note is ignored.
- `test_business_rules_checks.py`: one test per validator rule, on edited copies made with the `config_copy` fixture.
- `test_config_consistency.py`: new allowed differences, each citing its rule ID (TM-04, AT-01, WT-01..03, CC-01, CO-06, D-38).
- `test_no_client_literals.py`: gathers the lookup values, columns and every table cell value from `business_rules.md`.
- `test_prompt_builder.py`: each placeholder; Open lines absent.

**Verify:** `rg field_rules` finds only the history files. The app refuses to start with a missing or broken `business_rules.md`.

### M3. Contracts and schemas (§5)

**Contracts**
- `contracts/extraction.py`:
  - Status gets `unclear`; `allows_equivalent` is removed.
  - The record gets `context: dict[key, ExtractedField]`, single value only.
- `contracts/verification.py`: `section: Literal["fields","context"]` on field findings and unreported conflicts; verdict gets `incomplete`.
- New `contracts/matching.py`, `naming.py` and `plausibility.py`: the request item and response models from the prompts.
- `contracts/record.py`:
  - Records get `context` (extraction, citation, verification; no output).
  - Each field gets a `normalization` section and `suggestion: Suggestion | None`, where `Suggestion` holds value, source `matching|naming`, reason and rule_id.
  - Origins get `derived` and `from_suggestion`.
- `contracts/issue.py`: `details` may carry `suggestion` and `choices`.
- `contracts/changes.py`: `UseSuggestionChange`.
- `contracts/run.py`: models for matching, naming and plausibility; `ConfigVersions.business_rules`.

**Schemas and status rules**
- `llm_schema.py`:
  - The extraction schema gets `context` (generated from `context_fields()`).
  - New `build_matching_schema`, `build_naming_schema` and `build_plausibility_schema`. All are generated from Pydantic, not hand-written.
- `status_rules.py`: the `unclear` row (value null, warning required, alternatives empty, evidence optional), applied to context attributes the same way.

**Tests**
- Every CONTRACTS example parses.
- One test per new status rule, including context.
- Schemas are strict.

### M4. Normalization and Assembly (steps 4 and 7)

**Replace `backend/app/transform/` with two packages**

`backend/app/normalization/`:
- Reused from transform: `cleaning.py` (from transform), `lookup_matching.py` (tiers, now with excluded values removed) and `numbers.py`.
- New modules:
  - `characters.py` (4.2)
  - `translation.py` (4.3: phrase and range rows, "Reviewer chooses")
  - `concentration.py` (4.6)
  - `notes.py` (the existing `CODE: {json}` note format)
  - `normalize.py`: `normalize_record` / `normalize_field`, in the 4.1–4.6 order, per alternative for a conflicting field
  - `matching_items.py` (4.7)

`backend/app/assembly/`:
- `conflicts.py` (7.1)
- `loader_values.py` (7.2)
- `derivations.py`: one small named function each, `derive_critical`, `derive_consumable_class`, `derive_approval_type` and `derive_worksheet_template`, each reading its table
- `defaults.py` (7.4)
- `assemble.py` (7.5, 7.6; skips origin `user_edited`)

**Rules for both packages**
- Normalization writes only `field.normalization`. Assembly writes only `field.output`.
- No BioA values in code: every phrase, heading, vendor name and unit pattern comes from the tables.

**Tests**
- One test per substep and per table row type: phrase, range, reviewer chooses, character, concentration pattern, and each derivation row.
- `test_assembly_never_overwrites_person_value`
- `test_derived_fields_recomputed_on_recheck`
- Each test is marked `@pytest.mark.rule("SC-T07")` and so on.

**Delete:** `transform/` and its five test files.

### M5. Validation (step 8, except 8.6; §6)

**Issue catalogue**
- Edit `issue_catalogue.yaml` for every row of §6 and bump it to 0.8 (0.7 added `VALUE_INCOMPLETE` in the M1–M3 review fixes).
  - "field" level goes in `record_issues`; "run" goes in `run_issues`.
  - Remove `OR_EQUIVALENT`; `CONFLICT_UNRESOLVED` stays an error.
- Show the diff.

**Validation changes**
- Remove `find_or_equivalent_issue` and its call, and add the codes to `validation/codes.py`.
- `findings_to_issues.py`:
  - context findings are raised on the field named by `Drives`;
  - `incomplete` gives `VALUE_INCOMPLETE` (done in the M1–M3 review fixes);
  - `unclear` gives `VALUE_UNCLEAR`;
  - normalization notes give `REVIEWER_CHOICE_NEEDED` (with choices), `NOT_A_CONCENTRATION` and `DERIVED_VALUE_MISSING`;
  - assembly notes give `CONFLICT_CLOSED`.
- `NOT_IN_LOOKUP` carries the suggestion.
- New `validation/names.py`: `NAME_NOT_SET` with the suggestion. In-run duplicates stay as built.
- `duplicates.py`:
  - the shortlist adds existing types with the same catalog number;
  - while the name is not set, the check uses the suggested name, and the name as written is passed to the judge.
- New `validation/derived_check.py` (8.5): `DERIVED_VALUE_MISMATCH`.

**Tests:** one per issue code; a context finding is raised on its driven field; the catalog-number shortlist.

### M6. Model steps and graph

**Agents**
- Change `agents/extraction.py` and `agents/extraction_verification.py`: the new placeholders, context, and the `unclear`/`incomplete` handling.
- New `agents/matching.py`:
  - de-duplicates the items;
  - builds a difflib shortlist with the same `SequenceMatcher` and `normalize_for_match` as `build_shortlist`, of size `MATCHING_SHORTLIST_SIZE`;
  - makes one call;
  - rejects off-shortlist choices.
- New `agents/naming.py`: makes one call, then code checks each name (translation, max length, disallowed characters, unique in the run), and keeps the reason for any dropped suggestion.
- New `agents/plausibility.py`: no call when there are no active `[Plausibility]` lines; drops unknown check IDs. It is called from the validation service.

**Caches and settings**
- New review DB cache tables `matching_cache`, `naming_cache` and `plausibility_cache`, keyed as in the prompt. This sets `SCHEMA_VERSION = 3`; older files are refused.
- Call limits and the `_SKIPPED` run issues use the `JudgeRunner` pattern from `validation/judge_cache.py`.
- Settings in `settings.py` and `env.example`: `MATCHING_MODEL`, `NAMING_MODEL`, `PLAUSIBILITY_MODEL`, `MAX_MATCHING_CALLS`, `MAX_NAMING_CALLS`, `MAX_PLAUSIBILITY_CALLS` and `MATCHING_SHORTLIST_SIZE`. Each is blank with a comment.
- `openai_client.MODEL_SETTINGS` and `graph/context.LLM_NODES` get the new nodes. `capture_models` covers them.

**Graph**
- `graph/nodes.py` and `graph/routing.py`: ingest → extraction ⇄ extraction_verification → normalization → matching → naming → assembly → validation → finish.
- Routing stays in `routing.py`.
- `graph/reextraction.py` gets the 3.3 triggers: `incomplete`, context section, and `unclear` alone does not trigger.
- The step limit is raised for the extra nodes.

**Tests**
- The happy path through every node.
- The re-extract loop.
- Each `_SKIPPED` case: blank model, limit reached, call failed after the retry.
- Shortlist rejection.
- A cache hit and a cache miss.
- The state holds no document text.
- Fake replies are named `matching.1.json` and so on.

### M7. Review and export

**Review (`review/`)**
- `apply_changes.py`: `use_suggestion` sets origin `from_suggestion`.
- `service.recheck_run` runs `assemble_records` on the current values and then `validate_run`, never the model steps (the plausibility and judge caches still apply).
- A pick of an alternative goes through `normalize_field` (it used to use `transform_value`).

**Export (`export/`)**
- `loader.py` takes its columns from `business_rules.columns()`, in file order, and writes the extracted, generated and derived fields.
- `audit_workbook.py` / `audit_rows.py`:
  - the Values sheet adds "How set", "Suggestion" and "Suggestion reason";
  - new sheets "Context" and "Suggestions used".

**Tests:** a suggestion is accepted and audited; re-check re-derives after Manufacturer changes; an export round trip with 22 columns and the three expiry columns blank.

### M8. API — stop for OpenAPI review

- `/fields` returns roles, with context attributes hidden.
- The review view returns `suggestion`, and issue details return choices.
- The changes endpoint accepts `use_suggestion`.
- The run returns the new models and versions.
- Lookup value endpoints omit "all steps" excluded values.
- Regenerate with `uv run python -m app.api`, then **stop for your review**, then re-lock `backend/openapi.json`.

### M9. Front end

- Run `npm run generate:api`.
- Grid columns come from the API (already the case).
- `lib/issueActions.ts`:
  - "Use suggestion" on NOT_IN_LOOKUP and NAME_NOT_SET, showing the reason;
  - the choices shown on REVIEWER_CHOICE_NEEDED;
  - labels for every new code;
  - remove `OR_EQUIVALENT` and the TEST VALUE display.
- **Verify:** `npm ci && npm run typecheck && npm run build`, vitest, and a manual run with the fake provider.

### M10. Evals and cleanup

**Eval case `synthetic_001`**
- Update `expected_extraction.json`, `fake_llm/*` (context, no `allows_equivalent`, plus the matching and naming replies) and `case.yaml` (`business_rules_version`).
- Add seeded errors: an `incomplete` value, a wrong `source_heading` and a wrongly `unclear` value.
- Add labelled Matching and Naming cases, with scoring in `evals/scoring.yaml` and `app/evals/scoring.py`.

**Traceability and cleanup**
- `test_rule_traceability.py`: every active code-step rule ID in `business_rules.md` appears in a `rule` marker.
- Final `rg` sweep (Done criteria). The history file and the brief (`docs/REDESIGN_BUILD_PROMPT.md`) are left out: they name the removed items on purpose.

**End-to-end check:** one fake-provider run goes from upload to export with:
- a Matching suggestion used;
- a Naming suggestion used;
- a derived Approval Type;
- a re-check that re-derives after Manufacturer is changed.

---

## Deletion list (§9 — I ask once, at the start of M2, then `git rm` in the milestone that replaces each)

| Item | Removed in |
|---|---|
| `clients/bioa/field_rules.yaml`, `backend/app/config/field_rules.py`, field-rules tests | M2 |
| Container Type Size, Container Type Unit and Consumable Params: fields, columns, lookup sheets, fixtures, fake replies, docs mentions | M1 (docs), M2 (rest) |
| `test_container_tracking_default_is_applied_literally` | M2 |
| `backend/app/transform/` and `test_transform`, `test_transform_notes`, `test_cleaning`, `test_lookup_matching`, `test_numbers` (the last three move to normalization tests, not lost) | M4 |
| `OR_EQUIVALENT` (catalogue entry, `codes.py`, `find_or_equivalent_issue`, `test_or_equivalent_is_raised_once_per_record`, the review-service tests, the `issueActions.ts` entry) | M5, M9 |
| `allows_equivalent` (contract, schema, `evals/seeding.py`, fake replies, openapi, `schema.ts`, docs) | M3, M8–M10 |
| `placeholder_value` / TEST VALUE | M2 (config), M9 (UI) |
| `docs/diagrams/*.png/.svg`, `docs/design_figures.pdf` | M1 (done) |

## Decisions carried forward (from `docs/BUILD_HISTORY_v0.13.1.md`)

**Still hold:**

- **Settings and what blank means.** The app starts with every setting blank. A blank limit means no limit, and that now includes `MAX_MATCHING_CALLS`, `MAX_NAMING_CALLS` and `MAX_PLAUSIBILITY_CALLS`. A setting with no usable blank meaning is named when it is used. `MAX_REEXTRACT=1`.
- **Missing settings in the API** return 503 SETTING_MISSING.
- **Record name flag:** exactly one field, and it is sent to the judge. It is now the `Record name` attribute.
- **Judge fields from config:** now the `Sent to duplicate judge` attribute. The judge values and cache key use only these.
- **Citation check treats `|` as whitespace.**
- **Lookup matching never guesses:** a normalized match must be unique, and booleans accept only Y or N.
- **Defaults apply to not-found fields only, never to conflicting ones, and are applied literally.**
- **Transform notes format `CODE: {json}`** carries over as the normalization notes.
- **Findings apply to extracted values only;** none are raised after a person sets the value.
- **Excluded records** are not validated and are left out of the name and reference checks.
- **Duplicate shortlist:** difflib ratio ≥ 0.6, up to `shortlist_size`, plus the catalog-number matches.
- **Judge limit** applies per validation pass, and cached results do not count against it.
- **Judge that cannot answer** gives "unsure", and the result is cached.
- **Failures:**
  - a failed verification or re-extraction gives EXTRACTION_FAILED;
  - a cut-off response is retried once and then gives DOCUMENT_SET_TOO_LARGE;
  - the new model steps fail soft with `_SKIPPED` instead.
- **Models captured per run in `RunInfo.models`.**
- **Review DB schema version is refused when old.** It goes from 2 to 3.
- **Lookup values in review** are checked against the run's captured lookup version.
- **Undo bulk, Verify and draft export** behave as built.
- **Export file names, audit Values sheet layout and the "Value as written" column.**
- **Eval harness:** it drives the graph directly, with fake replies per case, seeded errors from `EvalLLMClient` and the value comparison rules.
- **OpenAPI lock test.** Generated API types are committed.
- **Background processing:** one worker thread. Run IDs are `run_NNNN`.
- **Roles,** the stored user and auth behave as built.
- **"Mandatory" Expected Amount Unit and Expected No of Containers are read as conditional.**
- **"N/A" stays in the Manufacturer and Supplier lists.**
- **DFD template version** is the short SHA-256 of the file.
- **The no-client-literals test** compares whole string constants and skips one-character values.
- **Config versions per run:** lookup lists and reference data are reloaded by their captured version. The other config files (now including `business_rules.md`) are recorded, not reloaded. This is unchanged from v0.13.1; see Open questions.

**No longer apply:**

- **"Container Tracking Method stays literal; every record gets TOO_LONG":** the default is now `i`, and the list holds codes (TM-03, TM-04).
- **TEST VALUE for Approval Type, Consumable Params and Worksheet Template:** two are derived and one is removed.
- **OR_EQUIVALENT and "Accept the named product":** removed. "or equivalent" stays in the copied value instead.
- **The `field_rules.yaml` format, its version 0.3 and `is_record_name` / `sent_to_duplicate_judge` as YAML keys:** they are replaced by `business_rules.md` attributes.
- **"A picked alternative goes through `transform_value`":** it now goes through `normalize_field`.

## Decisions made in this plan (not covered by the prompt or docs)

1. **New `normalization` section on each stored field** (normalized value, normalized alternatives, notes, matching-eligible flag). Normalization owns it. Re-check needs it so Assembly can run without re-normalizing.
2. **Value origins** add only `derived` and `from_suggestion`, as the contract says. The audit "How set" column shows "normalized" when the origin is `extracted` and normalization changed the value.
3. **A blank `MATCHING_SHORTLIST_SIZE` means the whole list** (no limit), in line with "blank means no limit".
4. **A blank model setting skips the step for both providers.** Tests and eval cases set the model settings.
5. **Values excluded from "all steps"** are treated as not on the list for normalization, Matching, derivation-output checks and the dropdowns offered by the API. Values excluded from "Matching" only are kept out of shortlists.
6. **Plausibility runs inside the validation service,** so re-check also reaches it. It makes no call while no check is active.
7. **The in-run duplicate check uses set names only.** The suggested name is used only for the reference-data check (8.4).
8. **The issue catalogue level maps to its sections:** field → `record_issues`, run → `run_issues`.
9. **Run statuses:** `transforming` is replaced by `normalizing`, `matching`, `naming` and `assembling` (`ARCHITECTURE.md` §6). The Processing screen gets one step per status (`UI_SPEC.md` §4.2).
10. **Stored-field shapes in `CONTRACTS.md` §4:** `normalization` holds `value`, `alternatives`, `notes`, `matching_value` and `choices`. Assembly notes stay in `output.changes`.
11. **Plausibility findings** are raised on the first field the finding lists, with the check ID in `details.check_id`.
12. **Eval case files** `expected_matching.json` and `expected_naming.json` (optional) hold the labelled Matching and Naming cases (`CONTRACTS.md` §9).

## Open questions

- **BR-1 to BR-9 and FL-1** are not resolved. `Assumption` rules are built as written, and `Open` rules stay inactive. They include SC-05, CO-04, EU-04, CR-03, TC-05, NM-09, EX-01 to EX-03 and PL-01 to PL-04.
- **Expiry column names are provisional** until BioA's updated DFD template arrives. If they differ, change the `Loader column` cells in `business_rules.md` and the template header.
- **Storage Condition "Ambient":** the list has its own `Ambient` value, but SC-T05 translates "ambient" to Room Temperature first (4.3 runs before 4.4), so `Ambient` is never chosen. This belongs with BR-3.
- **Greek letters outside the character table:** the business rules text says they "raise an issue for the reviewer". Today only fields with `Disallowed characters` (Consumable Type) raise INVALID_CHARACTERS. Should every text field check for them?
- **The seeded Approval Type and Worksheet Template values are not from BioA's LabVantage export.** They should be confirmed with BR-6.
- **Config versions per run:** `business_rules.md` and the prompts are recorded but read from the current files, as in v0.13.1. Keep this, or snapshot them per run?
- **Critical with no `source_heading`:** the brief raises `DERIVED_VALUE_MISSING`, but CR-02 says N for every item not in the Critical Reagents table. Which applies when no heading was found? Until decided, M4 follows the brief (raise the issue, leave Critical blank).
- **Carried over:** the record side of the duplicate comparison (expose the judge flag on `/fields`?).

## Progress log

### M1: Specs (done; awaiting review)
- Moved the v0.13.1 plan to `docs/BUILD_HISTORY_v0.13.1.md` (history note on line 1); new `PLAN.md`; `docs/REDESIGN_BUILD_PROMPT.md`.
- Added `clients/bioa/business_rules.md` v1.2: v1.1 from the package, plus the "Removed fields" section removed, TC-05 and the change log reworded so the removed fields are not named, and a 1.2 change log row.
- Added `clients/bioa/prompts/matching.md`, `naming.md`, `plausibility.md` with the loader's header format. The three replacement prompts move to M2 (see M1 above).
- Updated `docs/ARCHITECTURE.md` (glossary, both Mermaid diagrams, §4.5–§4.10, routing, run statuses, data rules, configuration, evaluation), `docs/CONTRACTS.md` (every row of prompt §5, new §3b–§3d, the `business_rules.md` grammar in §12, API notes), `docs/UI_SPEC.md` (processing steps, grid, new issue actions, "Or equivalent" removed), `CLAUDE.md` §5 and `README.md`.
- Tests: 544 passed, 1 skipped, 6 failed. All six are in `test_contracts.py`, which parses the `CONTRACTS.md` examples; they fail on the new contract fields and are fixed in M3.
- Decisions the docs did not cover: Decisions 9–12 above.
- Review answers: the placeholder was renamed to `{matching_rules}` (`matching.md` 0.2), and the rendered diagrams were deleted (user decisions 5 and 6).

### M2: Business rules file (done; awaiting review)
- New `config/business_rules.py` (models, Markdown reader, builders) and `config/business_rules_checks.py` (raw, model and cross-file checks; `parse_business_rules` / `load_business_rules` live here so the checks run before models are built). `bundle.py` loads `business_rules.md` with no fallback.
- Every `field_rules` reader renamed to `business_rules` (`ConfigVersions.business_rules`, `business_rules_version` on run fields and eval cases, audit row "Business rules version").
- Prompts: the package's `extraction.md` 0.5, `extraction_verification.md` 0.5 and `duplicate_judge.md` 0.4 with converted headers; `EXPECTED_PLACEHOLDERS` covers all six. The prompt builder fills `{general_rules}`, `{candidate_rules}`, `{field_section}`, `{context_section}`, `{matching_rules}`, `{naming_rules}`, `{checks}`; the extraction and verification agents fill the first four now.
- Config files: `lookup_lists.xlsx` `v0-seed-4` (tracking codes `i`/`t`, Approval Type and Worksheet Template seeded, two sheets deleted, `_Instructions` updated); `dfd_template.xlsx` at 22 columns; `rule` marker in `pyproject.toml`; `env.example` comment.
- Deleted: `field_rules.yaml`, `config/field_rules.py`, the field-rules cases of `test_broken_config.py`, `test_container_tracking_default_is_applied_literally`, and its twin `test_default_longer_than_its_limit_is_too_long_on_every_record` (same retired behavior). Fake replies drop the removed fields and `critical` / `consumable_class`; `expected_extraction.json` drops its 5 `consumable_class` / `critical` labels (user approved), so `test_evals` totals are 32/33.
- Tests: 580 passed, 1 skipped, 6 failed. The 6 are the `test_contracts.py` example tests from M1, fixed in M3. ruff and pyright clean. `backend/openapi.json` regenerated (renames and the new role/origin values only); `schema.ts` waits for M9.
- Decisions the docs did not cover:
  - Roles bridge until M4: `extracted_fields()` and `is_extracted` cover `extracted` and `generated`; derived fields get origin `derived` (added to `Origin` now, ahead of M3) and stay blank, unvalidated and not editable until Assembly.
  - Context attributes are kept in `BusinessRules.context`, not in `fields`, so every loop over loader fields stays 22 columns.
  - `FieldDefinition` keeps the old reader names (`lookup_sheet`, `separator`, `is_record_name`); `multi_value` is a property (separator set).
  - Grammar words that equal a column name (Status, Version) and keyword columns (Entry, Match type, Status, ...) are declared in `business_rules.py` and left out of the no-client-literals check; it now also checks every other data-table cell.
  - `blank_for_now` cells show an empty display value (TEST VALUE removed); `is_placeholder` stays in the API until M8.
  - The "relaxed config" test helper is gone: no lookup list is impossible to meet any more, so tests that need a red record plant an overlong value (`make_red_record`).
  - Rule notes cannot contain nested parentheses (the last parentheses of a rule line hold the status); the real file has none.
  - `evals/cases/_template/` still labels `consumable_class` / `critical`; left for M10.

### M3: Contracts and schemas (done; awaiting review)
- Contracts:
  - Extraction: `unclear` status, `context` on the record, `allows_equivalent` removed.
  - Verification: `incomplete` verdict, and `section` (`fields` / `context`, default `fields`) on field findings and unreported conflicts.
  - Record: `context` (`StoredContextAttribute`: extraction and verification only), `normalization` (`FieldNormalization`) and `suggestion` (`Suggestion`) on each field, and origin `from_suggestion`. `find_record_field_problems` also checks the context attributes.
  - Changes: `UseSuggestionChange`.
  - Trace: the `matching`, `naming` and `plausibility` nodes.
  - New `contracts/matching.py`, `naming.py` and `plausibility.py` hold the request items and responses.
  - `issue.py` and `run.py`: docstrings only. `details` and `models` are already open mappings.
- `llm_schema.py`:
  - The extraction schema gets a closed `context` object with one single-string property per context attribute.
  - The verification keys are the extracted fields plus the context attributes.
  - New `build_matching_schema`, `build_naming_schema` and `build_plausibility_schema`, all generated from the models.
- `status_rules.py`:
  - New `unclear` row.
  - New `context_missing` and `context_not_attribute` checks.
  - Context attributes follow the same rows as fields, with single values only.
- Tests:
  - Every CONTRACTS example parses, including the §3b response. This fixes the 6 failures left from M1.
  - Each new status rule has a test, including the context cases.
  - All six schemas are checked for strict mode.
  - New `test_graph_records.py`.
  - `use_suggestion` review tests: applied, rejected without a suggestion, undone with its bulk action.
  - Result: 618 passed, 1 skipped. ruff and pyright are clean.
  - `backend/openapi.json` was regenerated with the new shapes. `schema.ts` waits for M9.
- Decisions the docs did not cover:
  - **OR_EQUIVALENT moved earlier (from M5):** `find_or_equivalent_issue`, its call and `test_or_equivalent_is_raised_once_per_record` were deleted now, because they read `allows_equivalent`. The code constant and the catalogue entry stay until M5. The review-service tests that used OR_EQUIVALENT as an ordinary warning now use SCANNED_SOURCE, so no coverage was lost.
  - **`use_suggestion` built now (from M7):** check, apply, undo and audit description. Adding it to the change union needs a handler in each place, and the full behavior is small. It is also a bulk change type. `from_suggestion` is a person-set origin (`USER_ORIGINS`), so transformation and findings leave it alone.
  - **Context in stored records (from M6):** `graph/records.py` already wraps the context attributes and writes `section: context` findings to them, so the stored record matches §4. Citation checks on context and the re-extraction triggers are still M6.
  - **Fake replies (from M10):** the `synthetic_001` fake replies and the graph test fixture now carry `context`, with every attribute `not_found` (the synthetic documents give none). `allows_equivalent` is removed from them and from `evals/seeding.py`. Without this, the status rules reject them.
  - **No `run.py` status change:** `RunStatus` keeps `transforming` until the graph changes in M6 (Decision 9).
  - **Unrestricted IDs in the new schemas:** they do not narrow `rule_id` or `check_id` to the active rule IDs. Code checks those (M6), as CONTRACTS describes.

### M1–M3 review fixes (done; awaiting review)
- Review of M1–M3 by three reviewers (one per milestone). Fixed here: the committed package zip, the `incomplete` crash and the `business_rules.md` parser gaps. The M1 doc items and the M3 low items are not fixed yet.
- `claude_code_package.zip` untracked (`git rm --cached`) and added to `.gitignore` with `claude_code_package/`. It is still in the history of `c6966f2`; removing it from history is the user's call before pushing.
- `incomplete` verdict: `FIELD_VERDICT_CODES` maps it to the new `VALUE_INCOMPLETE` (error), so Validation no longer raises `KeyError`. `issue_catalogue.yaml` 0.7 adds the code (message wording is a draft). The verdict test now runs over every `FieldVerdict`, so a new verdict without a code fails.
- `business_rules.md` checks, each now a plain startup error:
  - attribute rows must have two cells, and an attribute may be listed once;
  - a requirement group is allowed only on `conditional`;
  - `*`/`+` bullets and indented lines in parsed sections are rejected (they were silently dropped);
  - a condition group needs at least two entries in Fields, and group names are unique;
  - business `[Extraction]` lines must sit under `### Candidate criteria`, and `[Matching]` lines must be in a field section (otherwise no prompt reads them);
  - any Pydantic error left when building the models becomes a ConfigError naming the file.
- Table cells: `\|` is a literal bar inside a cell.
- Tests: 10 new (all fail on the old parser) and 1 widened. Result: 629 passed, 1 skipped; ruff clean. pyright not run: Node.js is not on PATH on this machine.

- Docs (M1 review items):
  - `UI_SPEC.md`: no Accept on "Value incomplete" (an error); the Verify dialog lists every individual-review warning; the Processing steps are one per status (the two verification steps merged into "Checking against the documents"; "Preparing your preview" removed); the "2–8 °C" example now shows 4C.
  - `CONTRACTS.md`: the full individual-review list (with `UNREPORTED_CONFLICT`, already individual-review in the catalogue); Assembly never overwrites `fixed` either; the shortlist is up to 10 similar names plus the catalog-number matches.
  - `ARCHITECTURE.md` §4.7 heading no longer says "Transformation".
  - Prompt developer notes (HTML comments, never sent to the model) now match CONTRACTS: `matching.md` 0.3, `naming.md` 0.2, `plausibility.md` 0.2.
  - The M1 and M10 `rg` checks leave out the brief, which names the removed items on purpose.
  - New open question: Critical with no `source_heading`.
  - Not changed: the BioA examples in the three prompts (no rule lines; user's call), the processing mockup and `frontend/src/lib/processingSteps.ts` (M9).
- Tests (M3 review items): from_suggestion is kept by transformation; citation, verdict and unreported-conflict findings are dropped for every person-set origin; `use_suggestion` on a derived field is rejected; undoing a used suggestion keeps a later value. The first three fail if `from_suggestion` leaves `USER_ORIGINS`.
