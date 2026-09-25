"""PDF handling: page rendering, text-layer probing and reference extraction.

PyMuPDF is the default backend because it needs no external binaries (unlike
`pdf2image`, which requires a Poppler build on Windows).  `pdf2image` is kept
as an opt-in alternative through `RENDERER_BACKEND=pdf2image`.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from app.schemas.document import (
    DocumentJSON,
    DocumentPage,
    DocumentSource,
    DocumentType,
    make_image_block,
    make_table_block,
    make_text_block,
    renumber_blocks,
)
from app.services.images import ImageStore, clamp_bbox
from app.services.layout import sort_document_reading_order

try:  # PyMuPDF >= 1.24 exposes the `pymupdf` name, older ones only `fitz`
    import pymupdf as fitz  # type: ignore
except ImportError:  # pragma: no cover
    import fitz  # type: ignore

PDF_MAGIC = b"%PDF-"
MIN_EMBEDDED_IMAGE_PIXELS = 24 * 24


# --------------------------------------------------------------------------- #
#  primitives
# --------------------------------------------------------------------------- #


@dataclass
class RenderedPage:
    page_number: int
    image: Image.Image
    width: int
    height: int

    @property
    def size(self) -> list[int]:
        return [self.width, self.height]


@dataclass
class TextLayerProbe:
    page_count: int
    text_chars: int
    has_text_layer: bool
    per_page_chars: list[int] = field(default_factory=list)


class PdfError(RuntimeError):
    """Raised when a PDF cannot be opened or parsed."""


def is_pdf_bytes(blob: bytes) -> bool:
    return blob[:5] == PDF_MAGIC


def open_pdf(path: str | Path):
    try:
        document = fitz.open(str(path))
    except Exception as exc:  # pragma: no cover - depends on bad input
        raise PdfError(f"Не удалось открыть PDF: {exc}") from exc
    return document


def page_count(path: str | Path) -> int:
    with open_pdf(path) as document:
        return document.page_count


def probe_text_layer(
    path: str | Path, min_chars: int = 20, sample_pages: int = 3
) -> TextLayerProbe:
    """Decide whether a PDF carries a real text layer.

    File B must NOT have one: it is a printed and hand-signed copy, i.e. a pure
    scan.  Only the first `sample_pages` pages are inspected, which is enough to
    classify the document and keeps validation fast.
    """
    with open_pdf(path) as document:
        count = document.page_count
        per_page: list[int] = []
        for index in range(min(count, sample_pages)):
            text = document.load_page(index).get_text("text") or ""
            per_page.append(len(text.strip()))
    total = sum(per_page)
    return TextLayerProbe(
        page_count=count,
        text_chars=total,
        has_text_layer=total >= min_chars,
        per_page_chars=per_page,
    )


# --------------------------------------------------------------------------- #
#  rendering
# --------------------------------------------------------------------------- #


def render_pdf(
    path: str | Path,
    *,
    dpi: int = 200,
    max_pages: int = 50,
    backend: str = "pymupdf",
) -> list[RenderedPage]:
    """Rasterize every page (up to `max_pages`) into an RGB PIL image."""
    backend = (backend or "pymupdf").lower()
    if backend == "pdf2image":
        try:
            return _render_with_pdf2image(path, dpi=dpi, max_pages=max_pages)
        except Exception:  # pragma: no cover - fall back when poppler is absent
            pass
    return _render_with_pymupdf(path, dpi=dpi, max_pages=max_pages)


def _render_with_pymupdf(
    path: str | Path, *, dpi: int, max_pages: int
) -> list[RenderedPage]:
    scale = dpi / 72.0
    pages: list[RenderedPage] = []
    with open_pdf(path) as document:
        limit = min(document.page_count, max_pages)
        matrix = fitz.Matrix(scale, scale)
        for index in range(limit):
            page = document.load_page(index)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            image = Image.frombytes(
                "RGB", (pixmap.width, pixmap.height), pixmap.samples
            )
            pages.append(
                RenderedPage(
                    page_number=index + 1,
                    image=image,
                    width=pixmap.width,
                    height=pixmap.height,
                )
            )
    return pages


def _render_with_pdf2image(  # pragma: no cover - requires poppler
    path: str | Path, *, dpi: int, max_pages: int
) -> list[RenderedPage]:
    from pdf2image import convert_from_path

    images = convert_from_path(
        str(path), dpi=dpi, first_page=1, last_page=max_pages, fmt="png"
    )
    return [
        RenderedPage(
            page_number=index + 1,
            image=image.convert("RGB"),
            width=image.width,
            height=image.height,
        )
        for index, image in enumerate(images)
    ]


def image_to_png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


# --------------------------------------------------------------------------- #
#  reference extraction (file A: PDF with a real text layer)
# --------------------------------------------------------------------------- #


@dataclass
class PdfExtraction:
    document: "DocumentJSON"
    rendered_pages: list[RenderedPage] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _bbox_of(rect) -> list[float]:
    return [
        round(float(rect.x0), 2),
        round(float(rect.y0), 2),
        round(float(rect.x1 - rect.x0), 2),
        round(float(rect.y1 - rect.y0), 2),
    ]


def _overlaps(a: list[float], b: list[float], threshold: float = 0.5) -> bool:
    """True when `a` (xywh) is covered by `b` (xywh) for more than `threshold`."""
    ax0, ay0, aw, ah = a
    bx0, by0, bw, bh = b
    ax1, ay1 = ax0 + aw, ay0 + ah
    bx1, by1 = bx0 + bw, by0 + bh
    overlap_x = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    overlap_y = max(0.0, min(ay1, by1) - max(ay0, by0))
    overlap_area = overlap_x * overlap_y
    area = aw * ah
    if area <= 0:
        return False
    return overlap_area / area >= threshold


def _extract_tables(page) -> list[tuple[list[list[str]], list[float] | None]]:
    """Table rows + bbox via PyMuPDF's built-in table finder (1.23+)."""
    finder = getattr(page, "find_tables", None)
    if finder is None:
        return []
    try:
        result = page.find_tables()
    except Exception:  # pragma: no cover - malformed content
        return []

    tables: list[tuple[list[list[str]], list[float] | None]] = []
    for table in getattr(result, "tables", []):
        try:
            data = table.extract()
        except Exception:  # pragma: no cover
            continue
        if not data:
            continue
        rows = [[("" if cell is None else cell) for cell in row] for row in data]
        bbox = _bbox_of(fitz.Rect(table.bbox)) if getattr(table, "bbox", None) else None
        tables.append((rows, bbox))
    return tables


