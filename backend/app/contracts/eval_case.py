"""Eval case (CONTRACTS §9): the `case.yaml` file that describes one eval case folder."""

from typing import Literal

from app.contracts.base import ContractModel

CaseSource = Literal["synthetic", "bioa"]


class EvalCaseInfo(ContractModel):
    """One eval case: where its documents come from, who labeled it, and against which rules."""

    id: str
    description: str
    source: CaseSource
    tags: list[str] = []
    labeled_by: str
    labeled_on: str
    field_rules_version: str
