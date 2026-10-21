"""Conservative semantic column inference from headers and observed values.

The inferred role is evidence for validation and routing.  It is never used to
rewrite a value.  Low-signal columns deliberately remain ``text``.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from .models import Table
from .values import date_value, is_identifier, number


@dataclass(frozen=True)
class ColumnSemantic:
    """A column role with an auditable confidence and short evidence summary."""

    role: str
    confidence: float
    evidence: str
    header_signal: bool = False


HEADER_PATTERNS = {
    "phone": re.compile(
        r"\b(?:phone|mobile|telephone|tel|contact\s*(?:no|number)?)\b",
        re.I,
    ),
    "date": re.compile(
        r"\b(?:date|dated|period|posting\s+date|transaction\s+date)\b",
        re.I,
    ),
    "balance": re.compile(
        r"\b(?:balance|closing|opening|running\s+balance)\b",
        re.I,
    ),
    "total": re.compile(r"\b(?:total|subtotal|grand\s+total|net\s+total)\b", re.I),
    "amount": re.compile(
        r"\b(?:amount|amt|price|cost|value|debit|credit|charge|payment|rate)\b",
        re.I,
    ),
    "quantity": re.compile(
        r"\b(?:quantity|qty|units|count|pieces?|nos?)\b",
        re.I,
    ),
    "id": re.compile(
        r"(?:^|\b)(?:id|identifier|code|reference|ref|serial|(?:s|sl)\s*\.?\s*no|account\s*(?:no|number)|invoice\s*(?:no|number)|order\s*(?:no|number))(?:\b|$)",
        re.I,
    ),
}
UNICODE_HEADER_TERMS = {
    "phone": ("फ़ोन", "फोन", "मोबाइल", "ఫోన్", "మొబైల్"),
    "date": ("दिनांक", "तारीख", "తేదీ"),
    "balance": ("शेष", "बकाया", "బ్యాలెన్స్", "నిల్వ"),
    "total": ("कुल", "योग", "మొత్తం"),
    "amount": ("राशि", "रकम", "విలువ", "రాశి"),
    "quantity": ("मात्रा", "संख्या", "పరిమాణం", "సంఖ్య"),
    "id": ("आईडी", "पहचान", "क्रमांक", "ఐడి", "గుర్తింపు", "కోడ్", "క్రమ సంఖ్య"),
}


def normalized_header(value: str) -> str:
    """Return a comparison form while retaining every original header elsewhere."""
    characters = []
    for character in str(value).casefold():
        category = unicodedata.category(character)
        characters.append(character if character.isalnum() or category.startswith("M") else " ")
    return re.sub(r"\s+", " ", "".join(characters)).strip()


def phone_like(value: str) -> bool:
    """Recognise plausible phone strings without treating arbitrary amounts as phones."""
    text = str(value).strip()
    text = re.sub(r"(?:ext\.?|x)\s*\d+$", "", text, flags=re.I).strip()
    if not text or re.search(r"[A-Za-z]", text):
        return False
    if not re.fullmatch(r"\+?[\d\s().-]+", text):
        return False
    digits = re.sub(r"\D", "", text)
    return 7 <= len(digits) <= 15


def date_like(value: str) -> bool:
    """Include ambiguous numeric dates that value parsing intentionally leaves as text."""
    text = str(value).strip()
    return date_value(text) is not None or bool(
        re.fullmatch(r"\d{1,4}([-/\.])\d{1,2}\1\d{2,4}", text)
    )


def id_like(value: str) -> bool:
    """Recognise loss-sensitive identifiers, including stable alphanumeric codes."""
    text = str(value).strip()
    return is_identifier(text) or bool(
        re.fullmatch(r"(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9][A-Za-z0-9._/-]{2,}", text)
    )


def value_matches(role: str, value: str) -> bool | None:
    """Return whether a nonempty value is structurally compatible with a role."""
    text = str(value).strip()
    if not text:
        return None
    if role == "phone":
        return phone_like(text)
    if role == "date":
        return date_like(text)
    if role == "id":
        return id_like(text) or bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", text))
    if role in {"amount", "quantity", "total", "balance"}:
        return number(text) is not None
    return True


def _header_role(header: str) -> str | None:
    text = normalized_header(header)
    # Specific financial roles must win over the generic amount vocabulary.
    for role in ("phone", "date", "balance", "total", "quantity", "id", "amount"):
        if any(term in text for term in UNICODE_HEADER_TERMS[role]) or HEADER_PATTERNS[role].search(
            text
        ):
            return role
    return None


def infer_column_semantics(table: Table) -> list[ColumnSemantic]:
    """Infer phone/date/id/financial roles from header and recurring data signals."""
    output: list[ColumnSemantic] = []
    for column, header in enumerate(table.headers):
        values = [
            row[column].strip() for row in table.rows if column < len(row) and row[column].strip()
        ]
        role = _header_role(header)
        # Singular "Unit" often means an organisational unit ("Unit 1"),
        # while Qty/Quantity and plural Units are unambiguous. Treat singular
        # Unit as quantity only when this document supplies numeric evidence.
        if role is None and normalized_header(header) == "unit" and values:
            numeric = sum(number(value) is not None for value in values)
            if numeric / len(values) >= 0.75:
                role = "quantity"
        if role:
            matching = sum(value_matches(role, value) is True for value in values)
            ratio = matching / len(values) if values else 0.0
            output.append(
                ColumnSemantic(
                    role,
                    0.97 if not values or ratio >= 0.6 else 0.84,
                    f"header={header!r}; {matching}/{len(values)} populated values match",
                    True,
                )
            )
            continue

        if not values:
            output.append(ColumnSemantic("text", 0.25, "no populated values"))
            continue
        counts = Counter()
        for value in values:
            counts["phone"] += phone_like(value)
            counts["date"] += date_like(value)
            counts["id"] += id_like(value)
            counts["numeric"] += number(value) is not None
            counts["currency"] += bool(
                re.search(r"(?:[$£€₹]|\b(?:USD|INR|EUR|GBP|Rs\.?)\b)", value, re.I)
            )
        total = len(values)
        integers = [int(value) for value in values if re.fullmatch(r"\d+", value)]
        sequential = (
            column == 0
            and len(integers) == total
            and total >= 5
            and sum(current - previous == 1 for previous, current in zip(integers, integers[1:]))
            / (total - 1)
            >= 0.8
        )
        if total >= 3 and counts["date"] / total >= 0.75:
            output.append(
                ColumnSemantic("date", 0.78, f"{counts['date']}/{total} date-like values")
            )
        elif total >= 3 and counts["id"] / total >= 0.75:
            output.append(
                ColumnSemantic("id", 0.76, f"{counts['id']}/{total} identifier-like values")
            )
        elif sequential:
            output.append(
                ColumnSemantic("id", 0.86, f"{total} integer values form a sequential record key")
            )
        elif (
            total >= 3
            and counts["phone"] / total >= 0.8
            and any(re.search(r"[+() -]", value) for value in values)
        ):
            output.append(
                ColumnSemantic("phone", 0.72, f"{counts['phone']}/{total} phone-like values")
            )
        elif counts["currency"] / total >= 0.6:
            output.append(
                ColumnSemantic(
                    "amount", 0.75, f"{counts['currency']}/{total} currency-marked values"
                )
            )
        elif counts["numeric"] / total >= 0.85:
            output.append(
                ColumnSemantic("quantity", 0.55, f"{counts['numeric']}/{total} numeric values")
            )
        else:
            output.append(ColumnSemantic("text", 0.65, "mixed or textual values"))
    return output


def semantic_roles(table: Table) -> list[str]:
    """Compact role list used by stitching compatibility checks."""
    return [column.role for column in infer_column_semantics(table)]
