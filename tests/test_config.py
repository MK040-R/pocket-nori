"""
tests/test_config.py — Unit tests for URL normalization helpers.
"""

import pytest

from src.config import normalize_origin


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://pocket-nori.vercel.app", "https://pocket-nori.vercel.app"),
        ("https://pocket-nori.vercel.app/", "https://pocket-nori.vercel.app"),
        ("https://pocket-nori.vercel.app/onboarding", "https://pocket-nori.vercel.app"),
        ("http://localhost:3000/", "http://localhost:3000"),
    ],
)
def test_normalize_origin_strips_trailing_slashes_and_paths(value: str, expected: str) -> None:
    assert normalize_origin(value) == expected
