# BioA Business Rules: Consumable Type

| Attribute | Value |
|---|---|
| Version | 1.4 |
| Last updated | 2026-11-16 |

This file is the source of truth for BioAgilytix's Consumable Type rules. Code reads it, together with the **lookup value list** (the allowed LabVantage values for each list field).

---

## How to read and edit this file

The structure is strict, because code reads parts of this file. Code checks the file at startup and refuses to run if it is malformed.

### Field sections

There is one section per loader field, headed `## Field: <Loader column>`. Column order is set by `export_template.md`, not by this file.

A field section holds the field's **structural facts**: its key, loader column, role, requirement, data type, and whether it holds one value or several. Every step reads these to know the field's shape. **Guidance** on what a field means and how to read it lives elsewhere: in `extraction_rules.md` for extraction, and in the rule lines and tables of this file for every later step.

Each section has:

- **An attribute table**, with keys in this order:
  - required keys: Key, Loader column, Role, Requirement, Type;
  - optional keys: Max length, Lookup list, Default, Matching allowed, Sent to duplicate judge, Record name, Multi-value separator, Disallowed characters, Drives (context attributes: the loader field the attribute drives).
- **Rule lines** under `### Rules`, written as:
  `- <Rule ID> [<Step>] <Rule>. (<Status>; <Source>)`
- **Tables** under `### Translation table` or another `###` heading, where the field has one.

### Field roles

| Role | Meaning |
|---|---|
| `extracted` | The model copies the value from the documents as written; code then normalizes it |
| `derived` | Assembly sets it from other values, using the rules in this file. Never sent to the model for extraction |
| `generated` | Extracted as written, then the Naming step suggests the final value |
| `context` | Extracted for use by other rules; never exported or displayed |
| `system` | Assigned by LabVantage. Exported blank |
| `blank_for_now` | Not filled by the tool yet. Exported blank and not validated |

### Steps used in rule tags

| Tag | Meaning |
|---|---|
| `[Extraction]` | Model step. These lines live in `extraction_rules.md`, never in this file |
| `[Normalization]` | Code step |
| `[Matching]` | Model step. The line is inserted into the Matching prompt |
| `[Naming]` | Model step. The line is inserted into the Naming prompt |
| `[Assembly]` | Code step |
| `[Validation]` | Code step |
| `[Plausibility]` | Model check in Validation. The line is inserted into the plausibility prompt |

### Status labels

| Status | Meaning |
|---|---|
| Confirmed | Confirmed by BioA (in writing, in a meeting, or in the SOP) |
| Assumption | Working rule until BioA confirms. Listed in the open questions |
| Design | A Clarkston design choice where BioA's sources say nothing |
| Open | Not yet decided; the tool does not act on it |

### What editing changes

| Part | Effect of an edit |
|---|---|
| Attribute tables and translation tables | **Changes behavior directly.** Code reads them as data |
| Rule lines tagged for model steps | **Changes behavior directly.** They are inserted into the prompts |
| Rule lines tagged for code steps | **Documents the rule.** The code implements it under the same rule ID and a test checks it. Changing the line means the code and its test must change too |

Prompts never copy rules. A prompt builder inserts only the lines tagged for that step, and only for the fields in play.

### How status is applied

- A Status cell or rule status starts with one of the four labels. Anything after the label is a note.
- **Open** rule lines are not inserted into prompts, and Open table rows are ignored by code.
- Confirmed, Assumption and Design rules and rows are all active.

### Data tables

Code reads every table under a `###` heading in a field section or in the business rules section.

In a derivation table, a column named after a loader column reads that field's value, and a column named after a context attribute reads whether it was found (`yes` or `no`). Input cells: `any` matches every value, `(empty)` matches no value, and `in <table>` or `not in <table>` checks the value against the first column of that table in the same section, ignoring case and spaces. Output cells: `(blank)` leaves the field blank, and `(blank, with an issue)` leaves it blank and raises an issue for the reviewer. `(any other heading)` matches every heading the rows above did not. Values that belong to BioA (list values, vendor names, headings) appear only in these tables and in the lookup value list, never in code.

