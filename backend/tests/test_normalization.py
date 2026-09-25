"""Unit tests for text normalization."""

from __future__ import annotations

import pytest

from app.schemas.metrics import NormalizationOptions
from app.services.normalization import (
    normalize_for_diff,
    normalize_text,
    tokenize,
    unify_typography,
)


def test_lowercase_and_whitespace_collapse() -> None:
    result = normalize_text("  Привет   МИР\n\n  тест  ")
    assert result == "привет мир тест"


def test_typographic_quotes_and_dashes_are_unified() -> None:
    raw = "«Договор» — «Акт» – “Итог” ‛x‛"
    normalized = normalize_text(raw)
    assert normalized == '"договор" - "акт" - "итог" \'x\''


def test_non_breaking_spaces_and_zero_width_are_removed() -> None:
    raw = "Итого\u00a0сумма\u200b:\u202f100"
    assert normalize_text(raw) == "итого сумма: 100"


def test_hyphenated_line_break_is_joined() -> None:
    assert normalize_text("ис-\nполнение") == "исполнение"


def test_numeric_ranges_are_not_joined_across_lines() -> None:
    # only letters are joined, so a line-broken range keeps its hyphen
    assert normalize_text("5-\n10") == "5- 10"


def test_punctuation_removal_is_optional() -> None:
    raw = "Цена: 1 200,50 руб."
    with_punct = normalize_text(raw, NormalizationOptions())
    without_punct = normalize_text(
        raw, NormalizationOptions(remove_punctuation=True)
    )
    assert with_punct == "цена: 1 200,50 руб."
    assert ":" not in without_punct
    assert "." not in without_punct
    assert "цена" in without_punct


def test_lowercase_can_be_disabled() -> None:
    options = NormalizationOptions(lowercase=False)
    assert normalize_text("Привет Мир", options) == "Привет Мир"


def test_diacritics_stripping() -> None:
    options = NormalizationOptions(strip_diacritics=True)
    assert normalize_text("Café Zürich", options) == "cafe zurich"


def test_none_and_empty_are_safe() -> None:
    assert normalize_text(None) == ""
    assert normalize_text("") == ""
    assert tokenize("") == []


def test_tokenize_splits_on_whitespace() -> None:
    assert tokenize("a b  c\nd") == ["a", "b", "c", "d"]


def test_unify_typography_handles_ligatures() -> None:
    # "o" + U+FB01 (fi ligature) + "ce"
    assert unify_typography("o\ufb01ce") == "ofice"
    # ff + fi + fl
    assert unify_typography("\ufb00\ufb01\ufb02") == "fffifl"


@pytest.mark.parametrize(
    "raw",
    [
        "Минус\u22125 градусов",
        "Тире \u2014 здесь",
        "Дефис \u2010 тут",
    ],
)
def test_dash_variants_become_ascii_hyphen(raw: str) -> None:
    assert "\u2014" not in normalize_text(raw)
    assert "\u2212" not in normalize_text(raw)
    assert "\u2010" not in normalize_text(raw)


def test_normalize_for_diff_keeps_line_breaks() -> None:
    result = normalize_for_diff("Первая строка\n\nТретья строка")
    assert result == "первая строка\nтретья строка"
