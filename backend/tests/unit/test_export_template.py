"""Export template tests: the parser on a synthetic file, and the startup checks on the real one.

The synthetic file uses made-up columns only (labeled synthetic). Edits to the real file are
built at run time from the loaded config, so no client value is written here.
"""

from pathlib import Path

import pytest

from app.config.bundle import ConfigBundle
from app.config.errors import ConfigError
from app.config.export_template import ExportColumn, parse_export_template
from tests.conftest import assert_config_error

EXPORT_TEMPLATE = "export_template.md"

# A minimal synthetic export template: sheet settings and three columns
SYNTHETIC_TEMPLATE = """# Synthetic export template

| Attribute | Value |
|---|---|
| Version | 9.9 |

## How to read this file (prose, not parsed)

| Not | Read |
|---|---|
| a | b |

## Sheet

| Setting | Value |
|---|---|
| Sheet name | Synthetic sheet |
| Header bold | yes |
| Freeze header row | no |

## Columns

| Column | Type | Format |
|---|---|---|
| Syn Name | text | |
| Syn Amount | number | 2 decimals |
| Syn Date | date | MM/DD/YYYY |
"""


def edit_template(config_dir: Path, old: str, new: str) -> None:
    """Replace text that appears exactly once in a config copy's export template."""
    path = config_dir / EXPORT_TEMPLATE
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"{old!r} found {text.count(old)} times"
    path.write_text(text.replace(old, new), encoding="utf-8")


def column_row(name: str, kind: str, format_text: str = "") -> str:
    """Return a Columns table row as written in the file."""
    return f"| {name} | {kind} | {format_text} |" if format_text else f"| {name} | {kind} | |"


# ----- Parser -----


def test_sheet_settings_and_columns_are_read_in_order() -> None:
    """Version, sheet settings and columns come from their tables, in file order."""
    template = parse_export_template(SYNTHETIC_TEMPLATE)
    assert template.version == "9.9"
    assert (template.sheet.name, template.sheet.is_header_bold) == ("Synthetic sheet", True)
    assert template.sheet.is_header_frozen is False
    assert template.headers == ["Syn Name", "Syn Amount", "Syn Date"]


@pytest.mark.parametrize(
    ("kind", "format_text", "excel_format"),
    [
        ("text", "", "General"),
        ("number", "2 decimals", "0.00"),
        ("number", "0 decimals", "0"),
        ("date", "MM/DD/YYYY", "mm/dd/yyyy"),
    ],
)
def test_formats_become_excel_number_formats(
    kind: str, format_text: str, excel_format: str
) -> None:
    """A blank format is Excel's default; decimals and date patterns become Excel formats."""
    column = ExportColumn.model_validate({"name": "Syn", "type": kind, "format": format_text})
    assert column.excel_format() == excel_format


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("| Syn Name | text | |", "| Syn Name | money | |", "'Type' is 'money'"),
        ("| number | 2 decimals |", "| number | MM/DD/YYYY |", "does not fit type 'number'"),
        ("| text | |", "| text | 2 decimals |", "does not fit type 'text'"),
        ("| Syn Date | date |", "| Syn Name | date |", "'Syn Name' is listed twice"),
        ("| Header bold | yes |", "| Header bold | maybe |", "'Header bold' is 'maybe'"),
        ("| Freeze header row | no |\n", "", "missing the setting 'Freeze header row'"),
        ("| Synthetic sheet |", "| Synthetic/sheet |", "may not contain any of"),
        ("| Version | 9.9 |", "| Edition | 1 |", "needs a 'Version' row"),
    ],
)
def test_malformed_template_is_rejected(old: str, new: str, message: str) -> None:
    """Each malformed part stops loading with a plain message naming it."""
    assert SYNTHETIC_TEMPLATE.count(old) == 1
    with pytest.raises(ConfigError, match=message):
        parse_export_template(SYNTHETIC_TEMPLATE.replace(old, new))


# ----- Startup checks against business_rules.md -----


def test_missing_export_template_stops_loading(config_copy: Path) -> None:
    """Without export_template.md the config does not load; there is no Excel fallback."""
    (config_copy / EXPORT_TEMPLATE).unlink()
    assert_config_error(config_copy, f"{EXPORT_TEMPLATE}: file not found")


def test_loader_column_missing_from_the_template_is_reported(
    config_copy: Path, bundle: ConfigBundle
) -> None:
    """Every loader column of the business rules needs a row in the template."""
    column = bundle.export_template.columns[0]
    edit_template(config_copy, column_row(column.name, column.type, column.format) + "\n", "")
    assert_config_error(config_copy, f"the loader column '{column.name}' of business_rules.md")


def test_template_column_that_is_not_a_loader_column_is_reported(
    config_copy: Path, bundle: ConfigBundle
) -> None:
    """A template column must be a loader column of the business rules."""
    column = bundle.export_template.columns[0]
    edit_template(
        config_copy,
        column_row(column.name, column.type, column.format),
        column_row("Synthetic Column", column.type),
    )
    assert_config_error(config_copy, "the column 'Synthetic Column' is not a loader column")


def test_type_that_disagrees_with_the_field_type_is_reported(
    config_copy: Path, bundle: ConfigBundle
) -> None:
    """A number field exported as text (or the reverse) is rejected."""
    rule = next(rule for rule in bundle.business_rules.fields if rule.type == "decimal")
    edit_template(config_copy, column_row(rule.column, "number"), column_row(rule.column, "text"))
    assert_config_error(config_copy, f"'{rule.column}' is type 'text', but the field is 'decimal'")
