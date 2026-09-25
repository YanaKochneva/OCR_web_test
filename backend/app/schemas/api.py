"""Request/response bodies for the public REST API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.document import DocumentJSON, DocumentType, EntitySet, FileInfo
from app.schemas.metrics import MetricsReport, NormalizationOptions
from app.schemas.recognition import RecognitionMeta


class DocumentTypeInfo(BaseModel):
    """Card definition for screen 1 of the UI."""

    id: DocumentType
    label: str
    description: str
    entities: EntitySet
    accepted_hint: str = "PDF или DOCX, до 50 МБ"


class DocumentTypeListResponse(BaseModel):
    document_types: list[DocumentTypeInfo]
    default: DocumentType = DocumentType.text_tables_images


# --------------------------------------------------------------------------- #
#  POST /api/upload
# --------------------------------------------------------------------------- #


class UploadedSide(BaseModel):
    role: str  # "reference" | "recognized"
    file: FileInfo
    document: DocumentJSON | None = None
    ready: bool = False
    warnings: list[str] = Field(default_factory=list)


class UploadResponse(BaseModel):
    session_id: str
    document_type: DocumentType
    reference: UploadedSide
    recognized: UploadedSide
    warnings: list[str] = Field(default_factory=list)
    next_step: str = "recognize"


# --------------------------------------------------------------------------- #
#  POST /api/recognize
# --------------------------------------------------------------------------- #


class RecognizeRequest(BaseModel):
    session_id: str
    model: str | None = None
    force: bool = False


class RecognizeResponse(BaseModel):
    session_id: str
    document_type: DocumentType
    model: str
    document: DocumentJSON
    meta: RecognitionMeta
    warnings: list[str] = Field(default_factory=list)
    next_step: str = "metrics"


# --------------------------------------------------------------------------- #
#  POST /api/metrics
# --------------------------------------------------------------------------- #


class MetricsRequest(BaseModel):
    session_id: str
    options: NormalizationOptions = Field(default_factory=NormalizationOptions)
    include_diff: bool = True
    recompute: bool = True


class MetricsResponse(BaseModel):
    session_id: str
    document_type: DocumentType
    report: MetricsReport
    next_step: str = "done"


# --------------------------------------------------------------------------- #
#  GET /api/results/{id}
# --------------------------------------------------------------------------- #


class SessionSummary(BaseModel):
    session_id: str
    document_type: DocumentType
    created_at: str
    updated_at: str | None = None
    reference_filename: str | None = None
    recognized_filename: str | None = None
    recognized_status: str = "pending"  # pending | ready | failed
    metrics_status: str = "pending"  # pending | ready
    model: str | None = None
    cer: float | None = None
    wer: float | None = None
    exact_match: bool | None = None
    request_seconds: float | None = None
    total_tokens: int | None = None


class ResultsResponse(BaseModel):
    session: SessionSummary
    reference_file: FileInfo | None = None
    recognized_file: FileInfo | None = None
    reference: DocumentJSON | None = None
    recognized: DocumentJSON | None = None
    recognition: RecognitionMeta | None = None
    metrics: MetricsReport | None = None
    warnings: list[str] = Field(default_factory=list)

    # explicit gates used by the UI to enable/disable buttons
    reference_json_ready: bool = False
    recognized_json_ready: bool = False
    metrics_ready: bool = False


class SessionListResponse(BaseModel):
    sessions: list[SessionSummary]


class ErrorResponse(BaseModel):
    detail: str
    code: str | None = None
    context: dict | None = None
