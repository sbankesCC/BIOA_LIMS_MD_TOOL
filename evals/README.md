# Evals

Evaluation foundation. No real BioAgilytix test data yet.

- `cases/_template/` shows the case folder format. Copy it to add a case.
- Real BioA cases stay in this folder only inside the BioA environment. The repo's automated tests use synthetic cases.
- Run from the repo root: `uv run python -m app.evals run --suite cases`. `--suite` names a folder
  under `evals/` (or an absolute path); folders starting with `_` (the template) are skipped.
  Needs `CLIENT_CONFIG_DIR`. Options: `--runs N` (default 3), `--real-llm`, `--reports-dir`, `--work-dir`.
- Reports go to `reports/` as JSON (all versions + scores) and a short CSV summary. They are
  generated output and not committed.
- LLM: a case with a `fake_llm/` folder (fixture files `<node>.<attempt>.json`) runs on those fake
  replies, with no network and fixed limits (no retries, one re-extraction). Other cases, or every
  case with `--real-llm`, use `LLM_PROVIDER` and the limits from the settings.
- Runs use a temporary work folder (run store, review DB, checkpoints), never the app's data
  folders. `--work-dir` keeps the runs' files (LLM traces included) in a new folder instead.
- Runs use the seed lookup lists from the client config and no reference data.
- Seeded errors are planted into the first extraction response of each run; a re-extraction
  may correct them. Only planted errors are scored.
- If a case's `field_rules_version` differs from the current field rules, the loader flags it in the report: the expected output may need relabeling.

Scores:
- Records: recall (expected consumables found) and precision (no invented records).
- Fields: correct value per field, reported separately for each field.
- Status: not_found and conflicting reported correctly.
- Citations: source points to the expected document and page.
- Extraction verification: seeded errors caught, correct values wrongly flagged.

Rules:
- Records are matched to expected records by normalized name; unmatched ones are listed for manual review.
- Each case runs 3 times by default; reports show the spread.
- A field key missing from expected_extraction.json is "not labeled", not wrong.
- Description is excluded from automatic scoring (free text; reviewed by a person). Unscored
  fields are listed in `scoring.yaml`.
- Values are compared with whitespace collapsed, either as written or as exported (so a label in
  either form counts). Lists compare as sets; a conflict compares its alternatives.
- The record's name (under the record name field's key) is also that field's label.
- Citations: each expected source (document, plus page or section) must be in the record's
  "found in"; a section label matches a Word heading path containing it or an Excel sheet name.
