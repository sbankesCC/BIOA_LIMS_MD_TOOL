# Evals

Evaluation foundation. No real BioAgilytix test data yet.

- `cases/_template/` shows the case folder format. Copy it to add a case.
- Real BioA cases stay in this folder only inside the BioA environment. The repo's automated tests use synthetic cases.
- Run: `uv run python -m app.evals run --suite cases`.
- Reports go to `reports/` as JSON (all versions + scores) and a short CSV summary.
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
- Description is excluded from automatic scoring (free text; reviewed by a person).
