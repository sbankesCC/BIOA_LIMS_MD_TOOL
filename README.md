# BioAgilytix LabVantage Consumable Type Extractor: build package v0.13.1

The defined architecture, design and configuration for the pilot. Copy the contents of this folder to the repo root.

| Path | What it is |
|---|---|
| `BUILD_PROMPT.md` | Spec-style prompt for Claude Code (start here) |
| `CLAUDE.md` | Always-loaded working rules, code style and project essentials |
| `.claude/settings.json` | Command permissions matching CLAUDE.md section 1 |
| `docs/ARCHITECTURE.md` | Glossary and the defined architecture and design |
| `docs/CONTRACTS.md` | Every JSON contract, file format and API endpoint |
| `docs/UI_SPEC.md` | Screens and review behaviors |
| `docs/ui_mockups/` | UI mockups as static HTML and PNG (reference only; `UI_SPEC.md` wins) |
| `docs/diagrams/` | System diagram and LangGraph flow as PNG and SVG (rendered from the Mermaid in `ARCHITECTURE.md`) |
| `docs/design_figures.pdf` | All diagrams and mockup screens in one PDF, for sharing |
| `clients/bioa/source/BAL_Consumable_Type_Definitions.xlsx` | BioA's Data info and List Values sheets: the source of truth (example records removed) |
| `clients/bioa/field_rules.yaml` | The 22 fields from the Data info sheet, extraction guidance, and the amount/containers conditions |
| `clients/bioa/issue_catalogue.yaml` | Issue codes, severities, messages (wording is a draft) |
| `clients/bioa/lookup_lists.xlsx` | Lookup lists copied from the List Values sheet |
| `clients/bioa/dfd_template.xlsx` | The DFD template: the 22 Data info columns, in order |
| `clients/bioa/reference_data_mapping.yaml` | Column mapping for existing Consumable Types uploads |
| `clients/bioa/prompts/` | Extraction, extraction verification and duplicate judge prompts (drafts for review) |
| `evals/` | Eval case template and README (no real data yet) |
| `env.example` | Deployment settings |

Source of truth for fields and values: `BAL Consumable Type Import Example.xlsx` (Data info + List Values).


Confidential: `clients/bioa/` and any BioA cases in `evals/cases/` are BioAgilytix information.
They are excluded from the scrubbed Clarkston copy.
