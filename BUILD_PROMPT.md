# Build prompt (Claude Code)

How to use:
1. Put this package at the repo root.
2. Start Claude Code, run `/init` and keep only useful suggestions, then switch to plan mode and paste the prompt below.
3. Claude Code reads the docs, interviews you about blockers, and writes its plan to `PLAN.md`. You approve the plan.
4. It builds milestone by milestone, showing test evidence. Start each milestone in a fresh session.

---

## Prompt

We are building the pilot of the LabVantage Consumable Type Extractor for BioAgilytix (BioA):
the back end and the front end.

The architecture and design are defined in `docs/` and `clients/bioa/`. Build to them.
You plan the build: milestones, order, file structure, tests and how each milestone is verified.

### Read first (planning session)
Read these fully while planning. In later sessions, read only what the current task needs.
The PDF and PNG figures are for people; the text and HTML versions hold the same content.
1. `CLAUDE.md`: rules and required code style.
2. `docs/ARCHITECTURE.md`: what the system does and why. Start with the glossary (§1a) and what the source documents look like (§1b).
3. `docs/CONTRACTS.md`: every data shape, file format and API endpoint. Build to these exactly.
4. `docs/UI_SPEC.md` and `docs/ui_mockups/*.html`: screens and review behaviors.
5. `clients/bioa/`: config files the code loads (do not edit them): `field_rules.yaml`, `issue_catalogue.yaml`, `lookup_lists.xlsx`, `dfd_template.xlsx`, `reference_data_mapping.yaml`, `prompts/`. `source/BAL_Consumable_Type_Definitions.xlsx` is BioA's original field definitions and lists (the source of truth the config is built from).
6. `evals/README.md` and `evals/cases/_template/`.

### Why this exists
BioA lab staff create LabVantage Consumable Types by hand from methods, study plans and worksheets.
This tool reads those documents, proposes the records with sources, lets a user resolve problems, and fills out
the Excel loader (DFD template), plus an audit file. It is a regulated lab: QC approves every Consumable Type in
LabVantage, so accuracy and traceability (every value shows its source) matter more than speed.

### What to build: back end
- FastAPI API with every endpoint in CONTRACTS.md §13.
- LangGraph flow (ARCHITECTURE.md §3.2, §4.3–4.8, §5): Ingest → Extraction → Extraction verification → Transformation → Validation, with the re-extract loop, ending with the run ready for review. SQLite checkpointer.
- Ingestion for `.docx`, `.pdf` (text and scanned) and `.xlsx`, with chunking and loader-file detection. Scanned pages become `page_image` chunks (no OCR).
- Citation check, transformation, and a Validation service (field checks, condition groups, existing-type duplicate check with cached judge results) as plain code.
- Review service and review database (SQLite): changes, re-check, Verify, audit history (ARCHITECTURE.md §4.9, CONTRACTS.md §6–7).
- LLM client interface that sends text and page images in one request, with two implementations, chosen by `LLM_PROVIDER`:
  - `fake`: returns fixtures. All automated tests use it.
  - `openai`: real calls through the OpenAI SDK, using `OPENAI_API_KEY` and the model settings in `env.example`. Leave the values blank; I fill them in. Every call is traced (CONTRACTS.md §10).
- Export service: DFD loader + audit workbook (ARCHITECTURE.md §4.10, CONTRACTS.md §8).
- Admin services: lookup lists and reference data (ARCHITECTURE.md §4.11–4.12).
- Placeholder sign-in: a configured user with roles `user` and `admin` (CONTRACTS.md §13).
- Structured logging (CONTRACTS.md §11).
- Eval harness foundation (ARCHITECTURE.md §9, `evals/README.md`), with no real data.
- Startup validation of every config file, and a config consistency test against `clients/bioa/source/BAL_Consumable_Type_Definitions.xlsx` (ARCHITECTURE.md §9).

### What to build: front end
- React and TypeScript, built with Vite, in `frontend/`. Calls the back end only through its API.
- The screens and behaviors in `UI_SPEC.md`: start a run, processing, review and resolve (grid, resolution panel, bulk actions, exclude, Verify dialog, export), and admin for lookup lists and reference data.
- Look and layout from `docs/ui_mockups/*.html`: Clarkston design tokens (colors, fonts with fallbacks, spacing) as CSS variables, with status always shown as icon plus word.
- API types generated from the back end's OpenAPI schema, not written by hand.

### Not part of this build
- Writing to LabVantage. The tool's job ends at the filled template and audit file.
- Deployment, cloud storage and production job processing. The pilot runs locally.

### Constraints
- Everything in CLAUDE.md section 5.
- JSON Schemas sent to the LLM are generated from Pydantic models and `field_rules.yaml`. The extraction LLM copies values as written; all formatting and lookup matching is code.
- Prompts in `clients/bioa/prompts/` are drafts: fill their {placeholders} as described in their comments. Reasonable changes are allowed: tell me what changed and why, bump the version in the prompt header, and re-run the tests.
- Extraction status rules (CONTRACTS.md §2) are checked in code on every response.
- Fixtures and test documents are synthetic and labeled `synthetic`. No real BioA documents or records in the repo.
- Back-end stack: Python 3.12, FastAPI, Pydantic v2, LangGraph (no LangChain), openpyxl, PyYAML, pytest, `uv`, ruff (docstring and naming rules on), pyright. Propose a PDF library.
- Front-end stack: React, TypeScript, Vite, npm. Propose a component approach that matches the mockups; keep dependencies few.
- Settings come from the environment. `env.example` lists them; blank values are placeholders I fill in. Never invent values for them. The app must start with them blank; a feature that needs a blank setting reports the missing setting when used. If you need a new setting, add it to `env.example` as a blank placeholder and tell me.

### How to work
1. Explore the docs and config.
2. Interview me only about blockers: things that are unclear, missing or contradictory and would stop the build. Don't ask what the docs already answer. Record other uncertainties in `PLAN.md`.
3. Write your plan to `PLAN.md` as milestones: the order you will build in, the files and interfaces, the tests, and how you will verify each milestone. Wait for my approval. Your plan must follow three rules:
   - Contracts, config loaders and deterministic code (ingestion, transformation, validation, export) are built and tested before any LLM integration.
   - Each milestone ends with passing tests and a stop for my review. Start each milestone in a fresh session.
   - The back end comes first. Its OpenAPI schema is reviewed by me and locked before front-end work starts.
4. Build in your planned order.
5. After each coherent piece that passes its tests: show the real output and commit.
6. Tell me about any decision you make that the docs do not cover.
