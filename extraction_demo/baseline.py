"""Deterministic regex baseline. It is the floor any candidate extractor has to beat."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .normalize import (
    FINDING_SEP,
    NUMBER_WORDS,
    REVIEWER_SEP,
    is_null_like,
    parse_date,
    parse_int,
    parse_rating,
)

_STYLE_CODE = re.compile(r"\b[A-Z]{2,4}\d{1,2}-\d{2}\b")
_DATE_CANDIDATE = re.compile(
    r"\d{4}[-/]\d{2}[-/]\d{2}"
    r"|\d{1,2}/\d{1,2}/\d{4}"
    r"|\d{1,2}-[A-Za-z]{3}-\d{4}"
    r"|\d{1,2}(?:st|nd|rd|th)? [A-Za-z]{3,9},? \d{4}"
    r"|[A-Za-z]{3,9} \d{1,2}(?:st|nd|rd|th)?, \d{4}"
)
_COUNT = r"(\d+|" + "|".join(NUMBER_WORDS) + r")"
_PARTICIPANT_PATTERNS = (
    re.compile(rf"\b{_COUNT}\s+(?:participants|testers|wearers)\b", re.IGNORECASE),
    re.compile(r"\bn\s*[:=]\s*(\d+)", re.IGNORECASE),
)
_BULLET = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+(.*\S)\s*$")


def extract(text: str) -> Dict[str, Any]:
    rating = parse_rating(text)
    return {
        "product_name": _product_name(text),
        "style_code": _first(_STYLE_CODE, text),
        "test_type": _lower(r"\b(wear|lab)\b", text),
        "test_date": _test_date(text),
        "participants": _participants(text),
        "average_rating": rating[0] if rating else None,
        "rating_scale": rating[1] if rating else None,
        "recommendation": _lower(r"(?:recommendation|verdict)\b[^.\n]*?\b(ship|revise|drop)\b", text),
        "reviewer_names": _reviewers(text),
        "key_findings": _findings(text),
        "notes": _notes(text),
    }


def extract_dir(directory: Path) -> Dict[str, Dict[str, Any]]:
    return {path.stem: extract(path.read_text(encoding="utf-8")) for path in sorted(directory.glob("*.txt"))}


def _first(pattern: "re.Pattern[str]", text: str) -> Optional[str]:
    match = pattern.search(text)
    return match.group(0) if match else None


def _lower(pattern: str, text: str) -> Optional[str]:
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1).lower() if match else None


def _product_name(text: str) -> Optional[str]:
    match = (
        re.search(r"^Product:\s*(.+)$", text, re.MULTILINE)
        or re.search(r"^Shareback memo:\s*(.+?)\s*\(", text, re.MULTILINE)
        or re.search(r"^==\s*(.+?)\s*\|", text, re.MULTILINE)
    )
    return match.group(1).strip() if match else None


def _test_date(text: str) -> Optional[str]:
    for match in _DATE_CANDIDATE.finditer(text):
        parsed = parse_date(match.group(0))
        if parsed:
            return parsed
    return None


def _participants(text: str) -> Optional[int]:
    labelled = re.search(r"^Participants:\s*(.+)$", text, re.MULTILINE | re.IGNORECASE)
    if labelled:
        value = parse_int(labelled.group(1))
        return value if isinstance(value, int) else None
    for pattern in _PARTICIPANT_PATTERNS:
        match = pattern.search(text)
        if match:
            return parse_int(match.group(1))
    return None


def _reviewers(text: str) -> List[str]:
    match = re.search(r"^(?:Reviewers|who):\s*(.+)$", text, re.MULTILINE | re.IGNORECASE) or re.search(
        r"Reviewed by ([^.\n]+)", text
    )
    if not match:
        return []
    return [name.strip() for name in REVIEWER_SEP.split(match.group(1)) if name.strip()]


def _findings(text: str) -> List[str]:
    header = re.search(r"^(?:key findings|key takeaways|findings):?[ \t]*$", text, re.IGNORECASE | re.MULTILINE)
    if not header:
        return []
    findings = []
    for line in text[header.end():].splitlines()[1:]:
        if not line.strip():
            break
        bullet = _BULLET.match(line)
        if bullet:
            findings.extend(part.strip() for part in FINDING_SEP.split(bullet.group(1)) if part.strip())
    return findings[:5]


def _notes(text: str) -> Optional[str]:
    match = re.search(r"^(?:additional notes|notes|comments)\s*:\s*(.*)$", text, re.MULTILINE | re.IGNORECASE)
    if not match or is_null_like(match.group(1).strip().rstrip(".")):
        return None
    return match.group(1).strip()
