"""M8 API tests: roles and offered values, suggestion in the review view, choices, use_suggestion.

The runs use the fake LLM and synthetic documents. Field keys and list values come from the
client config, never written here.
"""

from pathlib import Path
from typing import Any

import pytest

from app.config.bundle import ConfigBundle
from app.config.business_rules import FieldDefinition
from app.llm.fake_client import FakeReply
from app.normalization.lookup_values import ALL_STEPS, find_allowed_values
from tests.fixtures.fake_llm import (
    extraction_reply,
    matching_reply,
    naming_reply,
    verification_reply,
)
from tests.fixtures.make_documents import WORD_FILE
from tests.integration.api_helpers import make_settings, open_api, read_file
from tests.integration.test_graph import NAMES, TWO_ROWS

pytestmark = pytest.mark.usefixtures("blank_environment")

RUN_ID = "run_0001"
UNRESOLVED_TEXT = "synthetic cold room"


def matching_field(bundle: ConfigBundle) -> FieldDefinition:
    """Return a field that allows Matching and has a lookup list."""
    return next(r for r in bundle.business_rules.extracted_fields() if r.matching_allowed)


def reviewer_choice_row(bundle: ConfigBundle) -> tuple[FieldDefinition, str, list[str]]:
    """Return a field with a "Reviewer chooses" translation row, a wording for it, its choices."""
    for rule in bundle.business_rules.fields:
        for table in rule.tables:
            for row in table.active_rows() if table.heading == "Translation table" else []:
                if not row["Lookup value"] or row["Lookup value"].startswith("(blank"):
                    wording = row["Document wording"].split(";")[0].strip()
                    return rule, wording, [c.strip() for c in row["Reviewer chooses"].split(";")]
    raise AssertionError("The config has no Reviewer chooses row.")


def replies(
    bundle: ConfigBundle, found: dict[str, str], matching: FakeReply | None
) -> dict[str, list[FakeReply]]:
    """Return fake replies for two records with these found values."""
    result: dict[str, list[FakeReply]] = {
        "extraction": [extraction_reply(bundle.business_rules, TWO_ROWS, found)],
        "extraction_verification": [verification_reply()],
        "naming": [naming_reply(NAMES)],
    }
    if matching is not None:
        result["matching"] = [matching]
    return result


def cell_of(view: dict[str, Any], record_id: str, key: str) -> dict[str, Any]:
    """Return one cell of the review view."""
    row = next(r for r in view["rows"] if r["record_id"] == record_id)
    return next(c for c in row["cells"] if c["field"] == key)


# ----- /fields -----