def _extract_images(page, dpi: int) -> list[tuple[bytes, list[float]]]:
    """Embedded raster images, re-rendered at `dpi` and clipped to their rect."""
    found: list[tuple[bytes, list[float]]] = []
    seen: set[tuple[int, tuple[float, ...]]] = set()

    for item in page.get_images(full=True):
        xref = item[0]
        try:
            rects = page.get_image_rects(xref)
        except Exception:  # pragma: no cover
            continue
        for rect in rects:
            if rect.is_empty or rect.is_infinite:
                continue
            key = (xref, (round(rect.x0, 1), round(rect.y0, 1)))
            if key in seen:
                continue
            seen.add(key)
            if rect.width * rect.height < MIN_EMBEDDED_IMAGE_PIXELS:
                continue
            try:
                pixmap = page.get_pixmap(
                    clip=rect, matrix=fitz.Matrix(dpi / 72.0, dpi / 72.0), alpha=False
                )
                blob = image_to_png_bytes(
                    Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
                )
            except Exception:  # pragma: no cover
                continue
            found.append((blob, _bbox_of(rect)))

    return found


# --------------------------------------------------------------------------- #
#  public entry point
# --------------------------------------------------------------------------- #


def extract_pdf_reference(
    path: str | Path,
    *,
    document_type: DocumentType,
    session_id: str,
    store: ImageStore,
    dpi: int = 200,
    max_pages: int = 50,
    renderer_backend: str = "pymupdf",
) -> PdfExtraction:
    """Build the reference JSON for a digital PDF.

    Text and tables come from the embedded text layer (exact, no OCR), images
    are cropped out of a high-DPI render so the reference and the recognized
    document reference byte-identical pictures.
    """
    entity_set = document_type.entity_set
    warnings: list[str] = []
    pages: list[DocumentPage] = []
    rendered_pages: list[RenderedPage] = []

    if entity_set.images:
        rendered_pages = render_pdf(
            path, dpi=dpi, max_pages=max_pages, backend=renderer_backend
        )
        rendered_lookup = {p.page_number: p for p in rendered_pages}
    else:
        rendered_lookup = {}

    scale = dpi / 72.0

    with open_pdf(path) as document:
        if document.page_count > max_pages:
            warnings.append(
                f"PDF содержит {document.page_count} страниц, обработаны "
                f"первые {max_pages} (лимит RENDER_MAX_PAGES)."
            )

        limit = min(document.page_count, max_pages)
        for index in range(limit):
            page = document.load_page(index)
            rendered = rendered_lookup.get(index + 1)
            page_width = rendered.width if rendered else int(page.rect.width * scale)
            page_height = rendered.height if rendered else int(page.rect.height * scale)
            page_size = [page_width, page_height]

            blocks: list = []
            table_bboxes: list[list[float]] = []

            if entity_set.tables:
                for rows, table_bbox in _extract_tables(page):
                    scaled_bbox = (
                        [
                            round(table_bbox[0] * scale, 2),
                            round(table_bbox[1] * scale, 2),
                            round(table_bbox[2] * scale, 2),
                            round(table_bbox[3] * scale, 2),
                        ]
                        if table_bbox
                        else None
                    )
                    blocks.append(
                        make_table_block(rows, scaled_bbox, source="pymupdf")
                    )
                    if scaled_bbox:
                        table_bboxes.append(scaled_bbox)

            if entity_set.text:
                for entry in page.get_text("blocks"):
                    x0, y0, x1, y1, content, _block_no, block_type = entry[:7]
                    if block_type != 0 or not (content or "").strip():
                        continue
                    bbox = [
                        round(x0 * scale, 2),
                        round(y0 * scale, 2),
                        round((x1 - x0) * scale, 2),
                        round((y1 - y0) * scale, 2),
                    ]
                    if any(_overlaps(bbox, tb) for tb in table_bboxes):
                        continue  # already captured as table cells
                    blocks.append(
                        make_text_block(
                            content, bbox, page_size=page_size, source="pymupdf"
                        )
                    )

            if entity_set.images:
                for blob, bbox in _extract_images(page, dpi):
                    url = store.save_bytes(session_id, blob, tag=f"p{index + 1}")
                    blocks.append(
                        make_image_block(
                            url,
                            clamp_bbox(bbox, page_size),
                            page_size=page_size,
                            source="pymupdf",
                        )
                    )

            pages.append(
                DocumentPage(
                    page_number=index + 1,
                    width=page_width,
                    height=page_height,
                    blocks=blocks,
                )
            )

    document_json = DocumentJSON(
        document_type=document_type,
        source=DocumentSource.reference,
        session_id=session_id,
        pages=pages,
        parser=f"pdf:{renderer_backend}",
    )
    sort_document_reading_order(document_json)
    renumber_blocks(document_json)

    return PdfExtraction(
        document=document_json,
        rendered_pages=rendered_pages,
        warnings=warnings,
    )
