"""CER / WER / exact-match computation plus page comparison and diffing.

`compute_metrics` is intentionally pure (documents in, report out) so it can be
unit-tested without FastAPI, GLM or the filesystem.
"""

from __future__ import annotations

import difflib
from datetime import datetime, timezone
from typing import Sequence

from app.schemas.document import BlockType, DocumentJSON, DocumentPage
from app.schemas.metrics import (
    DiffOp,
    DiffSegment,
    MetricsReport,
    NormalizationOptions,
    PageComparison,
    PageStatus,
    PairMetrics,
    PerformanceMetrics,
    TableMetrics,
)
from app.services.normalization import (
    normalize_for_diff,
    normalize_text,
    tokenize,
)

MAX_DIFF_SEGMENTS = 4000

try:  # fast path
    from rapidfuzz.distance import Levenshtein as _RapidLevenshtein
except Exception:  # pragma: no cover - optional dependency
    _RapidLevenshtein = None


# --------------------------------------------------------------------------- #
#  edit distance
# --------------------------------------------------------------------------- #


def _pure_levenshtein(a: Sequence, b: Sequence) -> int:
    """Two-row dynamic programming Levenshtein distance."""
    if a == b:
        return 0
    len_a, len_b = len(a), len(b)
    if len_a == 0:
        return len_b
    if len_b == 0:
        return len_a

    previous = list(range(len_b + 1))
    for i in range(1, len_a + 1):
        current = [i] + [0] * len_b
        item_a = a[i - 1]
        for j in range(1, len_b + 1):
            cost = 0 if item_a == b[j - 1] else 1
            current[j] = min(
                previous[j] + 1,        # deletion
                current[j - 1] + 1,     # insertion
                previous[j - 1] + cost,  # substitution
            )
        previous = current
    return previous[len_b]


def levenshtein_distance(a: Sequence, b: Sequence) -> int:
    """Edit distance between two sequences (chars or tokens)."""
    if _RapidLevenshtein is not None:
        return int(_RapidLevenshtein.distance(a, b))
    return _pure_levenshtein(a, b)


def _ratio(edit_distance: int, reference_length: int, recognized_length: int) -> float:
    """Rate with a safe denominator.

    When the reference is empty but the model produced text we cannot divide by
    zero, so we fall back to the reference length, and finally to 1.0 if both
    sides are empty (already handled by the caller returning 0.0).
    """
    denominator = reference_length
    if denominator == 0:
        denominator = recognized_length
    if denominator == 0:
        return 0.0
    return round(edit_distance / denominator, 6)


# --------------------------------------------------------------------------- #
#  core pair metric
# --------------------------------------------------------------------------- #


def compute_pair_metrics(
    reference_text: str,
    recognized_text: str,
    options: NormalizationOptions | None = None,
    *,
    reference_normalized: str | None = None,
    recognized_normalized: str | None = None,
) -> PairMetrics:
    """CER / WER / exact success for a single text pair."""
    options = options or NormalizationOptions()

    ref_norm = (
        reference_normalized
        if reference_normalized is not None
        else normalize_text(reference_text, options)
    )
    hyp_norm = (
        recognized_normalized
        if recognized_normalized is not None
        else normalize_text(recognized_text, options)
    )

    ref_words = tokenize(ref_norm)
    hyp_words = tokenize(hyp_norm)

    char_distance = levenshtein_distance(ref_norm, hyp_norm)
    word_distance = levenshtein_distance(ref_words, hyp_words)

    max_len = max(len(ref_norm), len(hyp_norm))
    similarity = 0.0 if max_len == 0 else round(1.0 - char_distance / max_len, 6)

    return PairMetrics(
        cer=_ratio(char_distance, len(ref_norm), len(hyp_norm)),
        wer=_ratio(word_distance, len(ref_words), len(hyp_words)),
        exact_match=ref_norm == hyp_norm,
        similarity=max(0.0, similarity),
        char_edit_distance=char_distance,
        word_edit_distance=word_distance,
        reference_chars=len(ref_norm),
        recognized_chars=len(hyp_norm),
        reference_words=len(ref_words),
        recognized_words=len(hyp_words),
    )



# --------------------------------------------------------------------------- #
#  diff
# --------------------------------------------------------------------------- #


