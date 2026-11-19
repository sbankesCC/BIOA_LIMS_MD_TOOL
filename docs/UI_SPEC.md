# UI specification

The defined screens and review behaviors of the pilot. Mockups: https://claude.ai/artifact/94a4dJBRDVaksUSy8BLM5a (static HTML copies in `ui_mockups/`).
The mockups are static and use placeholder values. Where this document and the mockups differ, this document wins.

## 1. Principles

- Users must never lose work. Runs are saved; users can leave and come back.
- Guided resolution, not free editing. The grid is read-only; values change only through issue actions in the panel.
- Every record and every value shows where it came from.
- Simple and familiar: patterns like a grammar checker ("here is the problem, here are your options").
- No chat, no in-tool approval workflow (QC approves in LabVantage, SOP §7.9).

## 2. Visual design

- Clarkston design system: Clarkston Blue header, Futura PT headings, Proxima Nova body (fallback Franklin Gothic / Libre Franklin), gold only for the one main action per screen.
- Neutral light background (not the warm Clarkston gray).
- Status colors (red, amber, grey, green) are outside the brand palette. Always paired with an icon and a word, never color alone.
- No Clarkston logo (BioA-facing tool).

## 3. Navigation

- Top bar (not a sidebar: the review grid needs the width): product name, New run, Runs, "How it works", Admin.
- Admin button is always visible in the pilot (placeholder sign-in).
- "How it works" opens a popup. It opens automatically on a user's first visit.

## 4. Screens

### 4.1 Start a run (landing page)
- Run name field, pre-filled from the first file name and today's date; editable now and later.
- Upload area: drag and drop or "Browse files". Accepts `.docx`, `.pdf`, `.xlsx`. Other types rejected immediately with a short message.
- File list: name, type, size, page count; remove button.
- "Start extraction" button (gold), disabled until a file is added.
- Recent runs list: name, started, status, record count, what needs action. Clicking opens the run.

### 4.2 Processing
- Step list (not a percentage bar): Reading documents, Extracting consumables, Checking against the documents, Formatting values, Matching list values, Suggesting names, Filling derived fields, Final checks. One step per processing status. The steps follow the run status (`ARCHITECTURE.md` §6). Current step highlighted; finished steps checked.
- "You can leave this page. Your run is saved."
- Failed: plain-language reason and Retry. Retry starts a new run from the same files; the failed run stays in the list.

### 4.3 Review and resolve (main screen)

Header:
- Run name (rename), document count, lookup list version, reference data date.

Run-level banner:
- For run issues (e.g. scanned pages, unreadable file, a skipped Matching, Naming or plausibility step). Has an X to dismiss; dismissal is remembered for the run.

Summary strip:
- Counts: Records, To fix (red), Warnings (yellow), Excluded.
- Filters: All, Needs action, Excluded.

Records grid (read-only):
- Columns in order: **Action needed** (Fix / Check / None / Excluded, icon + word), **Consumable Type**, **Found in** (document · section · page, "+1 more" when several), then the field columns.
- Found in is required on every row. Clicking it opens the source text with the passage highlighted.
- Clicking any value opens the panel on that field; a value with an issue opens that issue.
- Cells with issues are tinted (red / yellow); not-found optional values show "— (not found)" in grey.
- Excluded rows: struck through, reason shown, Restore link.
- Scrolls through all records; sticky header row; Action needed and Consumable Type columns pinned; other columns scroll sideways.
- The columns come from the API (`GET /runs/{id}/fields`), in export order (`export_template.md`). Context attributes (`source_heading`, `serial_dilution`) are never shown.
- Fields exported blank (`system`, `blank_for_now`) show an empty grey cell (read-only).
- Derived fields (Critical, Consumable Class, Approval Type, Worksheet Template) show their value like any other; the panel says it was derived.
- A field with a suggestion and no value shows the suggestion in grey italics with "suggested" (it is not exported until used). The Consumable Type column shows the suggested name this way until a name is set.
- Each value shows the text as written in the document next to the exported value when they differ (e.g. "2–8 °C" → 4C; "1e4 cps/uL" → 10000). "or equivalent" stays in the value as written.

Resolution panel (right side):
- Top: Previous / Next issue arrows that move through all open issues in the run, across records ("Issue 1 of 11 open"); close button.
- Record name.
- Compact list of this record's issues (icon, field, short label). Clicking one selects it.
- Only the selected issue is expanded.
- Footer: "Exclude record" (asks for a reason) and "Save and next issue". No other arrows in the footer.

Issue actions (only the actions that fit the issue):

