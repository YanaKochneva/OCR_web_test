"""Tests for DOCX reference extraction and upload validation."""

from __future__ import annotations

import pytest

from app.schemas.document import BlockType, DocumentType
from app.services.docx_parser import extract_docx_reference
from app.services.images import ImageStore
from app.services.parsers import (
    UploadValidationError,
    detect_suffix,
    parse_reference,
    sniff_format,
    validate_upload,
)
from tests.conftest import make_docx, make_text_pdf


def test_docx_paragraphs_and_tables(tmp_path, table_rows) -> None:
    store = ImageStore(tmp_path / "data")
    path = make_docx(
        tmp_path / "doc.docx",
        ["Договор поставки № 42", "Итого: 1 200,00 руб."],
        table_rows=table_rows,
    )

    document = extract_docx_reference(
        path,
        document_type=DocumentType.text_tables,
        session_id="d1",
        store=store,
    ).document

    assert document.parser == "docx"
    assert len(document.pages) == 1
    kinds = [b.type for b in document.pages[0].blocks]
    assert BlockType.text in kinds
    assert BlockType.table in kinds

    tables = document.tables()
    assert tables[0].rows[1] == ["Болт М8", "12", "5,50"]

    text = document.metric_text()
    assert "Договор поставки" in text
    assert "Болт М8" in text


def test_docx_skips_tables_for_text_only(tmp_path, table_rows) -> None:
    store = ImageStore(tmp_path / "data")
    path = make_docx(tmp_path / "doc.docx", ["Только текст"], table_rows=table_rows)

    result = extract_docx_reference(
        path,
        document_type=DocumentType.text_only,
        session_id="d2",
        store=store,
    )
    assert result.document.tables() == []
    assert "Болт М8" not in result.document.metric_text()
    assert any("Таблицы DOCX пропущены" in w for w in result.warnings)


def test_docx_is_accepted_as_reference_via_dispatcher(tmp_path, test_settings) -> None:
    store = ImageStore(tmp_path / "data")
    path = make_docx(tmp_path / "doc.docx", ["Строка документа"])

    result = parse_reference(
        path,
        document_type=DocumentType.text_only,
        session_id="d3",
        store=store,
        settings=test_settings,
        suffix=".docx",
    )
    assert result.has_text_layer is True
    assert "Строка документа" in result.document.metric_text()


# --------------------------------------------------------------------------- #
#  validation
# --------------------------------------------------------------------------- #


def test_detect_suffix_uses_the_extension() -> None:
    assert detect_suffix("file.pdf") == ".pdf"
    assert detect_suffix("FILE.PDF") == ".pdf"
    assert detect_suffix("no_extension") == ""


def test_sniff_format_reads_magic_bytes() -> None:
    assert sniff_format(b"%PDF-1.7 ...") == ".pdf"
    assert sniff_format(b"PK\x03\x04rest") == ".docx"
    assert sniff_format(b"plain text") is None


def test_validate_rejects_unsupported_extension(test_settings) -> None:
    # the extension wins, even when the bytes happen to look like a PDF
    with pytest.raises(UploadValidationError) as exc:
        validate_upload("scan.txt", b"%PDF-1.7 ok", test_settings, role="Эталон")
    assert exc.value.code == "unsupported_format"


def test_validate_rejects_mime_mismatch(test_settings) -> None:
    with pytest.raises(UploadValidationError) as exc:
        validate_upload("fake.pdf", b"just text", test_settings, role="Эталон")
    assert exc.value.code == "mime_mismatch"


def test_validate_rejects_oversized_file(test_settings) -> None:
    blob = b"%PDF-1.7" + b"0" * (test_settings.max_upload_bytes + 1)
    with pytest.raises(UploadValidationError) as exc:
        validate_upload("big.pdf", blob, test_settings, role="Эталон")
    assert exc.value.code == "file_too_large"


def test_validate_rejects_empty_file(test_settings) -> None:
    with pytest.raises(UploadValidationError) as exc:
        validate_upload("empty.pdf", b"", test_settings, role="Эталон")
    assert exc.value.code == "empty_file"


def test_validate_probes_the_text_layer(tmp_path, test_settings) -> None:
    path = make_text_pdf(tmp_path / "digital.pdf", ["Договор поставки № 42"])
    probe = validate_upload(
        "digital.pdf", path.read_bytes(), test_settings, role="Эталон"
    )
    assert probe.suffix == ".pdf"
    assert probe.mime_type == "application/pdf"
    assert probe.has_text_layer is True
    assert probe.page_count == 1
