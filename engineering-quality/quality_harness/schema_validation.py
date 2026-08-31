from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def validate_receipt_schema(payload: Mapping[str, Any], schema_path: Path) -> None:
    """Fail closed when a candidate/release receipt violates its tracked schema."""
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError as exc:  # pragma: no cover - harness dependency contract
        raise RuntimeError(
            "jsonschema is required to validate release receipts"
        ) from exc
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(
            payload
        ),
        key=lambda item: list(item.absolute_path),
    )
    if not errors:
        return
    rendered = []
    for error in errors[:12]:
        location = "/".join(str(part) for part in error.absolute_path) or "<root>"
        rendered.append(f"{location}: {error.message}")
    raise RuntimeError("receipt failed JSON Schema validation: " + "; ".join(rendered))