def test_fields_give_roles_hide_context_attributes_and_omit_excluded_values(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """Roles are returned; context attributes are not; all-step exclusions are not offered."""
    rules = bundle.business_rules
    with open_api(make_settings(tmp_path), replies(bundle, {}, None)) as api:
        api.start_run([read_file(synthetic_documents, WORD_FILE)])
        fields = api.client.get(f"/runs/{RUN_ID}/fields").json()["fields"]
    by_key = {field["key"]: field for field in fields}
    assert {field["role"] for field in fields} >= {"extracted", "derived", "system"}
    assert not {attribute.key for attribute in rules.context_fields()} & set(by_key)
    # Every list field offers its list minus the values excluded from all steps
    lost = 0
    for rule in rules.fields:
        if rule.lookup_sheet is None:
            continue
        offered = find_allowed_values(rule, rules, bundle.lookup_lists, ALL_STEPS)
        assert by_key[rule.key]["allowed_values"] == offered
        lost += len(bundle.lookup_lists.sheets[rule.lookup_sheet]) - len(offered)
    assert lost > 0


def test_an_excluded_value_cannot_be_chosen_through_the_changes_endpoint(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """A value excluded from every step is rejected like any value not on the list."""
    rules = bundle.business_rules
    rule = next(
        r
        for r in rules.fields
        if r.lookup_sheet
        and r.role == "derived"
        and len(find_allowed_values(r, rules, bundle.lookup_lists, ALL_STEPS))
        < len(bundle.lookup_lists.sheets[r.lookup_sheet])
    )
    assert rule.lookup_sheet is not None
    offered = set(find_allowed_values(rule, rules, bundle.lookup_lists, ALL_STEPS))
    excluded = next(v for v in bundle.lookup_lists.sheets[rule.lookup_sheet] if v not in offered)
    with open_api(make_settings(tmp_path), replies(bundle, {}, None)) as api:
        api.start_run([read_file(synthetic_documents, WORD_FILE)])
        change = {"type": "set_value", "change_id": "chg_0001", "record_id": "rec_0001"}
        change |= {"field": rule.key, "value": excluded, "reason": "synthetic", "bulk_id": None}
        response = api.post_changes(RUN_ID, [change])
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CHANGE_INVALID"


# ----- The review view -----


def test_review_view_returns_the_suggestion_and_use_suggestion_sets_the_value(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """A Matching suggestion shows on the cell; using it sets the value, origin from suggestion."""
    field = matching_field(bundle)
    assert field.lookup_sheet is not None
    choice = bundle.lookup_lists.sheets[field.lookup_sheet][0]
    fake = replies(bundle, {field.key: UNRESOLVED_TEXT}, matching_reply([("m_0001", choice)]))
    with open_api(make_settings(tmp_path), fake) as api:
        api.start_run([read_file(synthetic_documents, WORD_FILE)])
        view = api.client.get(f"/runs/{RUN_ID}/records").json()
        cell = cell_of(view, "rec_0001", field.key)
        assert cell["suggestion"]["value"] == choice
        assert cell["suggestion"]["source"] == "matching"
        assert cell["value"] is None
        use = {"type": "use_suggestion", "change_id": "chg_0001", "record_id": "rec_0001"}
        assert api.post_changes(RUN_ID, [use | {"field": field.key}]).status_code == 200
        assert api.client.post(f"/runs/{RUN_ID}/recheck").status_code == 200
        after = cell_of(api.client.get(f"/runs/{RUN_ID}/records").json(), "rec_0001", field.key)
    assert (after["value"], after["origin"]) == (choice, "from_suggestion")


def test_review_view_says_why_there_is_no_suggestion(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """When Matching answers null, the cell has no suggestion and carries the model's reason."""
    field = matching_field(bundle)
    fake = replies(bundle, {field.key: UNRESOLVED_TEXT}, matching_reply([("m_0001", None)]))
    with open_api(make_settings(tmp_path), fake) as api:
        api.start_run([read_file(synthetic_documents, WORD_FILE)])
        cell = cell_of(api.client.get(f"/runs/{RUN_ID}/records").json(), "rec_0001", field.key)
    assert cell["suggestion"] is None
    assert cell["no_suggestion_reason"] == "synthetic reason"


def test_issue_summary_returns_the_choices_of_a_reviewer_choice_issue(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """A "Reviewer chooses" issue lists the values to choose from."""
    field, wording, choices = reviewer_choice_row(bundle)
    fake = replies(bundle, {field.key: wording}, None)
    with open_api(make_settings(tmp_path), fake) as api:
        api.start_run([read_file(synthetic_documents, WORD_FILE)])
        cell = cell_of(api.client.get(f"/runs/{RUN_ID}/records").json(), "rec_0001", field.key)
    [issue] = [i for i in cell["issues"] if i["code"] == "REVIEWER_CHOICE_NEEDED"]
    assert issue["choices"] == choices
    assert issue["individual_review"] is True


# ----- The run -----


def test_run_returns_the_new_models_and_versions(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """The run detail names every model (the three new steps too) and the new file versions."""
    with open_api(make_settings(tmp_path), replies(bundle, {}, None)) as api:
        api.start_run([read_file(synthetic_documents, WORD_FILE)])
        run = api.client.get(f"/runs/{RUN_ID}").json()
    assert set(run["models"]) == {
        "extraction",
        "extraction_verification",
        "matching",
        "naming",
        "plausibility",
        "duplicate_judge",
    }
    versions = run["config_versions"]
    assert versions["extraction_rules"] == bundle.extraction_rules.version
    assert versions["export_template"] == bundle.export_template.version
    assert versions["business_rules"] == bundle.business_rules.version
    assert run["current_step"] is None
