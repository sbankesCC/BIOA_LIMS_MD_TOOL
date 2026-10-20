# Case notes (synthetic_001)

Synthetic case so the harness runs end to end with the fake LLM. All names and values are made up.

- Documents: `synthetic_001_method.docx` (section 6.2 reagent table, 6.3 equipment) and
  `synthetic_001_worksheet.xlsx` (sheet "Reagents"). Rebuild them with `make_documents.py`.
- Storage of the coating antibody differs: "-20 °C" in the method, "2–8 °C" in the worksheet
  (deliberate conflict).
- The detection reagent is only in the worksheet, so the fake extraction misses it at first and
  extraction verification reports it as a missed candidate (one re-extraction).
- "Synthetic Plate Reader" is equipment: an excluded item.
- Seeded error: the harness plants "Synthetic Vendor Two" as the antibody's manufacturer in the
  first extraction response; the fake verification reply reports it as `contradicted`.
- Not labeled (left out on purpose): container type size and unit of the antibody and the wash
  buffer ("1 mL vial" / "500 mL bottle" do not state a container size apart from the amount).
- `fake_llm/`: fake replies for every LLM call. They make one deliberate mistake: the antibody's
  container type ("vial") is returned as not_found, so the field and status scores are 37 of 38.