---

## General rules (all fields)

### Rules

- GEN-03 [Normalization] Replace micro and Greek characters in every text field using the character translation table below. Reason: Consumable Type names are the key and are sorted and filtered on. (Confirmed; 11/2, BioA written, SOP 7.1.1.2)
- GEN-04 [Normalization] Trim leading and trailing spaces and collapse repeated spaces. (Design; built)
- GEN-05 [Normalization] Never convert units or magnitudes. Keep the number and unit as stated: 500 uL stays 500 uL. Reason: LabVantage has its own unit conversion rules, and some volumes are very small. (Confirmed; 11/2)
- GEN-06 [Normalization] A list field takes a value only if it matches a lookup list value: exactly, or ignoring case, spaces and the degree sign. Never create a new list value. (Confirmed; charter review, 11/2)
- GEN-07 [Normalization] Never select a lookup value that starts with `DNU_` ("Do Not Use"). (Confirmed; BioA written)
- GEN-08 [Assembly] Compare values from different sources after normalization and translation. If they become the same value, use it and note it. (Confirmed; 11/2)
- GEN-09 [Validation] If values still differ after translation, the field is a conflict: an error, and the reviewer must pick a value. No document type takes priority. (Confirmed; BioA written, 11/2, D-41)

### Character translation table

| Character | Unicode | Replace with | Status |
|---|---|---|---|
| µ | U+00B5 (micro sign) | u | Confirmed |
| μ | U+03BC (Greek small mu) | u | Confirmed |
| α | U+03B1 | alpha | Confirmed |
| β | U+03B2 | beta | Confirmed |
| γ | U+03B3 | gamma | Confirmed |

Other Greek letters, and uppercase Greek letters, are not yet translated. They raise an issue for the reviewer. BioA has no known standard list beyond these (BioA written).

### Excluded lookup values

Values that must not be chosen, even though they are in the lookup value list.

| Lookup list | Value | Match | Excluded from | Status |
|---|---|---|---|---|
| (all lists) | DNU_ | prefix | all steps | Confirmed |
| Consumable Class | Provided by Sponsor | exact | all steps | Confirmed |
| Approval Type | ReagentVersionApproval | exact | all steps | Confirmed |
| Expected Amount Unit | Count | exact | Matching | Assumption (BR-4) |
| Expected Amount Unit | (Containers) | exact | Matching | Assumption (BR-4) |
| Expected Amount Unit | Vial | exact | Matching | Assumption (BR-4) |

---

## Field: Consumable Type

| Attribute | Value |
|---|---|
| Key | consumable_type |
| Loader column | Consumable Type |
| Role | generated |
| Requirement | required |
| Type | text |
| Max length | 40 |
| Disallowed characters | greek_letters; control_characters |
| Record name | yes |
| Sent to duplicate judge | yes |
| Matching allowed | no |

### Rules

- CT-02 [Assembly] The Naming step suggests the name, using the naming rules in the business rules section. (Confirmed; BioA written, 11/2, D-39)
- CT-03 [Assembly] The cell stays empty until the reviewer uses the suggestion or types a name. (Confirmed; D-39)
- CT-04 [Validation] 40 characters or fewer. (Confirmed; SOP 7.1.1.1, Data info)
- CT-05 [Validation] No Greek letters after character translation. (Confirmed; SOP 7.1.1.2)
- CT-06 [Validation] Unique within the run. A name that exactly matches an existing Consumable Type is an error. (Confirmed; Data info, primary key)

---

## Field: Description

| Attribute | Value |
|---|---|
| Key | description |
| Loader column | Description |
| Role | extracted |
| Requirement | optional |
| Type | text |
| Max length | 255 |
| Sent to duplicate judge | yes |
| Matching allowed | no |

### Rules

- DS-02 [Validation] 255 characters or fewer. (Confirmed; SOP 7.2.2.2, Data info)

---

## Field: Version

