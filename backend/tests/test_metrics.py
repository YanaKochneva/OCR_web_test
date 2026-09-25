"""Unit tests for CER / WER / exact success / diff / per-page comparison."""

from __future__ import annotations

import math

import pytest

from app.schemas.document import DocumentSource, DocumentType
from app.schemas.metrics import DiffOp, NormalizationOptions, PageStatus
from app.services.metrics import (
    build_diff,
    compare_pages,
    compare_tables,
    compute_metrics,
    compute_pair_metrics,
    exact_success,
    levenshtein_distance,
)
from tests.conftest import build_document

# --------------------------------------------------------------------------- #
#  Levenshtein
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("", "", 0),
        ("abc", "abc", 0),
        ("abc", "", 3),
        ("", "abc", 3),
        ("kitten", "sitting", 3),
        ("flaw", "lawn", 2),
        ("привет", "превет", 1),
    ],
)
def test_levenshtein_distance(a: str, b: str, expected: int) -> None:
    assert levenshtein_distance(a, b) == expected


# --------------------------------------------------------------------------- #
#  CER / WER / exact
# --------------------------------------------------------------------------- #


def test_identical_texts_give_zero_error() -> None:
    metrics = compute_pair_metrics("один два три", "один два три")
    assert metrics.cer == 0.0
    assert metrics.wer == 0.0
    assert metrics.exact_match is True
    assert metrics.similarity == 1.0


def test_single_character_substitution_cer() -> None:
    # "кот" -> "кит": 1 substitution over 3 reference characters
    metrics = compute_pair_metrics("кот", "кит")
    assert metrics.char_edit_distance == 1
    assert math.isclose(metrics.cer, 1 / 3, rel_tol=1e-6)


def test_wer_counts_word_level_errors() -> None:
    metrics = compute_pair_metrics("один два три четыре", "один два четыре")
    assert metrics.word_edit_distance == 1
    assert math.isclose(metrics.wer, 1 / 4, rel_tol=1e-6)
    assert metrics.reference_words == 4
    assert metrics.recognized_words == 3


def test_exact_match_survives_typographic_differences() -> None:
    reference = "«Договор» — итог 1 200,00 руб."
    recognized = '"Договор" - итог 1 200,00 руб.'
    assert compute_pair_metrics(reference, recognized).exact_match is True


def test_exact_match_fails_on_real_difference() -> None:
    assert compute_pair_metrics("сумма 100", "сумма 200").exact_match is False


def test_empty_reference_with_output_is_fully_wrong() -> None:
    metrics = compute_pair_metrics("", "лишний текст")
    assert metrics.cer == 1.0  # denominator falls back to the recognized length
    assert metrics.exact_match is False


def test_both_empty_is_perfect() -> None:
    metrics = compute_pair_metrics("", "")
    assert metrics.cer == 0.0
    assert metrics.wer == 0.0
    assert metrics.exact_match is True


def test_cer_can_exceed_one() -> None:
    assert compute_pair_metrics("аб", "абвгде").cer > 1.0


def test_normalization_options_change_cer() -> None:
    reference = "Цена: 100 руб."
    recognized = "цена 100 руб"
    with_punct = compute_pair_metrics(reference, recognized, NormalizationOptions())
    without_punct = compute_pair_metrics(
        reference, recognized, NormalizationOptions(remove_punctuation=True)
    )
    assert with_punct.cer > without_punct.cer
    assert without_punct.exact_match is True


# --------------------------------------------------------------------------- #
#  document-level entity filtering
# --------------------------------------------------------------------------- #


def test_metric_text_excludes_images() -> None:
    document = build_document(
        DocumentType.text_tables_images,
        pages=[[("text", "Текст абзаца."), ("image", "/static/images/s/a.png")]],
    )
    assert document.metric_text() == "Текст абзаца."


def test_tables_are_excluded_for_text_only_type() -> None:
    pages = [[("text", "Текст"), ("table", [["A", "B"]])]]
    text_only = build_document(DocumentType.text_only, pages=pages)
    with_tables = build_document(DocumentType.text_tables, pages=pages)
    assert "A" not in text_only.metric_text()
    assert "A" in with_tables.metric_text()


def test_images_never_reach_the_metrics_even_for_full_type() -> None:
    """Images stay file references, so their URL can never be 'recognized'."""
    reference = build_document(
        DocumentType.text_tables_images,
        pages=[[("text", "Текст"), ("image", "/static/images/s/ref.png")]],
    )
    recognized = build_document(
        DocumentType.text_tables_images,
        source=DocumentSource.recognized,
        pages=[[("text", "Текст"), ("image", "/static/images/s/other.png")]],
    )
    report = compute_metrics(reference, recognized)
    assert report.overall.exact_match is True
    assert report.overall.cer == 0.0


def test_exact_success_helper_matches_report() -> None:
    reference = build_document(DocumentType.text_only, pages=[[("text", "а б в")]])
    recognized = build_document(
        DocumentType.text_only,
        source=DocumentSource.recognized,
        pages=[[("text", "а б в")]],
    )
    assert exact_success(reference, recognized) is True


