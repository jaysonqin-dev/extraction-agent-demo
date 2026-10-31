"""Canonicalisation applied to both golden and candidate values before they are compared.

Normalisation absorbs formatting differences (case, spacing, date style, "4,5 out of 5")
so that the parity report can separate cosmetic variation from real extraction errors.
It never converts between rating scales: 8.4 on a 10-point scale stays 8.4.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

NULL_LIKES = {"", "n/a", "na", "none", "null", "nil", "-", "--"}

NUMBER_WORDS = {
    word: index
    for index, word in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen "
        "fourteen fifteen sixteen seventeen eighteen nineteen twenty".split()
    )
}

REVIEWER_SEP = re.compile(r",|;|&|\band\b", re.IGNORECASE)
FINDING_SEP = re.compile(r";|\n")

_NUMBER_TOKEN = re.compile(r"\b(\d+|" + "|".join(NUMBER_WORDS) + r")\b")
_DECIMAL = r"\d+(?:[.,]\d+)?"
# The lookarounds keep a date such as 05/19/2025 from being read as a rating of 5 out of 19.
_RATING_WITH_SCALE = re.compile(rf"(?<![\d/])({_DECIMAL})\s*(?:/|out of)\s*({_DECIMAL})(?![\d/])", re.IGNORECASE)
_PLAIN_DECIMAL = re.compile(rf"\s*({_DECIMAL})\s*")
_ORDINAL = re.compile(r"(?<=\d)(?:st|nd|rd|th)\b", re.IGNORECASE)
_BULLET = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+")

# Month-first is tried before day-first, so "03/04/2025" reads as 4 March. Documented in docs/design.md.
_DATE_FORMATS = (
    "%Y-%m-%d", "%Y/%m/%d", "%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y",
    "%d-%b-%Y", "%m/%d/%Y", "%d/%m/%Y",
)


def collapse(text: str) -> str:
    return " ".join(text.split())


def is_null_like(value: Any) -> bool:
    return value is None or (isinstance(value, str) and collapse(value).casefold() in NULL_LIKES)


def normalize_text(value: Any) -> Any:
    if is_null_like(value):
        return None
    return collapse(value).casefold() if isinstance(value, str) else value


def normalize_upper(value: Any) -> Any:
    if is_null_like(value):
        return None
    return collapse(value).upper() if isinstance(value, str) else value


def parse_int(value: Any) -> Any:
    """Return an int when the value holds exactly one count; otherwise return the text unchanged."""
    if is_null_like(value):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        tokens = _NUMBER_TOKEN.findall(value.casefold())
        if len(tokens) == 1:
            token = tokens[0]
            return int(token) if token.isdigit() else NUMBER_WORDS[token]
        return collapse(value)
    return value


def parse_rating(text: str) -> Optional[Tuple[float, Optional[int]]]:
    """Find a rating in free text. Returns (value, scale) where scale may be None."""
    match = _RATING_WITH_SCALE.search(text)
    if match:
        return _to_float(match.group(1)), int(_to_float(match.group(2)))
    match = _PLAIN_DECIMAL.fullmatch(text)
    if match:
        return _to_float(match.group(1)), None
    return None


def normalize_rating(value: Any) -> Any:
    if is_null_like(value):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    if isinstance(value, str):
        parsed = parse_rating(value)
        return round(parsed[0], 2) if parsed else collapse(value)
    return value


def parse_date(text: str) -> Optional[str]:
    cleaned = _ORDINAL.sub("", collapse(text)).replace(",", "")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def normalize_date(value: Any) -> Any:
    if is_null_like(value):
        return None
    if isinstance(value, str):
        return parse_date(value) or collapse(value)
    return value


def normalize_list(value: Any, separator: "re.Pattern[str]") -> Any:
    """Lists compare as order-insensitive collections; a bare string is split into items."""
    if is_null_like(value):
        return None
    if isinstance(value, str):
        items: List[Any] = separator.split(value)
    elif isinstance(value, list):
        items = value
    else:
        return value
    cleaned = []
    for item in items:
        if isinstance(item, str):
            item = _BULLET.sub("", item)
        item = normalize_text(item)
        if item is not None:
            cleaned.append(item)
    return sorted(cleaned, key=str)


def normalize_generic(value: Any) -> Any:
    if isinstance(value, str):
        return normalize_text(value)
    if isinstance(value, list):
        return [normalize_generic(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize_generic(item) for key, item in value.items()}
    return value


NORMALIZERS: Dict[str, Callable[[Any], Any]] = {
    "product_name": normalize_text,
    "style_code": normalize_upper,
    "test_type": normalize_text,
    "test_date": normalize_date,
    "participants": parse_int,
    "average_rating": normalize_rating,
    "rating_scale": parse_int,
    "recommendation": normalize_text,
    "reviewer_names": lambda v: normalize_list(v, REVIEWER_SEP),
    "key_findings": lambda v: normalize_list(v, FINDING_SEP),
    "notes": normalize_text,
}


def normalize_value(field: str, value: Any) -> Any:
    return NORMALIZERS.get(field, normalize_generic)(value)


def normalize_record(record: Dict[str, Any]) -> Dict[str, Any]:
    return {field: normalize_value(field, value) for field, value in record.items()}


def _to_float(text: str) -> float:
    return float(text.replace(",", "."))