| Attribute | Value |
|---|---|
| Key | version |
| Loader column | Version |
| Role | system |
| Requirement | optional |
| Type | text |
| Max length | 40 |

### Rules

- VR-01 [Assembly] Export blank. LabVantage assigns Version 1 on load. (Confirmed; 11/2, Data info, D-42)

---

## Field: Consumable Class

| Attribute | Value |
|---|---|
| Key | consumable_class |
| Loader column | Consumable Class |
| Role | derived |
| Requirement | optional |
| Type | text |
| Max length | 80 |
| Lookup list | Consumable Class |
| Sent to duplicate judge | yes |
| Matching allowed | no |

### Rules

- CC-01 [Assembly] Consumable Class is Prepared or Purchased only. (Confirmed; BioA written)
- CC-02 [Assembly] The vendor is BAL → Prepared. (Confirmed; BioA written)
- CC-03 [Assembly] The vendor is any other company → Purchased. Items provided by the sponsor are Purchased. (Confirmed; BioA written)
- CC-04 [Assembly] Never use "Provided by Sponsor"; BioA does not use that class. (Confirmed; BioA written)
- CC-05 [Assembly] "Vendor" means the Manufacturer value as extracted. (Assumption; BR-2)
- CC-06 [Assembly] No vendor listed: leave blank and raise an issue; the reviewer sets the class. (Assumption; BR-2)
- CC-07 [Assembly] A catalog number is not needed to be Purchased; not every purchased item has one. (Confirmed; BioA written)

### Class table

Used by CC-02, CC-03 and CC-06. The Manufacturer column reads the Manufacturer value (CC-05). Rows are checked top to bottom; the first match applies.

| Manufacturer | Consumable Class | Status |
|---|---|---|
| (empty) | (blank, with an issue) | Assumption (BR-2) |
| in BAL vendor names | Prepared | Confirmed |
| not in BAL vendor names | Purchased | Confirmed |

### BAL vendor names

The vendor counts as BAL if it matches one of these (ignoring case and spaces).

| Name as written | Status |
|---|---|
| BAL | Assumption |
| BioAgilytix | Assumption |
| BioAgilytix Labs | Assumption |

---

## Field: Storage Condition

| Attribute | Value |
|---|---|
| Key | storage_condition |
| Loader column | Storage Condition |
| Role | extracted |
| Requirement | optional |
| Type | text |
| Max length | 40 |
| Lookup list | Storage Condition |
| Matching allowed | yes |

### Rules

- SC-02 [Normalization] Translate the phrase using the translation table below. (Confirmed; 11/2, BioA written)
- SC-03 [Normalization] "Frozen" or "freezer" with no temperature: leave blank and raise a warning. The reviewer chooses -20C or -80C. Never sent to Matching. (Confirmed; 11/2, BioA written)
- SC-04 [Normalization] A phrase not in the table and not a list value goes to Matching. (Confirmed; D-21)
- SC-05 [Matching] [to write and confirm with BioA] (Open; M-3)

### Translation table

Phrases match ignoring case, spaces and the degree sign. A range matches any stated temperature from Min to Max °C, inclusive.

A row with no Lookup value and a "Reviewer chooses" list is left blank with a warning; the reviewer picks one of the listed values.

| Entry | Match type | Document wording | Min °C | Max °C | Lookup value | Reviewer chooses | Status |
|---|---|---|---|---|---|---|---|
| SC-T01 | phrase | 2–8 °C; 2-8 °C; 2 to 8 °C; 4 °C | | | 4C | | Confirmed |
| SC-T02 | phrase | refrigerated; refrigerator; refrigerate | | | 4C | | Confirmed |
| SC-T03 | phrase | ≤ -70 °C; -70 °C; -80 °C; ultra-low; ultra low | | | -80C | | Confirmed |
| SC-T04 | phrase | 15–25 °C; 15-25 °C; room temperature | | | Room Temperature | | Confirmed |
| SC-T05 | phrase | ambient | | | Room Temperature | | Assumption (BR-3) |
| SC-T06 | phrase | -20 °C | | | -20C | | Confirmed |
| SC-T07 | range | | -30 | -10 | -20C | | Assumption (±10 °C; BR-3) |
| SC-T08 | phrase | cryo; cryogenic; cryogenically stored; liquid nitrogen; LN2; -196 °C | | | Cryo | | Confirmed terms; confirm Cryo is active (BR-3) |
| SC-T09 | phrase | frozen; freezer; store frozen | | | | -20C; -80C | Confirmed |

