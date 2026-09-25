"""Schemas for text normalization, error rates and the diff viewer."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class NormalizationOptions(BaseModel):
    """Switches applied to BOTH sides before any comparison.

    Defaults follow the brief: lowercase, collapse whitespace, unify quotes and
    dashes.  Punctuation removal is *optional* because it materially changes CER.
    """

    lowercase: bool = True
    collapse_whitespace: bool = True
    unify_quotes: bool = True
    unify_dashes: bool = True
    remove_punctuation: bool = False
    strip_diacritics: bool = False

    label: str = "default"


class DiffOp(str, Enum):
    equal = "equal"
    insert = "insert"
    delete = "delete"
    replace = "replace"


class DiffSegment(BaseModel):
    """One word-level diff hunk.

    `reference` is the token(s) seen in file A, `recognized` what GLM produced.
    `equal`   - identical (both sides shown in grey)
    `insert`  - present only in the recognized text (hallucination / addition)
    `delete`  - present only in the reference text (missed by the model)
    `replace` - both sides non-empty and different
    """

    op: DiffOp
    reference: str = ""
    recognized: str = ""


class PairMetrics(BaseModel):
    """CER / WER / exact success for one text pair."""

    cer: float = 0.0
    wer: float = 0.0
    exact_match: bool = False
    similarity: float = 0.0

    char_edit_distance: int = 0
    word_edit_distance: int = 0
    reference_chars: int = 0
    recognized_chars: int = 0
    reference_words: int = 0
    recognized_words: int = 0


class PageStatus(str, Enum):
    matched = "matched"
    missing_in_recognized = "missing_in_recognized"
    extra_in_recognized = "extra_in_recognized"


class PageComparison(BaseModel):
    page_number: int
    status: PageStatus
    metrics: PairMetrics
    reference_blocks: int = 0
    recognized_blocks: int = 0
    reference_tables: int = 0
    recognized_tables: int = 0
    reference_images: int = 0
    recognized_images: int = 0


class TableMetrics(BaseModel):
    """Table-level sanity metrics (extra insight, table docs only)."""

    reference_tables: int = 0
    recognized_tables: int = 0
    matched_rows: int = 0
    cell_accuracy: float = 0.0
    row_count_delta: int = 0


class PerformanceMetrics(BaseModel):
    """Wall-clock and token accounting for the GLM call."""

    model: str | None = None
    request_seconds: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    pages_processed: int = 0
    per_page_seconds: list[float] = Field(default_factory=list)
    retries: int = 0
    fallback_models: list[str] = Field(default_factory=list)

    @property
    def seconds_per_page(self) -> float:
        if not self.pages_processed:
            return 0.0
        return self.request_seconds / self.pages_processed


class MetricsReport(BaseModel):
    session_id: str
    document_type: str
    generated_at: str
    options: NormalizationOptions
    accounted_entities: list[str] = Field(default_factory=list)
    overall: PairMetrics
    per_page: list[PageComparison] = Field(default_factory=list)
    tables: TableMetrics | None = None
    performance: PerformanceMetrics = Field(default_factory=PerformanceMetrics)
    reference_text_preview: str = ""
    recognized_text_preview: str = ""
    diff: list[DiffSegment] = Field(default_factory=list)
    diff_truncated: bool = False
    notes: list[str] = Field(default_factory=list)