def test_table_cell_accuracy_is_computed_for_table_types() -> None:
    reference = build_document(
        DocumentType.text_tables,
        pages=[[("text", "Итого"), ("table", [["A", "B"], ["1", "2"]])]],
    )
    recognized = build_document(
        DocumentType.text_tables,
        source=DocumentSource.recognized,
        pages=[[("text", "Итого"), ("table", [["A", "X"], ["1", "2"]])]],
    )
    table_metrics = compare_tables(reference, recognized, NormalizationOptions())
    assert table_metrics is not None
    assert table_metrics.reference_tables == 1
    assert table_metrics.cell_accuracy == pytest.approx(0.75)


def test_table_metrics_are_none_for_text_only() -> None:
    reference = build_document(DocumentType.text_only, pages=[[("text", "x")]])
    recognized = build_document(
        DocumentType.text_only,
        source=DocumentSource.recognized,
        pages=[[("text", "x")]],
    )
    assert compare_tables(reference, recognized, NormalizationOptions()) is None


# --------------------------------------------------------------------------- #
#  per-page comparison
# --------------------------------------------------------------------------- #


def test_per_page_comparison_alignment() -> None:
    reference = build_document(
        DocumentType.text_only,
        pages=[[("text", "первая")], [("text", "вторая")]],
    )
    recognized = build_document(
        DocumentType.text_only,
        source=DocumentSource.recognized,
        pages=[[("text", "первая")], [("text", "2-я")], [("text", "лишняя")]],
        page_numbers=[1, 2, 3],
    )
    comparisons = compare_pages(reference, recognized, NormalizationOptions())
    assert [c.page_number for c in comparisons] == [1, 2, 3]
    assert comparisons[0].status is PageStatus.matched
    assert comparisons[0].metrics.exact_match is True
    assert comparisons[1].status is PageStatus.matched
    assert comparisons[1].metrics.cer > 0
    assert comparisons[2].status is PageStatus.extra_in_recognized


def test_missing_page_is_reported() -> None:
    reference = build_document(
        DocumentType.text_only,
        pages=[[("text", "стр 1")], [("text", "стр 2")]],
    )
    recognized = build_document(
        DocumentType.text_only,
        source=DocumentSource.recognized,
        pages=[[("text", "стр 1")]],
    )
    comparisons = compare_pages(reference, recognized, NormalizationOptions())
    assert comparisons[1].status is PageStatus.missing_in_recognized
    assert comparisons[1].metrics.cer == 1.0


# --------------------------------------------------------------------------- #
#  diff
# --------------------------------------------------------------------------- #


def test_diff_marks_equal_and_changed_words() -> None:
    segments, truncated = build_diff("один два три", "один ТРИ")
    assert truncated is False
    ops = [s.op for s in segments]
    assert DiffOp.equal in ops
    assert DiffOp.replace in ops or DiffOp.delete in ops


def test_diff_insert_and_delete() -> None:
    inserted, _ = build_diff("альфа гамма", "альфа бета гамма")
    assert any(s.op is DiffOp.insert and s.recognized == "бета" for s in inserted)

    deleted, _ = build_diff("альфа бета гамма", "альфа гамма")
    assert any(s.op is DiffOp.delete and s.reference == "бета" for s in deleted)


def test_diff_is_truncated_when_too_long() -> None:
    reference = " ".join(f"слово{i}" for i in range(50))
    recognized = " ".join(f"иначе{i}" for i in range(50))
    segments, truncated = build_diff(reference, recognized, max_segments=10)
    assert truncated is True
    assert len(segments) == 10


# --------------------------------------------------------------------------- #
#  full report
# --------------------------------------------------------------------------- #


def test_compute_metrics_report_contains_everything() -> None:
    reference = build_document(
        DocumentType.text_tables,
        pages=[[("text", "Итого:"), ("table", [["A", "100"]])]],
    )
    recognized = build_document(
        DocumentType.text_tables,
        source=DocumentSource.recognized,
        pages=[[("text", "Итого:"), ("table", [["A", "200"]])]],
    )
    report = compute_metrics(reference, recognized)
    assert report.document_type == "text_tables"
    assert report.accounted_entities == ["text", "tables"]
    assert report.overall.exact_match is False
    assert report.tables is not None
    assert len(report.per_page) == 1
    assert report.diff
    assert report.reference_text_preview


def test_report_notes_when_reference_has_no_tables() -> None:
    reference = build_document(
        DocumentType.text_tables, pages=[[("text", "только текст")]]
    )
    recognized = build_document(
        DocumentType.text_tables,
        source=DocumentSource.recognized,
        pages=[[("text", "только текст")]],
    )
    report = compute_metrics(reference, recognized)
    assert any("таблицы не найдены" in note for note in report.notes)


def test_report_notes_when_types_mismatch() -> None:
    reference = build_document(DocumentType.text_only, pages=[[("text", "x")]])
    recognized = build_document(
        DocumentType.text_tables,
        source=DocumentSource.recognized,
        pages=[[("text", "x")]],
    )
    report = compute_metrics(reference, recognized)
    assert any("не совпадает" in note for note in report.notes)