---

## Field: Critical

| Attribute | Value |
|---|---|
| Key | critical |
| Loader column | Critical |
| Role | derived |
| Requirement | optional |
| Type | text |
| Max length | 1 |
| Lookup list | Critical |
| Matching allowed | no |

### Rules

- CR-01 [Assembly] Y if the item's `source_heading` is the Critical Reagents table. (Confirmed; 11/2, BioA written)
- CR-02 [Assembly] N for every item not in that table, e.g. under "Other Consumables" or "Non-Critical". (Confirmed; 11/2)
- CR-03 [Validation] A document with no Critical Reagents table raises a warning on its records. BioA says this is unusual. (Open)
- CR-04 [Assembly] Written as Y or N. (Assumption; BR-8: Data info says Y/N, the DFD example shows Yes/No)

### Critical headings

Used by CR-01 and CR-02. A `source_heading` is the Critical Reagents table when it contains the first phrase and none of the second (ignoring case). Rows are checked top to bottom; the last row gives every other heading.

| Heading contains | Unless it contains | Critical | Status |
|---|---|---|---|
| critical reagent | non-critical; non critical; noncritical | Y | Confirmed |
| (any other heading) | | N | Confirmed |

---

## Field: Expected Amount

| Attribute | Value |
|---|---|
| Key | expected_amount |
| Loader column | Expected Amount |
| Role | extracted |
| Requirement | conditional (amount_or_containers) |
| Type | decimal |
| Matching allowed | no |

### Rules

- EA-04 [Assembly] Never default. Reason: defaults can cause unit errors when lots are created. (Confirmed; BioA written, 11/2)
- EA-05 [Validation] The expected amount may differ from the container size (e.g., a 0.65 mL tube holding 0.45 mL). No flag. (Confirmed; 11/2)

---

## Field: Expected Amount Unit

| Attribute | Value |
|---|---|
| Key | expected_amount_unit |
| Loader column | Expected Amount Unit |
| Role | extracted |
| Requirement | conditional (amount_or_containers) |
| Type | text |
| Max length | 40 |
| Lookup list | Expected Amount Unit |
| Matching allowed | yes |

### Rules

- EU-02 [Normalization] µL → uL and µg → ug through the character translation table; case variants match the list (ml → mL). (Confirmed; BioA written, 11/2)
- EU-03 [Normalization] Never convert to another unit. (Confirmed; 11/2)
- EU-04 [Matching] Never choose Count, (Containers) or Vial until BioA defines when they are used. (Open; BR-4)

---

## Field: Expected No of Containers

| Attribute | Value |
|---|---|
| Key | expected_no_of_containers |
| Loader column | Expected No of Containers |
| Role | extracted |
| Requirement | conditional (amount_or_containers) |
| Type | integer |
| Matching allowed | no |

### Rules

- EN-02 [Assembly] Never default. (Confirmed; BioA written)

---

## Field: Container Tracking Method

| Attribute | Value |
|---|---|
| Key | container_tracking_method |
| Loader column | Container Tracking Method |
| Role | extracted |
| Requirement | optional |
| Type | text |
| Max length | 1 |
| Lookup list | Container Tracking Method |
| Default | i |
| Matching allowed | no |

### Rules

- TM-02 [Normalization] Translate the displayed value to its one-character code using the translation table below. (Confirmed; BioA written, D-43)
- TM-03 [Assembly] Default `i` (Individual) when not found. (Confirmed; Data info default)
- TM-04 [Validation] The exported value must be `i` or `t`. The Container Tracking Method lookup list holds these codes. (Confirmed; BioA written)

### Translation table

