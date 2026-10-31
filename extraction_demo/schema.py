"""A small JSON-schema subset validator that returns structured errors instead of raising.

Supported keywords: type, nullable, required, properties, additionalProperties (false),
enum, minimum, maximum, minLength, pattern, format ("date"), items, minItems, maxItems.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema" / "shareback.schema.json"

_TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
}


@dataclass(frozen=True)
class SchemaError:
    path: str
    code: str
    message: str

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


def load_schema(path: Path = SCHEMA_PATH) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def validate(instance: Any, schema: Dict[str, Any], path: str = "$") -> List[SchemaError]:
    if instance is None:
        if schema.get("nullable"):
            return []
        return [SchemaError(path, "null_not_allowed", "value must not be null")]

    expected = schema.get("type")
    if expected and not _TYPE_CHECKS[expected](instance):
        return [SchemaError(path, "type", f"expected {expected}, got {type(instance).__name__}")]

    errors: List[SchemaError] = []
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(SchemaError(path, "enum", f"{instance!r} is not one of {schema['enum']}"))

    if isinstance(instance, str):
        errors.extend(_check_string(instance, schema, path))
    elif isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(SchemaError(path, "minimum", f"{instance} is below {schema['minimum']}"))
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(SchemaError(path, "maximum", f"{instance} is above {schema['maximum']}"))
    elif isinstance(instance, list):
        errors.extend(_check_array(instance, schema, path))
    elif isinstance(instance, dict):
        errors.extend(_check_object(instance, schema, path))
    return errors


def _check_string(value: str, schema: Dict[str, Any], path: str) -> List[SchemaError]:
    errors = []
    if len(value) < schema.get("minLength", 0):
        errors.append(SchemaError(path, "minLength", f"shorter than {schema['minLength']}"))
    if "pattern" in schema and not re.search(schema["pattern"], value):
        errors.append(SchemaError(path, "pattern", f"{value!r} does not match {schema['pattern']}"))
    if schema.get("format") == "date" and not _is_iso_date(value):
        errors.append(SchemaError(path, "format", f"{value!r} is not an ISO date (YYYY-MM-DD)"))
    return errors


def _check_array(items: List[Any], schema: Dict[str, Any], path: str) -> List[SchemaError]:
    errors = []
    if "minItems" in schema and len(items) < schema["minItems"]:
        errors.append(SchemaError(path, "minItems", f"fewer than {schema['minItems']} items"))
    if "maxItems" in schema and len(items) > schema["maxItems"]:
        errors.append(SchemaError(path, "maxItems", f"more than {schema['maxItems']} items"))
    if "items" in schema:
        for index, item in enumerate(items):
            errors.extend(validate(item, schema["items"], f"{path}[{index}]"))
    return errors


def _check_object(obj: Dict[str, Any], schema: Dict[str, Any], path: str) -> List[SchemaError]:
    errors = []
    properties = schema.get("properties", {})
    for key in schema.get("required", []):
        if key not in obj:
            errors.append(SchemaError(f"{path}.{key}", "required", "required property is missing"))
    for key, value in obj.items():
        if key in properties:
            errors.extend(validate(value, properties[key], f"{path}.{key}"))
        elif schema.get("additionalProperties") is False:
            errors.append(SchemaError(f"{path}.{key}", "additional_property", "property is not in the schema"))
    return errors


def _is_iso_date(value: str) -> bool:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True
