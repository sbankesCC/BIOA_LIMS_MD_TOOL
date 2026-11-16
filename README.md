# BioAgilytix LabVantage Consumable Type Extractor

The pilot reads BioA documents, extracts Consumable Type master data, guides a user through review,
and fills the DFD loader. Pipeline: Ingest → Extraction ⇄ Verification → Normalization → Matching →
Naming → Assembly → Validation → Review → Export (`docs/ARCHITECTURE.md`). The redesign after build
v0.13.1 is in progress: see `PLAN.md`.

| Path | What it is |
|---|---|
| `PLAN.md` | The redesign plan: milestones, decisions, open questions, progress log (start here) |
| `docs/REDESIGN_BUILD_PROMPT.md` | The redesign prompt `PLAN.md` was built from |
| `docs/BUILD_HISTORY_v0.13.1.md` | The completed v0.13.1 build plan (history) |
| `BUILD_PROMPT.md` | The original v0.13.1 build prompt (history) |
| `CLAUDE.md` | Always-loaded working rules, code style and project essentials |
| `.claude/settings.json` | Command permissions matching CLAUDE.md section 1 |
| `docs/ARCHITECTURE.md` | Glossary and the defined architecture and design |
| `docs/CONTRACTS.md` | Every JSON contract, file format and API endpoint |
| `docs/UI_SPEC.md` | Screens and review behaviors |
| `docs/ui_mockups/` | UI mockups as static HTML and PNG (reference only; `UI_SPEC.md` wins) |
| `clients/bioa/source/BAL_Consumable_Type_Definitions.xlsx` | BioA's Data info and List Values sheets (example records removed); differences are listed in the config consistency test |
| `clients/bioa/business_rules.md` | The only source of field and business rules: the 22 loader fields, context attributes, rule lines by step, translation and derivation tables, open questions |
| `clients/bioa/extraction_rules.md` | Extraction guidance: general rules, candidate criteria and each extracted field's `[Extraction]` lines |
| `clients/bioa/export_template.md` | The loader layout: sheet settings and the columns in export order, with type and display format |
| `clients/bioa/issue_catalogue.yaml` | Issue codes, severities, messages (wording is a draft) |
| `clients/bioa/lookup_lists.xlsx` | Lookup lists copied from the List Values sheet |
| `clients/bioa/reference_data_mapping.yaml` | Column mapping for existing Consumable Types uploads |
| `clients/bioa/prompts/` | Extraction, extraction verification, matching, naming (with BioA's naming rules), plausibility and duplicate judge prompts (drafts for review) |
| `evals/` | Eval case template and README (no real data yet) |
| `env.example` | Deployment settings |

Source of truth for fields and rules: `clients/bioa/business_rules.md`; for allowed values: the lookup lists.


Confidential: `clients/bioa/` and any BioA cases in `evals/cases/` are BioAgilytix information.
They are excluded from the scrubbed Clarkston copy.