| Entry | Match type | Document wording | Lookup value | Status |
|---|---|---|---|---|
| TM-T01 | phrase | Individual | i | Confirmed |
| TM-T02 | phrase | Together | t | Confirmed |

---

## Field: Manage Container Inventory Flag

| Attribute | Value |
|---|---|
| Key | manage_container_inventory_flag |
| Loader column | Manage Container Inventory Flag |
| Role | extracted |
| Requirement | optional |
| Type | boolean |
| Max length | 1 |
| Default | Y |
| Matching allowed | no |

### Rules

- MI-02 [Assembly] Default Y when not found. (Confirmed; Data info default)

---

## Field: Container Type

| Attribute | Value |
|---|---|
| Key | container_type |
| Loader column | Container Type |
| Role | extracted |
| Requirement | required |
| Type | text |
| Max length | 40 |
| Lookup list | Container Type |
| Matching allowed | yes |

### Rules

- CO-03 [Normalization] Match to the Container Type list; a phrase that does not match goes to Matching. (Confirmed; D-21)
- CO-04 [Matching] [to write and confirm with BioA, e.g. whether a vial may match a tube] (Open; M-3)
- CO-05 [Validation] Required. (Confirmed; BioA)
- CO-06 [Assembly] Container size and unit are not loader fields; LabVantage takes them from the Container Type record. (Confirmed; Brad, D-45)

---

## Field: Manufacturer

| Attribute | Value |
|---|---|
| Key | manufacturer |
| Loader column | Manufacturer |
| Role | extracted |
| Requirement | optional |
| Type | text |
| Max length | 40 |
| Lookup list | Manufacturer |
| Sent to duplicate judge | yes |
| Matching allowed | no |

### Rules

- MF-03 [Normalization] Match the document's wording to the list (GEN-06). Similar entries such as "Thermo Fisher" and "Thermo Fisher Scientific" are distinct values; never merge them. Never sent to Matching. (Confirmed; 11/2, BioA written)
- MF-04 [Validation] No match: leave blank and raise an issue; the reviewer searches the list or creates the master data. (Confirmed; 11/2)

---

## Field: Supplier

| Attribute | Value |
|---|---|
| Key | supplier |
| Loader column | Supplier |
| Role | extracted |
| Requirement | optional |
| Type | text |
| Max length | 40 |
| Lookup list | Supplier |
| Matching allowed | no |

### Rules

- SU-03 [Normalization] Same matching as Manufacturer (MF-03). (Confirmed; 11/2)
- SU-04 [Validation] Same as MF-04. (Confirmed; 11/2)

---

## Field: Catalog No

| Attribute | Value |
|---|---|
| Key | catalog_no |
| Loader column | Catalog No |
| Role | extracted |
| Requirement | optional |
| Type | text |
| Multi-value separator | ", " |
| Sent to duplicate judge | yes |
| Matching allowed | no |

### Rules

- CN-02 [Assembly] Join several catalog numbers in one cell with ", ". Several numbers are not a conflict. (Design; build)
- CN-03 [Validation] Always text, to keep leading zeros. A missing catalog number raises no issue. (Design; BioA written: not every item has one)

---

## Field: Target Concentration

| Attribute | Value |
|---|---|
| Key | target_concentration |
| Loader column | Target Concentration |
| Role | extracted |
| Requirement | optional |
| Type | decimal |
| Sent to duplicate judge | yes |
| Matching allowed | no |

### Rules

- TC-02 [Normalization] A value is a concentration only when a concentration unit follows the number: weight per volume (e.g., ng/mL), weight per weight, or volume per volume. LabVantage accepts numbers only. (Confirmed; BioA written, 11/2)
- TC-03 [Normalization] Classify the value using the table below. Anything that is not a concentration is left blank with a warning. (Confirmed; BioA written, 11/2)
- TC-04 [Normalization] A multiplier such as "10x" may be part of the name (e.g., "10x PBS + Tween"); it is never a concentration. (Confirmed; 11/2)
- TC-05 [Assembly] The concentration unit has no loader field. (Open; FL-1)

