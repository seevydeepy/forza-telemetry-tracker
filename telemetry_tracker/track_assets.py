"""Validation helpers for local track-map artwork assets."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Mapping

ALLOWED_MIME_TYPES = {"image/png", "image/jpeg", "image/webp", "image/svg+xml"}
MAX_ASSET_BYTES = 5 * 1024 * 1024
TRANSFORM_KEYS = ("scale", "rotate_deg", "translate_x", "translate_y")


def validate_asset(filename: str, mime_type: str, size_bytes: int) -> None:
    """Validate metadata for a locally copied track asset."""

    clean_name = Path(str(filename or "")).name.strip()
    if not clean_name:
        raise ValueError("filename is required")
    if clean_name != str(filename or "").strip():
        raise ValueError("filename must not include path components")
    if mime_type not in ALLOWED_MIME_TYPES:
        supported = ", ".join(sorted(ALLOWED_MIME_TYPES))
        raise ValueError(f"unsupported MIME type: {mime_type}; expected one of {supported}")
    try:
        size = int(size_bytes)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("size_bytes must be an integer") from exc
    if size < 0:
        raise ValueError("size_bytes must be non-negative")
    if size > MAX_ASSET_BYTES:
        raise ValueError(f"asset exceeds maximum size of {MAX_ASSET_BYTES} bytes")


def default_transform() -> dict:
    return {
        "scale": 1.0,
        "rotate_deg": 0.0,
        "translate_x": 0.0,
        "translate_y": 0.0,
    }


def validate_transform(transform: Mapping[str, object] | None) -> dict:
    """Return a normalized asset transform or raise ValueError."""

    if transform is None:
        return default_transform()
    if not isinstance(transform, Mapping):
        raise ValueError("transform must be an object")

    normalized: dict[str, float] = {}
    for key in TRANSFORM_KEYS:
        if key not in transform:
            raise ValueError(f"transform.{key} is required")
        try:
            value = float(transform[key])
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"transform.{key} must be a finite number") from exc
        if not math.isfinite(value):
            raise ValueError(f"transform.{key} must be a finite number")
        normalized[key] = value

    if normalized["scale"] <= 0:
        raise ValueError("transform.scale must be greater than zero")
    return normalized
