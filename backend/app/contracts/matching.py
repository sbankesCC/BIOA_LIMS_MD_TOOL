"""Matching (CONTRACTS §3b): request items built by code and the model's answers.

One call per run with every unresolved lookup value. An answer is only a suggestion: code
rejects a choice that is not on the item's shortlist, and never sets the value.
"""

from app.contracts.base import ContractModel


class MatchingItem(ContractModel):
    """One unresolved lookup value: its field's column name, the value, its quote and shortlist."""

    item_id: str
    field: str
    value: str
    quote: str
    shortlist: list[str]


class MatchingAnswer(ContractModel):
    """The model's answer for one item: a shortlist value copied exactly, or null, and why."""

    item_id: str
    choice: str | None
    reason: str


class MatchingOutput(ContractModel):
    """The whole Matching response: one answer per item."""

    answers: list[MatchingAnswer]