def build_diff(
    reference_text: str,
    recognized_text: str,
    options: NormalizationOptions | None = None,
    *,
    max_segments: int = MAX_DIFF_SEGMENTS,
) -> tuple[list[DiffSegment], bool]:
    """Word-level diff of the two normalized texts.

    Returns the segments plus a flag telling whether the list was truncated.
    """
    options = options or NormalizationOptions()
    ref_words = tokenize(normalize_for_diff(reference_text, options))
    hyp_words = tokenize(normalize_for_diff(recognized_text, options))

    matcher = difflib.SequenceMatcher(a=ref_words, b=hyp_words, autojunk=False)
    segments: list[DiffSegment] = []
    truncated = False

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            segments.append(
                DiffSegment(
                    op=DiffOp.equal,
                    reference=" ".join(ref_words[i1:i2]),
                    recognized=" ".join(hyp_words[j1:j2]),
                )
            )
        elif tag == "delete":
            segments.append(
                DiffSegment(op=DiffOp.delete, reference=" ".join(ref_words[i1:i2]))
            )
        elif tag == "insert":
            segments.append(
                DiffSegment(op=DiffOp.insert, recognized=" ".join(hyp_words[j1:j2]))
            )
        else:  # replace - pair word-by-word so the UI can align columns
            ref_chunk = ref_words[i1:i2]
            hyp_chunk = hyp_words[j1:j2]
            for index in range(max(len(ref_chunk), len(hyp_chunk))):
                left = ref_chunk[index] if index < len(ref_chunk) else ""
                right = hyp_chunk[index] if index < len(hyp_chunk) else ""
                if left and right:
                    op = DiffOp.equal if left == right else DiffOp.replace
                    segments.append(
                        DiffSegment(op=op, reference=left, recognized=right)
                    )
                elif left:
                    segments.append(DiffSegment(op=DiffOp.delete, reference=left))
                else:
                    segments.append(DiffSegment(op=DiffOp.insert, recognized=right))

        if len(segments) >= max_segments:
            truncated = True
            break

    return segments[:max_segments], truncated


# --------------------------------------------------------------------------- #
#  page alignment
# --------------------------------------------------------------------------- #


def _page_index(document: DocumentJSON) -> dict[int, DocumentPage]:
    return {page.page_number: page for page in document.pages}


def _count(page: DocumentPage | None, block_type: BlockType) -> int:
    return 0 if page is None else len(page.blocks_of(block_type))


def compare_pages(
    reference: DocumentJSON,
    recognized: DocumentJSON,
    options: NormalizationOptions,
) -> list[PageComparison]:
    """Align pages by `page_number` and score each pair independently."""
    ref_pages = _page_index(reference)
    hyp_pages = _page_index(recognized)

    comparisons: list[PageComparison] = []
    for number in sorted(set(ref_pages) | set(hyp_pages)):
        ref_page = ref_pages.get(number)
        hyp_page = hyp_pages.get(number)

        if ref_page and hyp_page:
            status = PageStatus.matched
        elif ref_page:
            status = PageStatus.missing_in_recognized
        else:
            status = PageStatus.extra_in_recognized

        comparisons.append(
            PageComparison(
                page_number=number,
                status=status,
                metrics=compute_pair_metrics(
                    ref_page.metric_text() if ref_page else "",
                    hyp_page.metric_text() if hyp_page else "",
                    options,
                ),
                reference_blocks=len(ref_page.blocks) if ref_page else 0,
                recognized_blocks=len(hyp_page.blocks) if hyp_page else 0,
                reference_tables=_count(ref_page, BlockType.table),
                recognized_tables=_count(hyp_page, BlockType.table),
                reference_images=_count(ref_page, BlockType.image),
                recognized_images=_count(hyp_page, BlockType.image),
            )
        )
    return comparisons


# --------------------------------------------------------------------------- #
#  tables
# --------------------------------------------------------------------------- #


def _cell(rows: list[list[str]], row_index: int, col_index: int) -> str:
    if row_index >= len(rows):
        return ""
    row = rows[row_index]
    if col_index >= len(row):
        return ""
    return row[col_index] or ""