### Concentration units

Used by TC-02. A unit counts as a concentration unit when it matches a row.

| Unit pattern | Examples | Status |
|---|---|---|
| unit per unit (contains "/") | ng/mL; ug/uL; mg/mL; cps/uL | Confirmed (cps/uL: Assumption) |
| percent with basis | % w/v; % w/w; % v/v | Confirmed |
| molar units | M; mM; uM; nM; pM | Assumption (BR-9) |

### Classification table

| Pattern | Example | Target Concentration | Issue | Status |
|---|---|---|---|---|
| Number + concentration unit | "5 ng/mL" | 5 | None | Confirmed |
| Scientific notation + copy-number unit | "1.6e4 cps/uL" | 16000 | Info: number read from text | Assumption (cps/uL as a concentration unit) |
| Ratio | "1:100" | blank | Warning: dilution ratio, not a concentration | Confirmed |
| Multiplier | "10x" | blank | Warning: multiplier, not a concentration | Confirmed |
| Number without a unit | "0.5" | blank | Warning: no concentration unit | Confirmed |
| No pattern | "half-strength" | blank | Warning: not recognized | Confirmed |

---

## Field: Approval Type

| Attribute | Value |
|---|---|
| Key | approval_type |
| Loader column | Approval Type |
| Role | derived |
| Requirement | optional |
| Type | text |
| Max length | 40 |
| Lookup list | Approval Type |
| Matching allowed | no |

### Rules

- AT-01 [Assembly] Set from Consumable Class and Critical using the approval type table in the business rules section. (Confirmed; 11/2, BioA written, SOP 7.2.2.5)
- AT-02 [Assembly] Never set ReagentVersionApproval. It approves the master data and stays a manual step. (Confirmed; 11/2, BioA written)

---

## Field: Worksheet Template

| Attribute | Value |
|---|---|
| Key | worksheet_template |
| Loader column | Worksheet Template |
| Role | derived |
| Requirement | optional |
| Type | text |
| Max length | 40 |
| Lookup list | Worksheet Template |
| Matching allowed | no |

### Rules

- WT-01 [Assembly] Prepared + Critical Y → "BAL Consumable Dynamic LES Worksheet (With Stages) W/ Critical Approval". (Assumption; SOP 7.4.2.2; confirm exact list value, BR-6)
- WT-02 [Assembly] Prepared + Critical N → "BAL Consumable Dynamic LES Worksheet (With Stages) W/ Non- Critical Approval". (Assumption; SOP 7.4.2.2; BR-6)
- WT-03 [Assembly] Purchased → blank. (Assumption; BR-6)

### Worksheet template table

Used by WT-01 to WT-03.

| Consumable Class | Critical | Worksheet Template | Status |
|---|---|---|---|
| Prepared | Y | BAL Consumable Dynamic LES Worksheet (With Stages) W/ Critical Approval | Assumption (BR-6) |
| Prepared | N | BAL Consumable Dynamic LES Worksheet (With Stages) W/ Non- Critical Approval | Assumption (BR-6) |
| Purchased | any | (blank) | Assumption (BR-6) |

---

## Field: Status

| Attribute | Value |
|---|---|
| Key | status |
| Loader column | Status |
| Role | system |
| Requirement | optional |
| Type | text |
| Max length | 20 |
| Lookup list | Status |

### Rules

- ST-01 [Assembly] Export blank. LabVantage assigns Provisional on load; approval moves it to Current. (Confirmed; 11/2, D-42)

---

## Field: Expiry Based On

| Attribute | Value |
|---|---|
| Key | expiry_based_on |
| Loader column | Expiry Based On |
| Role | blank_for_now |
| Requirement | optional |
| Type | text |

### Rules

- EX-01 [Assembly] Exported blank until BioA defines the rules. (Open; BR-7)

---

## Field: Expiry Period

| Attribute | Value |
|---|---|
| Key | expiry_period |
| Loader column | Expiry Period |
| Role | blank_for_now |
| Requirement | optional |
| Type | text |

### Rules

