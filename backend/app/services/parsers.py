"""Format detection, upload validation and the reference-parsing dispatcher."""

from __future__ import annotations

import mimetypes
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from app.config import Settings
from app.schemas.document import DocumentJSON, DocumentType
from app.services.docx_parser import DOCX_MAGIC, extract_docx_reference
from app.services.images import ImageStore
from app.services.pdf_parser import (
    PDF_MAGIC,
    RenderedPage,
    TextLayerProbe,
    extract_pdf_reference,
    probe_text_layer,
)

PDF_SUFFIXES = {".pdf"}
DOCX_SUFFIXES = {".docx"}

MIME_BY_SUFFIX = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class UploadValidationError(ValueError):
    """Raised for anything the user can fix by picking another file."""

    def __init__(self, message: str, code: str = "invalid_upload") -> None:
        super().__init__(message)
        self.code = code


@dataclass
class FileProbe:
    suffix: str
    mime_type: str
    size_bytes: int
    page_count: int | None = None
    has_text_layer: bool | None = None
    text_layer_chars: int | None = None


@dataclass
class ParseResult:
    document: DocumentJSON
    rendered_pages: list[RenderedPage] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    page_count: int = 0
    has_text_layer: bool | None = None
    text_layer_chars: int | None = None


# --------------------------------------------------------------------------- #
#  detection & validation
# --------------------------------------------------------------------------- #


def detect_suffix(filename: str, blob: bytes | None = None) -> str:
    """Extension taken from the file name, lower-cased.

    The extension is authoritative for *which* format the user declares; the
    magic bytes are only used as a cross-check in :func:`validate_upload`, so a
    `.txt` file that happens to contain a PDF is still rejected loudly instead
    of being silently treated as a PDF.
    """
    return Path(filename).suffix.lower()


def sniff_format(blob: bytes) -> str | None:
    """Format guessed from the content, or ``None`` when unknown."""
    if blob.startswith(PDF_MAGIC):
        return ".pdf"
    if blob.startswith(DOCX_MAGIC):
        return ".docx"
    return None


def _materialize(suffix: str, blob: bytes) -> Path:
    """Temporary file with the *declared* suffix so MuPDF picks the right parser."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
        handle.write(blob)
        return Path(handle.name)


def _probe_pdf_text_layer(path: Path, settings: Settings) -> TextLayerProbe:
    try:
        return probe_text_layer(path, min_chars=settings.text_layer_min_chars)
    finally:
        path.unlink(missing_ok=True)


def validate_upload(
    filename: str, blob: bytes, settings: Settings, *, role: str
) -> FileProbe:
    """Size / extension / MIME / content-sniffing validation for one file."""
    if not filename:
        raise UploadValidationError(f"{role}: не указано имя файла.", "missing_filename")
    if not blob:
        raise UploadValidationError(f"{role}: файл пустой.", "empty_file")

    size = len(blob)
    if size > settings.max_upload_bytes:
        raise UploadValidationError(
            f"{role}: файл больше {settings.max_upload_mb} МБ "
            f"(получено {size / 1024 / 1024:.1f} МБ).",
            "file_too_large",
        )

    suffix = detect_suffix(filename, blob)
    if suffix not in settings.allowed_suffixes:
        allowed = ", ".join(sorted(settings.allowed_suffixes))
        raise UploadValidationError(
            f"{role}: формат «{suffix or 'неизвестен'}» не поддерживается. "
            f"Допустимо: {allowed}.",
            "unsupported_format",
        )

    sniffed = sniff_format(blob)
    if sniffed != suffix:
        raise UploadValidationError(
            f"{role}: содержимое файла не соответствует расширению {suffix} "
            f"(проверка MIME{' определила ' + sniffed if sniffed else ' не распознала формат'}).",
            "mime_mismatch",
        )

    guessed = mimetypes.guess_type(filename)[0]
    probe = FileProbe(
        suffix=suffix,
        mime_type=MIME_BY_SUFFIX.get(suffix) or guessed or "application/octet-stream",
        size_bytes=size,
    )

    if suffix == ".pdf":
        layer = _probe_pdf_text_layer(_materialize(suffix, blob), settings)
        probe.page_count = layer.page_count
        probe.has_text_layer = layer.has_text_layer
        probe.text_layer_chars = layer.text_chars

    return probe


# --------------------------------------------------------------------------- #
#  reference parsing
# --------------------------------------------------------------------------- #


def parse_reference(
    path: str | Path,
    *,
    document_type: DocumentType,
    session_id: str,
    store: ImageStore,
    settings: Settings,
    suffix: str,
) -> ParseResult:
    """Turn file A into the reference `DocumentJSON`."""
    if suffix in PDF_SUFFIXES:
        extraction = extract_pdf_reference(
            path,
            document_type=document_type,
            session_id=session_id,
            store=store,
            dpi=settings.render_dpi,
            max_pages=settings.render_max_pages,
            renderer_backend=settings.renderer_backend,
        )
        probe = probe_text_layer(path, min_chars=settings.text_layer_min_chars)
        return ParseResult(
            document=extraction.document,
            rendered_pages=extraction.rendered_pages,
            warnings=extraction.warnings,
            page_count=probe.page_count,
            has_text_layer=probe.has_text_layer,
            text_layer_chars=probe.text_chars,
        )

    if suffix in DOCX_SUFFIXES:
        extraction = extract_docx_reference(
            path,
            document_type=document_type,
            session_id=session_id,
            store=store,
        )
        return ParseResult(
            document=extraction.document,
            warnings=extraction.warnings,
            page_count=len(extraction.document.pages),
            has_text_layer=True,
            text_layer_chars=len(extraction.document.metric_text()),
        )

    raise UploadValidationError(
        f"Формат «{suffix}» не поддерживается для эталона.", "unsupported_format"
    )


def render_recognized_pages(
    path: str | Path, settings: Settings, suffix: str
) -> list[RenderedPage]:
    """Rasterize file B for the GLM call (PDF scans only)."""
    from app.services.pdf_parser import render_pdf

    if suffix not in PDF_SUFFIXES:
        raise UploadValidationError(
            "Распознаваемый документ отправляется в GLM как изображения страниц, "
            "поэтому файл Б должен быть PDF-сканом. Конвертируйте DOCX в PDF.",
            "recognized_must_be_pdf",
        )
    return render_pdf(
        path,
        dpi=settings.render_dpi,
        max_pages=settings.render_max_pages,
        backend=settings.renderer_backend,
    )