| Issue | Actions |
|---|---|
| Required value missing | Enter value: searchable dropdown for list fields, checked input for free text |
| Not in lookup list | When there is a Matching suggestion: shown with its reason and a "Use suggestion" action. Or pick from searchable dropdown, closest matches first |
| Name not set | When there is a Naming suggestion: shown with its reason and the naming rule, and a "Use suggestion" action. Or type a name (checked input) |
| Reviewer choice needed | Pick one of the offered values (e.g. -20C or -80C for "frozen"), each with "Show source", or another value from the list |
| Value unclear | Shows the extraction's warning. View source; enter the value, mark not found, or Accept |
| Value incomplete | View source; enter the whole value (an error, so it cannot be accepted) |
| Not a concentration | Shows the value as written. Enter a number, or leave blank |
| Derived value missing | Says what input is missing (e.g. no vendor). Enter the input field, or set the derived value directly |
| Derived value differs | Shows the set value and the derived value. Use the derived value, or keep the set value with a note |
| Conflict closed (grey) | Nothing to do: the sources agree after formatting |
| Plausibility check | Shows the check ID and reason. View the fields; Accept, or Change |
| Conflicting values | Pick one alternative (each with "Show source"), or "Other value" from the list |
| Citation not verified / unsupported | View source; Accept, Change, or mark not found |
| Optional value not found (grey) | Leave blank, or Add value |
| Possible duplicate of existing type | Side-by-side comparison; "Not a duplicate" or Exclude record |
| Default applied | Accept, or Change |
| Formatting corrected (grey) | Nothing to do |
| Not a consumable | Exclude record (with reason), or Accept |
| Should be split / may be missing (one at a time) | View source; split or add outside the tool, or confirm; a note saying what was done is required |

Changing a value that has no issue: click the cell, "Change value", reason required.

Bulk actions (offered in the panel when they apply):
- Change all: same field, same issue, same current value. Shows "Also applies to N other records"; confirmation list with all records checked; user can uncheck any.
- Fill missing: "Supplier is missing in N records. Set all to X?" with the same confirmation list.
- Accept all warnings of this type.
- Resolve repeated conflicts: "Use the method's value for all N similar conflicts."
- Bulk actions only touch flagged values; never verified (no-issue) values.
- Individual-review warnings are never offered in "Also apply to N similar". Their Accept button is enabled only after the user opens "Show source".
- Each bulk action is one undo.
- No free-form "select rows and set a field".

Saving and re-checking:
- "Save and next issue" stores the choice immediately (`POST /runs/{id}/changes`).
- The re-check (the review service runs Assembly, then the Validation service; derived fields are recomputed unless a person set them) runs when the user moves to another record, after a bulk action, after an exclude/restore, or on Verify (`POST /runs/{id}/recheck`). This avoids a slow re-check on every click.

Bottom action bar (fixed to the bottom of the window):
- Progress: issues resolved (e.g. "9 of 20").
- Reminder: "Before importing into production LabVantage, review all values, including those without warnings."
- State text: "Not verified yet: exports are saved as drafts" (or "Verified by X on date").
- "Verify output" (secondary) and "Export to Excel" (gold, always enabled).

### 4.4 Verify dialog
- Opens when the user clicks Verify output with open items.
- Red issues: "N issues to fix. These must be resolved before you can verify." Verify disabled.
- Warnings that need individual review (citation not verified, source may not support it, unreported conflict, value unclear, reviewer choice needed, derived value differs, plausibility check): "N warnings must be reviewed one at a time." Verify disabled, with a link to the first one.
- Other yellow warnings only: "N warnings not reviewed. If you verify, they are accepted as they are." Allows "Accept warnings and verify".
- Includes the production reminder text.
- "Keep reviewing" returns to the grid.
- After verifying: header shows the verified label. Any later change removes it.

### 4.5 Export
- Downloads two files: the loader and the audit workbook (`ARCHITECTURE.md` §4.10, `CONTRACTS.md` §8).
- Unverified exports are drafts (file name says draft).
- Exports are numbered; the run keeps the list.

### 4.6 Admin: Lookup lists
- Current version card: version, uploaded by, date; "Download current workbook".
- Upload area; after upload, a check report:
  - Passed checks (based on the current version, sheets and headers present).
  - Problems to fix, each with sheet, row and plain explanation.
  - Changes from the current version by list (added, removed), with "View every added and removed value".
- "Apply updates as vN" (disabled with the reason while problems remain).
- Version history: version, uploaded by, date, changes, Current/Superseded, Download, "Restore vN".
- Wording: "Apply updates", "Current", "Restore" (not "activate", "active", "roll back").

### 4.7 Admin: Reference data
- Same pattern as lookup lists: current snapshot date, upload, column check report, apply, history. (No mockup; follow the lookup lists screen.)

## 5. Screens without a mockup

Build these from this spec, in the style of the mockups: How it works popup; Reference data admin page; bulk-action confirmation list; exclude-record dialog; possible-duplicate comparison; post-export state; failed run state.
