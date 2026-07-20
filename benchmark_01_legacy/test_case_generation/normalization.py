"""Text normalization helpers for generated commercial-name cases.

Problem: generated cases must use the same broad normalization assumptions as
the app/evaluator while preserving user-facing noisy inputs.
Inputs: arbitrary catalog strings, including Latin, Arabic, numbers, symbols,
and missing values.
Outputs: normalized spaced strings, compact keys, and safe lower-case query
strings for CSV output.
Edge cases: None values, punctuation-only values, Arabic digits, Arabic letter
variants, repeated spaces, and one-character tokens.
Failure modes: empty inputs raise ValueError in strict helpers; returning an
empty generated query would create invalid evaluation rows.
Algorithm choice: regex-based normalization is used instead of locale-specific
tokenizers because commercial names mix Latin, Arabic, digits, and punctuation;
the evaluator already uses a compatible regex pipeline.
"""

from __future__ import annotations

import re


ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
ARABIC_LETTERS = str.maketrans({
    "آ": "ا",
    "أ": "ا",
    "إ": "ا",
    "ٱ": "ا",
    "ى": "ي",
    "ئ": "ي",
    "ؤ": "و",
    "ة": "ه",
})
DIACRITICS_PATTERN = re.compile(r"[\u064b-\u065f\u0670\u0640]")
NON_SEARCH_CHARS_PATTERN = re.compile(r"[^0-9A-Z\u0600-\u06ff]+")
NON_COMPACT_CHARS_PATTERN = re.compile(r"[^0-9A-Z\u0600-\u06ff]+")
SPACE_PATTERN = re.compile(r"\s+")


def normalize_search(value: object) -> str:
    """Normalize a value for matching and generation.

    Args:
        value: Any catalog or generated value.

    Returns:
        Uppercase normalized text with punctuation collapsed to spaces.
    """

    if value is None:
        return ""
    text = str(value).translate(ARABIC_DIGITS).translate(ARABIC_LETTERS)
    text = DIACRITICS_PATTERN.sub("", text)
    text = NON_SEARCH_CHARS_PATTERN.sub(" ", text.upper())
    return SPACE_PATTERN.sub(" ", text).strip()


def compact_key(value: object) -> str:
    """Return the punctuation-free key used for collision checks.

    Args:
        value: Any catalog or generated value.

    Returns:
        Compact uppercase key containing only letters and numbers.
    """

    return NON_COMPACT_CHARS_PATTERN.sub("", normalize_search(value))


def lower_query(value: object) -> str:
    """Convert a generated value into a deterministic user-facing query.

    Args:
        value: Generated query value.

    Returns:
        Lower-case query text with normalized internal spacing.

    Raises:
        ValueError: If the value normalizes to an empty string.
    """

    normalized = normalize_search(value)
    if not normalized:
        raise ValueError("generated query normalized to empty text")
    return normalized.lower()


def latin_tokens(value: object) -> list[str]:
    """Return useful Latin-style tokens from a normalized value.

    Args:
        value: Catalog text.

    Returns:
        Tokens with one-character fragments removed.
    """

    return [token for token in normalize_search(value).split() if len(token) > 1]


def require_compact(value: object, label: str) -> str:
    """Return a compact key or raise a descriptive validation error.

    Args:
        value: Source value to normalize.
        label: Human-readable label used in error messages.

    Returns:
        Non-empty compact key.

    Raises:
        ValueError: If the compact key is empty.
    """

    compact = compact_key(value)
    if not compact:
        raise ValueError(f"{label} has no searchable compact key")
    return compact


def has_arabic(value: object) -> bool:
    """Return whether a value contains Arabic letters.

    Args:
        value: Text to inspect.

    Returns:
        True when at least one Arabic codepoint remains after normalization.
    """

    return bool(re.search(r"[\u0600-\u06ff]", normalize_search(value)))

