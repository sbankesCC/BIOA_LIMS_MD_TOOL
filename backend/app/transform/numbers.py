"""Numbers from text, for decimal and integer fields ("1e4 cps/uL" gives "10000").

A value that is already a plain number stays as it is. Text holding exactly one number gives that
number with NUMBER_READ_FROM_TEXT. Anything else is kept as written; validation flags WRONG_TYPE.
"""

import re
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel

from app.transform.notes import TransformNote

# A plain number: optional sign, digits, optional decimal part (what the loader accepts as is)
PLAIN_NUMBER = re.compile(r"[-+]?\d+(\.\d+)?")

# A number without sign: digits (thousands commas allowed) with an optional decimal part,
# or a decimal part alone (".5")
UNSIGNED_NUMBER = r"(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)"

# A number inside text, with an optional exponent ("1e4"). A sign only counts at the start or
# after a space, so the range "-2-8" reads as "-2" and "8", never as "-2" and "-8".
NUMBER_IN_TEXT = re.compile(rf"(?:(?:^|(?<=\s))[-+])?{UNSIGNED_NUMBER}(?:[eE][-+]?\d+)?")


class NumberResult(BaseModel):
    """The output value of a number field and the note for validation, if any."""

    value: str
    note: TransformNote | None = None


def read_number(value: str) -> NumberResult:
    """Return a plain number as is, the one number found in text, or the text unchanged."""
    if PLAIN_NUMBER.fullmatch(value):
        return NumberResult(value=value)
    number = find_single_number(value)
    # No number, or several (a range, "1 x 10^4"): keep it as written for validation
    if number is None:
        return NumberResult(value=value)
    note = TransformNote(code="NUMBER_READ_FROM_TEXT", original=value, value=number)
    return NumberResult(value=number, note=note)


def find_single_number(text: str) -> str | None:
    """Return the only number in the text as plain digits, or None if there is not exactly one."""
    tokens = NUMBER_IN_TEXT.findall(text)
    if len(tokens) != 1:
        return None
    return format_plain_number(tokens[0])


def format_plain_number(token: str) -> str | None:
    """Write a number token as plain digits: no thousands commas, no exponent."""
    try:
        number = Decimal(token.replace(",", ""))
    except InvalidOperation:
        return None
    return format(number, "f")
