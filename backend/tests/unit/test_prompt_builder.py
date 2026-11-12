"""Prompt builder tests: placeholders filled, comments removed, chunks as text and image parts."""

import pytest

from app.config.bundle import ConfigBundle
from app.config.business_rules import RuleLine
from app.config.business_rules_checks import parse_business_rules
from app.config.prompts import PromptTemplate
from app.contracts.chunk import Chunk
from app.llm.client import ImagePart, PromptPart, TextPart
from app.llm.prompt_builder import (
    NOTHING_TEXT,
    PromptError,
    ReextractionProblem,
    build_candidate_rules,
    build_checks,
    build_context_section,
    build_field_section,
    build_general_rules,
    build_matching_rules,
    build_naming_rules,
    build_prompt_parts,
    build_reextraction_section,
    build_rule_placeholders,
    format_judge_record,
)
from tests.unit.test_business_rules_parser import SYNTHETIC_RULES
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


def rule_ids(text: str) -> list[str]:
    """Return the rule ID at the start of each `- <ID> <text>` line."""
    return [line.split()[1] for line in text.splitlines() if line.startswith("- ")]


def active_ids(rules: list[RuleLine]) -> list[str]:
    """Return the IDs of the active rules, in order."""
    return [rule.rule_id for rule in rules if rule.is_active]


def test_real_prompts_fill_every_placeholder(bundle: ConfigBundle) -> None:
    """Each client prompt builds with its placeholders and keeps no comment or placeholder."""
    values = {
        **build_rule_placeholders(bundle.business_rules),
        "reextraction_section": "",
        "citation_results": "synthetic results",
        "records": "synthetic records",
        "excluded_items": NOTHING_TEXT,
        "record": "synthetic record",
        "candidates": "synthetic candidates",
        "items": "synthetic items",
        "matching_rules": build_matching_rules(bundle.business_rules, []),
        "naming_rules": build_naming_rules(bundle.business_rules),
        "checks": build_checks(bundle.business_rules),
    }
    for template in bundle.prompts.values():
        text = all_text(build_prompt_parts(template, values, [TEXT_CHUNK]))
        assert "<!--" not in text
        assert "{field_section}" not in text and "{chunks}" not in text


def test_rule_lines_have_id_and_text_without_status_or_source(bundle: ConfigBundle) -> None:
    """A rule line is inserted as `- <ID> <text>`: no step tag, status or source."""
    rule = bundle.business_rules.rules_for("Extraction")[0]
    text = build_general_rules(bundle.business_rules)
    assert text.splitlines()[0] == f"- {rule.rule_id} {rule.text}"
    assert f"[{rule.step}]" not in text and f"({rule.status};" not in text


def test_general_rules_are_the_active_extraction_lines(bundle: ConfigBundle) -> None:
    """{general_rules} holds the General rules' [Extraction] lines, not their code steps."""
    general = bundle.business_rules.general.rules
    expected = active_ids([rule for rule in general if rule.step == "Extraction"])
    assert rule_ids(build_general_rules(bundle.business_rules)) == expected


def test_candidate_rules_are_the_candidate_criteria(bundle: ConfigBundle) -> None:
    """{candidate_rules} holds the [Extraction] lines under Candidate criteria only."""
    business = bundle.business_rules.business.rules
    expected = active_ids([rule for rule in business if rule.heading == "Candidate criteria"])
    assert expected
    assert rule_ids(build_candidate_rules(bundle.business_rules)) == expected


def test_field_section_has_one_block_per_extracted_field(bundle: ConfigBundle) -> None:
    """{field_section}: per extracted or generated field, key, column and its [Extraction] lines."""
    rules = bundle.business_rules
    blocks = build_field_section(rules).split("\n\n")
    extracted = rules.extracted_fields()
    assert len(blocks) == len(extracted)
    for block, field in zip(blocks, extracted, strict=True):
        assert block.splitlines()[0].startswith(f"{field.key} ({field.column})")
        assert rule_ids(block) == active_ids(rules.rules_for("Extraction", field.key))


def test_field_section_marks_list_fields(bundle: ConfigBundle) -> None:
    """A multi-value field is marked as a list in its block heading."""
    field = next(field for field in bundle.business_rules.extracted_fields() if field.multi_value)
    assert f"{field.key} ({field.column}) (a list: one entry per value)" in build_field_section(
        bundle.business_rules
    )


def test_context_section_has_one_block_per_context_attribute(bundle: ConfigBundle) -> None:
    """{context_section}: per context attribute, its key and its [Extraction] lines."""
    rules = bundle.business_rules
    blocks = build_context_section(rules).split("\n\n")
    assert [block.splitlines()[0] for block in blocks] == [a.key for a in rules.context]


def test_open_lines_are_never_inserted(bundle: ConfigBundle) -> None:
    """Open rule lines (here: every Matching and Plausibility line) are left out."""
    rules = bundle.business_rules
    matching_keys = [field.key for field in rules.fields if field.matching_allowed]
    assert rules.rules_for("Matching", active_only=False)
    assert rules.rules_for("Plausibility", active_only=False)
    assert build_matching_rules(rules, matching_keys) == NOTHING_TEXT
    assert build_checks(rules) == NOTHING_TEXT


def test_naming_rules_are_every_active_naming_line(bundle: ConfigBundle) -> None:
    """{naming_rules} holds every active [Naming] line; Open ones are left out."""
    rules = bundle.business_rules
    every = rules.rules_for("Naming", active_only=False)
    assert any(not rule.is_active for rule in every)
    assert rule_ids(build_naming_rules(rules)) == active_ids(every)


def test_matching_rules_cover_only_the_fields_in_the_call() -> None:
    """{matching_rules} holds the active [Matching] lines of the fields that have items."""
    amount_line = "- SA-01 [Extraction] The synthetic amount. (Design; synthetic)"
    text = SYNTHETIC_RULES.replace(
        amount_line,
        amount_line
        + "\n- SA-02 [Matching] Match synthetic amounts plainly. (Design; synthetic)"
        + "\n- SA-03 [Matching] An open matching rule. (Open; synthetic)",
    )
    rules = parse_business_rules(text)
    assert build_matching_rules(rules, ["syn_amount"]) == "- SA-02 Match synthetic amounts plainly."
    assert build_matching_rules(rules, ["syn_name"]) == NOTHING_TEXT


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
    rule = bundle.business_rules.record_name_field()
    text = format_judge_record({rule.key: "Syn A", "description": None}, bundle.business_rules)
    assert f"- {rule.column}: Syn A" in text
    assert "(not given)" in text
