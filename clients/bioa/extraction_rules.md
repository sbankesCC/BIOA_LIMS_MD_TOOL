# BioA Extraction Rules: Consumable Type

| Attribute | Value |
|---|---|
| Version | 1.0 |
| Last updated | 2026-11-16 |

This file holds the extraction guidance: what counts as a Consumable Type, and what the model copies for each field. The extraction and extraction verification prompts read their rules only from this file. The fields themselves (key, loader column, data type, one value or several) are defined in `business_rules.md`.

---

## How to read and edit this file

The structure is strict, because code reads parts of this file. Code checks the file at startup and refuses to run if it is malformed.

- `## General rules` holds the rules for every field under `### Rules`, and what counts as a Consumable Type under `### Candidate criteria`.
- One `## Field: <key>` section per extracted field and context attribute, named by its key in `business_rules.md`, with its rule lines under `### Rules`.
- Every rule line is tagged `[Extraction]` and written as `- <Rule ID> [Extraction] <Rule>. (<Status>; <Source>)`. Open lines are not inserted into the prompts.
- Rule IDs are unique across this file and `business_rules.md`.
- At startup, code checks that every extracted field and context attribute has a section with at least one active line, and that no section names any other key.

---

## General rules (all fields)

### Rules

- GEN-01 [Extraction] Copy every value exactly as written in the documents, whole: no formatting, conversion, completion or inference. (Confirmed; D-03, D-05)
- GEN-02 [Extraction] If a value is not written in the documents, it is not_found. Never fill a value to complete a record. (Confirmed; charter review)

### Candidate criteria

Inserted into the extraction prompt (D-46).

- CAND-01 [Extraction] A Consumable Type is a kind of material used to run the assay: purchased reagents, kits, water, buffers and solutions, master mixes, primers and probes, reference standards, controls (QCs), and materials provided by the sponsor. (Assumption; prompt v0.4; confirm with BioA SME, E-1)
- CAND-02 [Extraction] Each distinct material is its own record. Different concentrations, a stock vs a working solution, and each level of a serial dilution are separate records. (Confirmed; SOP 7.4.3)
- CAND-03 [Extraction] Not Consumable Types: instruments and equipment, software, study samples. (Assumption; prompt v0.4; E-1)
- CAND-04 [Extraction] Look in reagent and materials tables, preparation sections and supplemental worksheets. Prepared reagents may appear only on a worksheet. (Assumption; prompt v0.4; E-1)
- CAND-05 [Extraction] The same material may appear in several documents: make one record and cite every place. (Design; build)

---

## Field: consumable_type

### Rules

- CT-01 [Extraction] The material's name exactly as written. Do not shorten it or apply a naming convention. (Confirmed; build)

---

## Field: description

### Rules

- DS-01 [Extraction] A description of the material if the document gives one, such as the vendor's product name. Copy as written. (Design; build)

---

## Field: storage_condition

### Rules

- SC-01 [Extraction] The storage temperature or condition as written, including words such as frozen, refrigerated or cryogenic, e.g. "-20 °C" or "2–8 °C". (Confirmed; 11/2)

---

## Field: expected_amount

### Rules

- EA-01 [Extraction] The quantity of material expected per container, number only, as written, only when the document states it. (Confirmed; build, 11/2)
- EA-02 [Extraction] A container phrase such as "1 mL vial" is the Container Type, not the expected amount. (Confirmed; 11/2)
- EA-03 [Extraction] Do not use the volume prepared per batch as the expected amount. (Confirmed; BioA written)

---

## Field: expected_amount_unit

### Rules

- EU-01 [Extraction] The unit of the expected amount as written. (Confirmed; build)

---

## Field: expected_no_of_containers

### Rules

- EN-01 [Extraction] The number of containers per lot, only when stated. (Confirmed; build)

---

## Field: container_tracking_method

### Rules

- TM-01 [Extraction] Only if the document says how containers are tracked. Usually not_found. (Design; build)

---

## Field: manage_container_inventory_flag

### Rules

- MI-01 [Extraction] Y or N, only if the document says whether container inventory is managed. Usually not_found. (Design; build)

---

## Field: container_type

### Rules

- CO-01 [Extraction] The whole container phrase as written, including size and unit, e.g. "1 mL vial" or "15 mL conical tube". Never split it into an amount and a unit. (Confirmed; 11/2)
- CO-02 [Extraction] Words such as tube, bottle, vial, microtube or conical tube mark a container type. (Confirmed; 11/2)

---

## Field: manufacturer

### Rules

- MF-01 [Extraction] The company that makes the material, as written. (Confirmed; build, 11/2)
- MF-02 [Extraction] If only one vendor is named, put it in both Manufacturer and Supplier. (Assumption; BR-5)

---

## Field: supplier

### Rules

- SU-01 [Extraction] The company the material is bought from, as written. Kept separate from Manufacturer. (Design; build)
- SU-02 [Extraction] If only one vendor is named, put it in both Manufacturer and Supplier. (Assumption; BR-5)

---

## Field: catalog_no

### Rules

- CN-01 [Extraction] Every catalog number for this material, one entry each, as written, including "or equivalent" (e.g., "1234 or equivalent"). (Confirmed; BioA written, 11/2)

---

## Field: target_concentration

### Rules

- TC-01 [Extraction] The concentration as written, with its unit, e.g. "100 uM" or "1e4 cps/uL". (Confirmed; build)

---

## Field: source_heading

### Rules

- SH-01 [Extraction] The heading of the table or section the item is listed under, as written (e.g., "Table 3. Critical Reagents"). (Confirmed; D-07)

---

## Field: serial_dilution

### Rules

- SD-01 [Extraction] The text stating that the item is one level of a serial dilution (e.g., "STD 1–8 prepared by serial dilution of the stock"). (Confirmed; D-07, SOP 7.4.3)
