"""Conservative scalar parsing: ambiguity stays text, identifiers stay intact."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d.%m.%Y")


def number(value: str) -> Decimal | None:
    """Parse unambiguous dot-decimal, grouped or parenthesized amounts."""
    text = str(value).strip().replace("\u2212", "-").replace("\u00a0", " ")
    text = re.sub(r"^(?:USD|INR|EUR|GBP|Rs\.?|[$£€₹])\s*", "", text, flags=re.I)
    text = re.sub(r"\s*(?:USD|INR|EUR|GBP)$", "", text, flags=re.I)
    percent = text.endswith("%")
    if percent:
        text = text[:-1].strip()
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    if not re.fullmatch(
        r"[+-]?(?:\d+|\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})+,\d{3})(?:\.\d+)?", text
    ):
        return None
    try:
        value = Decimal(text.replace(",", ""))
        return value / 100 if percent else value
    except InvalidOperation:
        return None


def is_identifier(value: str) -> bool:
    """Keep leading zeros and long digit strings losslessly in Excel."""
    text = str(value).strip()
    return bool(re.fullmatch(r"0\d+", text) or re.fullmatch(r"\d{16,}", text))


def date_value(value: str) -> datetime | None:
    """Parse ISO and unambiguous day-first dates; leave ambiguous dates alone."""
    text = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
            if fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y") and parsed.day <= 12:
                return None
            return parsed
        except ValueError:
            continue
    return None


def kind(value: str) -> str:
    """Classify by contents without relying on column labels."""
    if not str(value).strip():
        return "empty"
    if is_identifier(value):
        return "id"
    if date_value(value):
        return "date"
    if number(value) is not None:
        return "currency" if re.search(r"[$£€₹]|USD|INR|EUR|GBP", value) else "numeric"
    return "text"