- EX-02 [Assembly] Exported blank until BioA defines the rules. (Open; BR-7)

---

## Field: Expiry Period Units

| Attribute | Value |
|---|---|
| Key | expiry_period_units |
| Loader column | Expiry Period Units |
| Role | blank_for_now |
| Requirement | optional |
| Type | text |

### Rules

- EX-03 [Assembly] Exported blank until BioA defines the rules. (Open; BR-7)

---

## Context attributes

Extracted once per candidate record, with the same shape as a field (status, value, evidence, alternatives, warning). Never exported or displayed (D-07, D-30).

## Field: source_heading

| Attribute | Value |
|---|---|
| Key | source_heading |
| Loader column | none |
| Role | context |
| Requirement | optional |
| Type | text |
| Drives | critical |

### Rules

- SH-02 [Validation] An unresolved finding on this attribute appears as an issue on Critical. (Confirmed; D-31)

## Field: serial_dilution

| Attribute | Value |
|---|---|
| Key | serial_dilution |
| Loader column | none |
| Role | context |
| Requirement | optional |
| Type | text |
| Drives | approval_type |

### Rules

- SD-02 [Validation] An unresolved finding on this attribute appears as an issue on Approval Type. (Confirmed; D-31)

---

## Business rules (across fields)

### Approval type table

Used by AT-01. Rows are checked top to bottom; the first match applies. The `serial_dilution` column is yes when that context attribute was found.

| Consumable Class | Critical | serial_dilution | Approval Type | Status |
|---|---|---|---|---|
| any | any | yes | (blank) | Confirmed (SOP 7.2.2.5.d) |
| Prepared | Y | no | MixConsumableCritical | Confirmed (11/2; SOP 7.2.2.5.a) |
| Prepared | N | no | MixConsumableNonCritical | Confirmed (11/2; SOP 7.2.2.5.b) |
| Purchased | Y | no | RecConsumableCritical | Confirmed (11/2; SOP 7.2.2.5.c) |
| Purchased | N | no | (blank) | Confirmed (SOP 7.2.2.5.d) |

### Condition groups

- COND-01 [Validation] amount_or_containers: Expected Amount with Expected Amount Unit, or Expected No of Containers, must be present. Otherwise `CONDITION_UNMET` (error). (Confirmed; Data info)
- COND-02 [Validation] amount_with_unit: Expected Amount and Expected Amount Unit are both present or both empty. Otherwise `PAIR_INCOMPLETE`. (Design; build)

| Group | Rule | Fields | Issue code | Status |
|---|---|---|---|---|
| amount_or_containers | one_of | expected_amount + expected_amount_unit; expected_no_of_containers | CONDITION_UNMET | Confirmed |
| amount_with_unit | both_or_neither | expected_amount; expected_amount_unit | PAIR_INCOMPLETE | Design |

### Naming rules

Inserted into the Naming prompt. Source: SOP 7.1, scope BAL-DUR.

- NM-01 [Naming] General format: `<Concentration> <Chemical/Reagent>_<Signifier1>_<Signifier2>`. Example: "Absolute Ethanol_Molecular Biology Grade". (Confirmed; SOP 7.1.3)
- NM-02 [Naming] HPLC columns and plates: `<Type>_<Size>`. Example: "Allure Biphenyl_200 x 2.1 x 1.8uM". (Confirmed; SOP 7.1.4)
- NM-03 [Naming] Primers: `<Concentration>_<Target>_<Species>_Primer_<FWD/REV>_<Signifier>`. (Confirmed; SOP 7.1.5)
- NM-04 [Naming] Probes: `<Concentration>_<Target>_<Species>_<Probe>_<Fluorophore>_<Signifier>`. Example: "500uM_Albumin_Hum_Probe_VIC_RCL OTS". (Confirmed; SOP 7.1.5)
- NM-05 [Naming] Assay mixes: `<Concentration>_<Vendor>_<Target>_<Fluorophore>_<Species>_<Signifier> Assay Mx`. Example: "20X BAL_Albumin_VIC_Hum_RCL OTS Assay Mx". (Confirmed; SOP 7.1.5)
- NM-06 [Naming] Use the standard abbreviations: STD (standard), BUF (buffer), SOL (solvent), REF (reference standard), FWD (forward), REV (reverse), Hum (human). (Confirmed; SOP 7.1.2)
- NM-07 [Naming] Up to 40 characters; no Greek letters (apply the character translation table). (Confirmed; SOP 7.1.1)
- NM-08 [Naming] Use only parts the record holds. Leave a part out rather than invent it. (Design; D-39)
- NM-09 [Naming] These rules apply to Durham. Conventions at other sites, and Dave's updated conventions, are not yet defined. (Open; BR-1)

