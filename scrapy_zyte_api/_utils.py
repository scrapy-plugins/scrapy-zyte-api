from __future__ import annotations


def str_to_bool(value: str) -> bool:
    """Interpret a string as a boolean the way Zyte API proxy mode does."""
    return value.strip().lower() in ("true", "1")
