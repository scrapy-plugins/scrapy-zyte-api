from __future__ import annotations


def str_to_bool(value: str) -> bool:
    """Interpret a string as a boolean the way Zyte API proxy mode headers do:
    any value other than an empty string or ``"false"`` (case-insensitive,
    surrounding whitespace ignored) is ``True``."""
    return value.strip().lower() not in ("", "false")
