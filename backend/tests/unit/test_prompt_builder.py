"""Prompt builder tests: placeholders filled, comments removed, chunks as text and image parts."""

import pytest

from app.config.bundle import ConfigBundle
from app.config.prompts import PromptTemplate
from app.contracts.chunk import Chunk
from app.llm.client import ImagePart, PromptPart, TextPart
from app.llm.prompt_builder import (
    PromptError,
    ReextractionProblem,
    build_field_section,
    build_prompt_parts,
    build_reextraction_section,
    format_judge_record,
)
from tests.unit.validation_helpers import make_record

TEXT_CHUNK = Chunk(
    chunk_id="doc01-c001",
    document_id="doc01",
    page=None,
    section="synthetic section",
    sheet=None,
    row_range=None,
    kind="paragraph",
    is_scanned=False,
    text="Synthetic paragraph text.",
    image_ref=None,
)
IMAGE_CHUNK = Chunk(
    chunk_id="doc02-p01-c001",
    document_id="doc02",
    page=1,
    section=None,
    sheet=None,
    row_range=None,
    kind="page_image",
    is_scanned=True,
    text=None,
    image_ref="runs/run_synthetic/pages/doc02-p01-c001.png",
)


def make_template(text: str) -> PromptTemplate:
    """Return a synthetic prompt template."""
    return PromptTemplate(name="synthetic", version="0.1", status="test", text=text)


def all_text(parts: list[PromptPart]) -> str:
    """Return the text of every text part, joined."""
    return "".join(part.text for part in parts if isinstance(part, TextPart))


def test_placeholders_are_filled_and_comments_removed() -> None:
    """Values replace their placeholders; HTML comments (and the header) disappear."""
    template = make_template("<!-- prompt: synthetic -->\n# Role\nA {record} B\n<!-- note -->\nEnd")
    parts = build_prompt_parts(template, {"record": "synthetic value"})
    assert all_text(parts) == "# Role\nA synthetic value B\n\nEnd\n"


def test_placeholder_text_inside_a_value_is_not_replaced_again() -> None:
    """A filled value that looks like a placeholder stays as it is."""
    template = make_template("{record} and {candidates}")
    parts = build_prompt_parts(template, {"record": "{candidates}", "candidates": "x"})
    assert all_text(parts) == "{candidates} and x\n"


def test_json_braces_in_the_template_are_kept() -> None:
    """JSON examples with braces are not placeholders."""
    template = make_template('Shape: { "judgments": [] }')
    assert all_text(build_prompt_parts(template, {})) == 'Shape: { "judgments": [] }\n'


def test_missing_value_is_an_error() -> None:
    """A placeholder with no value raises a plain error naming it."""
    with pytest.raises(PromptError, match="record"):
        build_prompt_parts(make_template("A {record}"), {})


def test_chunks_become_labeled_text_and_image_parts() -> None:
    """Text chunks are `[chunk_id] text`; a page image is a label followed by an image part."""
    template = make_template("Static first\n{chunks}\nAfter")
    parts = build_prompt_parts(template, {}, [TEXT_CHUNK, IMAGE_CHUNK])
    assert isinstance(parts[0], TextPart)
    assert parts[0].text.startswith("Static first")
    assert "[doc01-c001] Synthetic paragraph text." in parts[0].text
    assert parts[0].text.endswith("[doc02-p01-c001] (scanned page image)\n")
    assert parts[1] == ImagePart(chunk_id="doc02-p01-c001", image_ref=IMAGE_CHUNK.image_ref or "")
    assert isinstance(parts[2], TextPart)
    assert "After" in parts[2].text


def test_real_prompts_fill_every_placeholder(bundle: ConfigBundle) -> None:
    """Each client prompt builds with its placeholders and keeps no comment or placeholder."""
    values = {
        "field_section": "synthetic fields",
        "reextraction_section": "",
        "citation_results": "synthetic results",
        "records": "synthetic records",
        "excluded_items": "(none)",
        "record": "synthetic record",
        "candidates": "synthetic candidates",
    }
    for template in bundle.prompts.values():
        text = all_text(build_prompt_parts(template, values, [TEXT_CHUNK]))
        assert "<!--" not in text
        assert "{field_section}" not in text and "{chunks}" not in text


def test_field_section_has_one_line_per_extracted_field(bundle: ConfigBundle) -> None:
    """The field section lists every extracted field with its key, column and guidance."""
    lines = build_field_section(bundle.field_rules).splitlines()
    extracted = bundle.field_rules.extracted_fields()
    assert len(lines) == len(extracted)
    assert lines[0].startswith(f"- {extracted[0].key} ({extracted[0].column})")


def test_reextraction_section_lists_records_and_problems(bundle: ConfigBundle) -> None:
    """The section names the affected record, each problem, and missed items as written."""
    record = make_record(bundle, record_id="rec_0002")
    problems = [
        ReextractionProblem(record_id="rec_0002", field="description", problem="unsupported"),
        ReextractionProblem(item="Syn item", problem="missed candidate", chunk_ids=["doc01-c001"]),
    ]
    section = build_reextraction_section([record], problems)
    assert section.startswith("# Problems to fix")
    assert "- rec_0002: synthetic record" in section
    assert "- rec_0002, field description: unsupported" in section
    assert '- item "Syn item": missed candidate (doc01-c001)' in section


def test_reextraction_section_is_empty_without_problems() -> None:
    """A first extraction gets an empty re-extraction section."""
    assert build_reextraction_section([], []) == ""


def test_judge_record_shows_column_names_and_missing_values(bundle: ConfigBundle) -> None:
    """The judge sees each identifying field by column name; an empty one is "not given"."""
    rule = bundle.field_rules.record_name_field()
    text = format_judge_record({rule.key: "Syn A", "description": None}, bundle.field_rules)
    assert f"- {rule.column}: Syn A" in text
    assert "(not given)" in text
