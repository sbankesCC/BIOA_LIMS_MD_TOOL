"""API test: duplicate issues show existing types' attributes from the run's pinned reference data.

A run keeps the reference data version current at its start; a later version does not change
what its re-check shows. Every document, reply and value is synthetic.
"""

import csv
from io import StringIO
from pathlib import Path
from typing import Any

import pytest

from app.config.bundle import ConfigBundle
from app.llm.fake_client import FakeReply
from app.validation import codes
from tests.fixtures.fake_llm import extraction_reply, verification_reply
from tests.fixtures.make_documents import REAGENT_TABLE, WORD_FILE
from tests.integration.api_helpers import ApiHarness, make_settings, open_api, read_file

RUN_ID = "run_0001"

# The synthetic table row extracted as the run's only record, and its name
RECORD_ROW = 1
RECORD_NAME = REAGENT_TABLE[RECORD_ROW][0]

# Synthetic attributes of the existing type in each reference data version
FIRST_DESCRIPTION = "Synthetic description, first version"
SECOND_DESCRIPTION = "Synthetic description, second version"
CLASS = "Synthetic class"
ACTIVE = "Y"

pytestmark = pytest.mark.usefixtures("blank_environment")


def make_reference_csv(bundle: ConfigBundle, description: str) -> bytes:
    """Return a synthetic existing-types CSV naming the record, with every mapped column."""
    columns = bundle.reference_mapping.columns
    header = [columns.name, columns.version, columns.description]
    header += [columns.consumable_class, columns.active_flag]
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerow([RECORD_NAME, "1", description, CLASS, ACTIVE])
    return buffer.getvalue().encode("utf-8")


def apply_reference(api: ApiHarness, bundle: ConfigBundle, description: str) -> None:
    """Upload a reference data version and make it current."""
    upload = ("synthetic existing.csv", make_reference_csv(bundle, description), "text/csv")
    response = api.client.post("/admin/reference-data", files={"file": upload})
    assert response.status_code == 200, response.text
    upload_id = response.json()["version"]["upload_id"]
    applied = api.client.post(f"/admin/reference-data/{upload_id}/apply")
    assert applied.status_code == 200, applied.text


def one_record_replies(bundle: ConfigBundle) -> dict[str, list[FakeReply]]:
    """Return fake replies for a run with one record and nothing else to report."""
    return {
        "extraction": [extraction_reply(bundle.field_rules, [("R1", RECORD_ROW)])],
        "extraction_verification": [verification_reply()],
    }


def find_candidates(view: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the duplicate candidates of the run's EXISTS_IN_LABVANTAGE issue."""
    for row in view["rows"]:
        for cell in row["cells"]:
            for issue in cell["issues"]:
                if issue["code"] == codes.EXISTS_IN_LABVANTAGE:
                    return issue["duplicate_candidates"]
    raise AssertionError("The synthetic run has no EXISTS_IN_LABVANTAGE issue.")


def test_candidates_show_attributes_from_the_pinned_reference_version(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """The review view shows the run's version's attributes, even after a newer version."""
    with open_api(make_settings(tmp_path), one_record_replies(bundle)) as api:
        apply_reference(api, bundle, FIRST_DESCRIPTION)
        response = api.start_run([read_file(synthetic_documents, WORD_FILE)])
        assert response.status_code == 202, response.text
        [candidate] = find_candidates(api.client.get(f"/runs/{RUN_ID}/records").json())
        assert candidate["name"] == RECORD_NAME
        assert candidate["match"] == "exact"
        assert (candidate["description"], candidate["consumable_class"]) == (
            FIRST_DESCRIPTION,
            CLASS,
        )
        assert candidate["active_flag"] == ACTIVE
        # A newer reference data version applies to new runs only
        apply_reference(api, bundle, SECOND_DESCRIPTION)
        assert api.client.post(f"/runs/{RUN_ID}/recheck").status_code == 200
        [rechecked] = find_candidates(api.client.get(f"/runs/{RUN_ID}/records").json())
        assert rechecked["description"] == FIRST_DESCRIPTION
