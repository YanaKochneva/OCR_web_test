"""Tests for PDF rendering, text-layer probing and reference extraction."""

from __future__ import annotations

import pytest

from app.schemas.document import BlockType, DocumentType
from app.services.images import ImageStore
from app.services.normalization import normalize_text
from app.services.pdf_parser import (
    PdfError,
    extract_pdf_reference,
    probe_text_layer,
    render_pdf,
)
from tests.conftest import make_image_pdf, make_scanned_pdf, make_text_pdf

# --------------------------------------------------------------------------- #
#  text layer probing
# --------------------------------------------------------------------------- #


def test_text_pdf_has_a_text_layer(tmp_path) -> None:
    path = make_text_pdf(tmp_path / "digital.pdf", ["Договор поставки № 42"])
    probe = probe_text_layer(path, min_chars=5)
    assert probe.page_count == 1
    assert probe.has_text_layer is True
    assert probe.text_chars > 0


def test_scanned_pdf_has_no_text_layer(tmp_path) -> None:
    path = make_scanned_pdf(tmp_path / "scan.pdf")
    probe = probe_text_layer(path, min_chars=5)
    assert probe.page_count == 1
    assert probe.has_text_layer is False
    assert probe.text_chars == 0


def test_probe_counts_pages(tmp_path) -> None:
    path = make_text_pdf(tmp_path / "multi.pdf", ["строка"], pages=3)
    assert probe_text_layer(path, min_chars=5).page_count == 3


def test_broken_pdf_raises(tmp_path) -> None:
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.7 not really a pdf")
    with pytest.raises(PdfError):
        probe_text_layer(broken)


# --------------------------------------------------------------------------- #
#  rendering
# --------------------------------------------------------------------------- #


def test_render_scales_with_dpi(tmp_path) -> None:
    path = make_text_pdf(tmp_path / "digital.pdf", ["Текст"])
    low = render_pdf(path, dpi=72)[0]
    high = render_pdf(path, dpi=144)[0]
    assert high.width > low.width
    # A4-ish page at 72 dpi is ~595 px wide
    assert 590 <= low.width <= 600


def test_render_respects_max_pages(tmp_path) -> None:
    path = make_text_pdf(tmp_path / "multi.pdf", ["строка"], pages=4)
    assert len(render_pdf(path, dpi=72, max_pages=2)) == 2


# --------------------------------------------------------------------------- #
#  reference extraction
# --------------------------------------------------------------------------- #


def test_extract_text_reference(tmp_path) -> None:
    store = ImageStore(tmp_path / "data")
    path = make_text_pdf(
        tmp_path / "digital.pdf", ["Договор поставки № 42", "Итого: 1 200,00 руб."]
    )

    result = extract_pdf_reference(
        path,
        document_type=DocumentType.text_only,
        session_id="s1",
        store=store,
        dpi=72,
    )

    document = result.document
    assert document.document_type is DocumentType.text_only
    assert len(document.pages) == 1
    assert document.pages[0].blocks
    assert all(b.type is BlockType.text for b in document.pages[0].blocks)
    # MuPDF emits non-breaking spaces between words; normalization handles it
    text = normalize_text(document.metric_text())
    assert "договор поставки" in text
    assert "1 200,00" in text
    # ids are assigned: p1-001-text
    assert document.pages[0].blocks[0].id.startswith("p1-001-")


def test_extract_reference_for_text_only_skips_images(tmp_path) -> None:
    store = ImageStore(tmp_path / "data")
    path = make_image_pdf(tmp_path / "with-image.pdf")

    document = extract_pdf_reference(
        path,
        document_type=DocumentType.text_only,
        session_id="s2",
        store=store,
        dpi=72,
    ).document

    assert document.images() == []
    assert document.tables() == []
    assert "figure 1" in normalize_text(document.metric_text())
    # no crops are produced for a text_only reference
    assert list((tmp_path / "data" / "images" / "s2").glob("*")) == []


def test_extract_images_for_full_document_type(tmp_path) -> None:
    store = ImageStore(tmp_path / "data")
    path = make_image_pdf(tmp_path / "with-image.pdf", image_size=(400, 300))

    result = extract_pdf_reference(
        path,
        document_type=DocumentType.text_tables_images,
        session_id="s3",
        store=store,
        dpi=72,
    )
    document = result.document

    images = document.images()
    assert len(images) == 1
    image = images[0]
    assert image.url and image.url.startswith("/static/images/s3/")
    assert image.content is None  # pictures are never transcribed
    assert image.bbox is not None and len(image.bbox) == 4
    assert image.bbox[2] > 0 and image.bbox[3] > 0

    stored = ImageStore.resolve_url(image.url, tmp_path / "data")
    assert stored is not None and stored.exists()

    # a page render is produced so the UI can show the source page
    assert result.rendered_pages
    assert "figure 1" in normalize_text(document.metric_text())


def test_blocks_are_sorted_in_reading_order(tmp_path) -> None:
    """The top paragraph must be first after reading-order sorting."""
    import pymupdf

    store = ImageStore(tmp_path / "data")
    path = tmp_path / "layout.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 500), "Bottom paragraph", fontsize=12)
    page.insert_text((72, 60), "Top heading", fontsize=12)
    document.save(str(path))
    document.close()

    result = extract_pdf_reference(
        path,
        document_type=DocumentType.text_only,
        session_id="s4",
        store=store,
        dpi=72,
    )
    tops = [b.bbox[1] for b in result.document.pages[0].blocks if b.bbox]
    assert tops == sorted(tops)
    first = normalize_text(result.document.pages[0].blocks[0].content or "")
    assert "top heading" in first


def test_page_limit_produces_a_warning(tmp_path) -> None:
    store = ImageStore(tmp_path / "data")
    path = make_text_pdf(tmp_path / "multi.pdf", ["строка"], pages=4)

    result = extract_pdf_reference(
        path,
        document_type=DocumentType.text_only,
        session_id="s5",
        store=store,
        dpi=72,
        max_pages=2,
    )
    assert len(result.document.pages) == 2
    assert any("страниц" in warning for warning in result.warnings)
