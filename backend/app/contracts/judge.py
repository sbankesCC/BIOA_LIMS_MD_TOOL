"""Duplicate judge output (CONTRACTS §3a): one verdict per shortlisted existing Consumable Type."""

from typing import Literal

from app.contracts.base import ContractModel

JudgeVerdict = Literal["same", "different", "unsure"]


class Judgment(ContractModel):
    """The judge's verdict on one candidate, with a one-sentence reason."""

    candidate_id: str
    verdict: JudgeVerdict
    reason: str


class JudgeOutput(ContractModel):
    """The whole duplicate judge response."""

    judgments: list[Judgment]
