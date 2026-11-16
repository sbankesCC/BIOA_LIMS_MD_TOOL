# BioA Export Template: Consumable Type loader

| Attribute | Value |
|---|---|
| Version | 1.0 |
| Last updated | 2026-11-16 |

This file is the layout of the DFD loader file the tool exports: the sheet, and every loader column with its order, data type and display format. Export builds the loader from this file alone. What each field means, and how its value is produced, is in `business_rules.md`.

---

## How to read and edit this file

The structure is strict, because code reads it. Code checks the file at startup and refuses to run if it is malformed.

- `## Sheet` holds one table of settings: `Sheet name` (at most 31 characters, none of `[ ] : * ? / \`), `Header bold` (`yes` or `no`) and `Freeze header row` (`yes` or `no`).
- `## Columns` holds one row per loader column, in the order the loader writes them. This file is the only place the column order is set.
  - `Column`: the column header. The set of columns must equal the `Loader column` names of the field sections in `business_rules.md`.
  - `Type`: `text`, `number` or `date`. It must agree with the field's `Type` in `business_rules.md`: `decimal` and `integer` are `number`; `text` and `boolean` are `text`; a `date` column holds a `text` field.
  - `Format`: blank (Excel's default), `<n> decimals` for a number (for example `2 decimals`), or a date pattern made of `YYYY`, `MM` and `DD` for a date (for example `MM/DD/YYYY`). A text column has no format.
- A format only changes how Excel shows a value. The stored value is written unchanged and is never rounded. A value that does not fit its type (a draft export can hold one) is written as text.

---

## Sheet

| Setting | Value |
|---|---|
| Sheet name | Sheet1 |
| Header bold | yes |
| Freeze header row | no |

## Columns

| Column | Type | Format |
|---|---|---|
| Consumable Type | text | |
| Description | text | |
| Version | text | |
| Consumable Class | text | |
| Storage Condition | text | |
| Critical | text | |
| Expected Amount | number | |
| Expected Amount Unit | text | |
| Expected No of Containers | number | |
| Container Tracking Method | text | |
| Manage Container Inventory Flag | text | |
| Container Type | text | |
| Manufacturer | text | |
| Supplier | text | |
| Catalog No | text | |
| Target Concentration | number | |
| Approval Type | text | |
| Worksheet Template | text | |
| Status | text | |
| Expiry Based On | text | |
| Expiry Period | text | |
| Expiry Period Units | text | |

---

## Change log

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-11-16 | Replaces `dfd_template.xlsx`. Same sheet, header style and column order. Formats are blank (Excel's default) until BioA gives them |