### Plausibility checks

Inserted into the plausibility prompt. **None are active** until VAL-2 is decided with Tina. Candidates:

- PL-01 [Plausibility] Storage condition vs item type (e.g., a room-temperature buffer stored at -80C). (Open; VAL-2)
- PL-02 [Plausibility] Amount magnitude (e.g., 50 L expected for an antibody). (Open; VAL-2)
- PL-03 [Plausibility] Class vs description. (Open; VAL-2)
- PL-04 [Plausibility] Consistency across a serial dilution (e.g., two levels with the same concentration). (Open; VAL-2)

---

## Open questions for BioA

| # | Question | Rules affected |
|---|---|---|
| BR-1 | Naming conventions at sites other than Durham, and when Dave's updated conventions will be ready | NM-09 |
| BR-2 | How BAL is written as a vendor in documents; whether "vendor" means Manufacturer; the class of a prepared reagent with no vendor listed | CC-05, CC-06, BAL vendor names |
| BR-3 | Is Cryo an active storage value? What range maps to -80C? Does "ambient" mean Room Temperature? Is ±10 °C right for -20C? | SC-T05, SC-T07, SC-T08 |
| BR-4 | When are Count, (Containers) and Vial used as units? | EU-04 |
| BR-5 | When only one vendor is named, should it go in both Manufacturer and Supplier? | MF-02, SU-02 |
| BR-6 | Is Worksheet Template in scope? Is it blank for Purchased items? Confirm the exact list values | WT-01 to WT-03 |
| BR-7 | Rules for Expiry Based On, Expiry Period and Expiry Period Units | EX-01 to EX-03 |
| BR-8 | Critical as Y/N or Yes/No in the loader | CR-04 |
| BR-9 | Do molar units (M, mM, uM, nM) and cps/uL count as concentration units? | Concentration units table |
| FL-1 | The concentration unit has no loader field: drop it, or keep it in the audit output only? | TC-05 |

---

## Change log

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-11-11 | Created from the earlier field rules file (v0.3), BioA's written answers, the 11/2 instruction review and Brad's confirmation. Fixes the old file's rules that contradicted BioA: "1 mL vial" split into amount and unit; batch volume as expected amount; Critical and Consumable Class only when stated; Container Tracking default "Individual"; "or equivalent" dropped from catalog numbers; no naming convention. Adds the character, storage and tracking-method translation tables, derivations, naming rules, the Container Type requirement and the expiry fields |
| 1.1 | 2026-11-11 | Added data tables so no BioA value has to live in code: excluded lookup values, class table, critical headings, concentration units, worksheet template table, condition groups table, the "frozen" row (SC-T09) and the serial-dilution row of the approval type table. Added `Drives` to the context attributes and BR-9 |
| 1.2 | 2026-11-11 | Removed the list of fields taken out of the loader; the loader columns are the field sections above, nothing else |
| 1.3 | 2026-11-16 | Derivation tables written so code can read them: the class table reads the Manufacturer column and refers to the BAL vendor names table; the critical headings table has a row for every other heading; the approval type table's serial dilution column is named `serial_dilution`. No rule changed |
| 1.4 | 2026-11-16 | Moved every [Extraction] line (general, candidate criteria, fields and context attributes) to `extraction_rules.md`, unchanged. Field sections hold structural facts; column order comes from `export_template.md` |