def compare_tables(
    reference: DocumentJSON, recognized: DocumentJSON, options: NormalizationOptions
) -> TableMetrics | None:
    """Cell-level accuracy over row-aligned table pairs."""
    if not reference.entity_set.tables:
        return None

    ref_tables = reference.tables()
    hyp_tables = recognized.tables()

    total_cells = 0
    correct_cells = 0

    for ref_table, hyp_table in zip(ref_tables, hyp_tables):
        ref_rows = ref_table.rows or []
        hyp_rows = hyp_table.rows or []
        width = max([len(r) for r in ref_rows] + [len(r) for r in hyp_rows] + [0])
        for row_index in range(max(len(ref_rows), len(hyp_rows))):
            for col_index in range(width):
                total_cells += 1
                if normalize_text(
                    _cell(ref_rows, row_index, col_index), options
                ) == normalize_text(_cell(hyp_rows, row_index, col_index), options):
                    correct_cells += 1

    matched_rows = sum(
        min(len(t.rows or []), len(o.rows or [])) for t, o in zip(ref_tables, hyp_tables)
    )
    row_count_delta = sum(len(t.rows or []) for t in ref_tables) - sum(
        len(o.rows or []) for o in hyp_tables
    )

    return TableMetrics(
        reference_tables=len(ref_tables),
        recognized_tables=len(hyp_tables),
        matched_rows=matched_rows,
        cell_accuracy=0.0 if total_cells == 0 else round(correct_cells / total_cells, 6),
        row_count_delta=row_count_delta,
    )


# --------------------------------------------------------------------------- #
#  report
# --------------------------------------------------------------------------- #


def compute_metrics(
    reference: DocumentJSON,
    recognized: DocumentJSON,
    options: NormalizationOptions | None = None,
    *,
    performance: PerformanceMetrics | None = None,
    include_diff: bool = True,
    preview_chars: int = 1500,
) -> MetricsReport:
    """Full benchmark report for one reference/recognized pair."""
    options = options or NormalizationOptions()

    reference_text = reference.metric_text()
    recognized_text = recognized.metric_text()

    ref_normalized = normalize_text(reference_text, options)
    hyp_normalized = normalize_text(recognized_text, options)

    overall = compute_pair_metrics(
        reference_text,
        recognized_text,
        options,
        reference_normalized=ref_normalized,
        recognized_normalized=hyp_normalized,
    )

    notes: list[str] = []
    if reference.document_type != recognized.document_type:
        notes.append(
            "Тип документа эталона и результата не совпадает - "
            "метрики посчитаны по типу эталона."
        )
    if not ref_normalized:
        notes.append("Эталонный текст после нормализации пуст - метрики недостоверны.")
    if not hyp_normalized:
        notes.append(
            "Распознанный текст после нормализации пуст - проверьте вызов GLM."
        )
    if reference.entity_set.tables and not reference.tables():
        notes.append(
            "Для выбранного типа документа таблицы не найдены в эталоне."
        )
    if reference.entity_set.images:
        images = len(reference.images())
        if images:
            notes.append(
                f"Изображения ({images} шт.) сохранены как кропы страницы и "
                "исключены из CER/WER."
            )

    diff: list[DiffSegment] = []
    diff_truncated = False
    if include_diff:
        diff, diff_truncated = build_diff(
            reference_text, recognized_text, options
        )

    return MetricsReport(
        session_id=reference.session_id,
        document_type=reference.document_type.value,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        options=options,
        accounted_entities=reference.entity_set.metric_entities,
        overall=overall,
        per_page=compare_pages(reference, recognized, options),
        tables=compare_tables(reference, recognized, options),
        performance=performance or PerformanceMetrics(),
        reference_text_preview=ref_normalized[:preview_chars],
        recognized_text_preview=hyp_normalized[:preview_chars],
        diff=diff,
        diff_truncated=diff_truncated,
        notes=notes,
    )


def exact_success(
    reference: DocumentJSON,
    recognized: DocumentJSON,
    options: NormalizationOptions | None = None,
) -> bool:
    """Document-level exact success (convenience wrapper, used in tests)."""
    options = options or NormalizationOptions()
    return compute_pair_metrics(
        reference.metric_text(), recognized.metric_text(), options
    ).exact_match
