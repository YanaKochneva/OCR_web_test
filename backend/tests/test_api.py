"""End-to-end API tests: upload -> recognize -> metrics -> results.

The GLM client runs in mock mode (`GLM_MOCK=true`), so no API key and no network
access are needed.  The pipeline, the JSON schemas and the readiness gates are
all exercised for real.
"""

from __future__ import annotations

from app.services.images import ImageStore
from tests.conftest import make_scanned_pdf, make_text_pdf


def _upload(client, document_type: str, reference_path, recognized_path):
    with reference_path.open("rb") as reference_file, recognized_path.open(
        "rb"
    ) as recognized_file:
        return client.post(
            "/api/upload",
            data={"document_type": document_type},
            files={
                "reference": (reference_path.name, reference_file, "application/pdf"),
                "recognized": (recognized_path.name, recognized_file, "application/pdf"),
            },
        )


def _all_text(document: dict) -> str:
    chunks = []
    for page in document["pages"]:
        for block in page["blocks"]:
            if block["type"] == "text":
                chunks.append(block.get("content") or "")
            elif block["type"] == "table":
                for row in block.get("rows") or []:
                    chunks.extend(row)
    return "\n".join(chunks)


def test_health_and_document_types(api_client) -> None:
    health = api_client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["mock_mode"] is True

    types = api_client.get("/api/document-types")
    assert types.status_code == 200
    payload = types.json()
    ids = [item["id"] for item in payload["document_types"]]
    assert ids == ["text_only", "text_tables", "text_tables_images"]
    entities = {item["id"]: item["entities"] for item in payload["document_types"]}
    assert entities["text_only"] == {"text": True, "tables": False, "images": False}
    assert entities["text_tables_images"] == {
        "text": True,
        "tables": True,
        "images": True,
    }


def test_full_flow_text_only(api_client, tmp_path) -> None:
    reference = make_text_pdf(
        tmp_path / "etalon.pdf", ["Договор поставки № 42", "Итого: 1 200,00 руб."]
    )
    recognized = make_scanned_pdf(tmp_path / "scan.pdf")

    upload = _upload(api_client, "text_only", reference, recognized)
    assert upload.status_code == 200, upload.text
    body = upload.json()
    session_id = body["session_id"]

    assert body["reference"]["ready"] is True
    assert body["recognized"]["ready"] is False
    assert body["reference"]["document"]["source"] == "reference"
    assert "Договор" in _all_text(body["reference"]["document"])

    # metrics must be refused before recognition has run
    early = api_client.post("/api/metrics", json={"session_id": session_id})
    assert early.status_code == 409
    assert "распознанный JSON" in early.json()["detail"]

    recognize = api_client.post("/api/recognize", json={"session_id": session_id})
    assert recognize.status_code == 200, recognize.text
    recognized_body = recognize.json()
    assert recognized_body["document"]["source"] == "recognized"
    assert recognized_body["meta"]["usage"]["total_tokens"] > 0
    assert recognized_body["meta"]["request_seconds"] >= 0

    metrics = api_client.post("/api/metrics", json={"session_id": session_id})
    assert metrics.status_code == 200, metrics.text
    report = metrics.json()["report"]
    # CER is not bounded by 1: the mock text is much longer than the reference
    assert report["overall"]["cer"] >= 0.0
    assert report["performance"]["total_tokens"] > 0
    assert report["performance"]["pages_processed"] == 1
    assert report["per_page"][0]["page_number"] == 1
    assert report["accounted_entities"] == ["text"]

    results = api_client.get(f"/api/results/{session_id}")
    assert results.status_code == 200
    payload = results.json()
    assert payload["reference_json_ready"] is True
    assert payload["recognized_json_ready"] is True
    assert payload["metrics_ready"] is True
    assert payload["metrics"]["overall"]["cer"] == report["overall"]["cer"]


def test_metrics_gate_depends_on_both_jsons(api_client, tmp_path) -> None:
    reference = make_text_pdf(tmp_path / "et.pdf", ["Текст"])
    recognized = make_scanned_pdf(tmp_path / "sc.pdf")

    session_id = _upload(api_client, "text_only", reference, recognized).json()[
        "session_id"
    ]
    state = api_client.get(f"/api/results/{session_id}").json()
    assert state["reference_json_ready"] is True
    assert state["recognized_json_ready"] is False
    assert state["metrics_ready"] is False

    api_client.post("/api/recognize", json={"session_id": session_id})
    state = api_client.get(f"/api/results/{session_id}").json()
    assert state["recognized_json_ready"] is True
    assert state["metrics_ready"] is False  # metrics not computed yet

    api_client.post("/api/metrics", json={"session_id": session_id})
    state = api_client.get(f"/api/results/{session_id}").json()
    assert state["metrics_ready"] is True


def test_images_are_saved_as_crops_not_text(api_client, tmp_path) -> None:
    reference = make_text_pdf(tmp_path / "et.pdf", ["Рисунок 1 - схема"])
    recognized = make_scanned_pdf(tmp_path / "sc.pdf")

    session_id = _upload(api_client, "text_tables_images", reference, recognized).json()[
        "session_id"
    ]
    recognize = api_client.post("/api/recognize", json={"session_id": session_id})
    assert recognize.status_code == 200

    payload = recognize.json()["document"]
    images = [
        block
        for page in payload["pages"]
        for block in page["blocks"]
        if block["type"] == "image"
    ]
    assert images, "mock client must produce an image block for this document type"
    for image in images:
        assert image["url"].startswith("/static/images/")
        assert image["content"] is None  # never transcribed as text
        # the crop is stored on disk and reachable through the static mount
        stored = ImageStore.resolve_url(image["url"], api_client.store.data_dir)
        assert stored is not None and stored.exists()
        assert stored.stat().st_size > 0


def test_text_layer_warning_for_file_b(api_client, tmp_path) -> None:
    reference = make_text_pdf(tmp_path / "et.pdf", ["Текст эталона"])
    recognized = make_text_pdf(tmp_path / "digital-copy.pdf", ["Текст копии"])

    response = _upload(api_client, "text_only", reference, recognized)
    assert response.status_code == 200
    warnings = response.json()["recognized"]["warnings"]
    assert any("текстовый слой" in warning for warning in warnings)


def test_upload_rejects_wrong_format(api_client, tmp_path) -> None:
    reference = make_text_pdf(tmp_path / "et.pdf", ["Текст"])
    bad = tmp_path / "notes.txt"
    bad.write_text("просто текст", encoding="utf-8")

    response = _upload(api_client, "text_only", reference, bad)
    assert response.status_code == 422
    assert "не поддерживается" in response.json()["detail"]


def test_upload_rejects_unknown_document_type(api_client, tmp_path) -> None:
    reference = make_text_pdf(tmp_path / "et.pdf", ["Текст"])
    recognized = make_scanned_pdf(tmp_path / "sc.pdf")

    response = _upload(api_client, "text_everything", reference, recognized)
    assert response.status_code == 422
    assert "Неизвестный тип документа" in response.json()["detail"]


def test_recognize_rejects_docx_recognized_file(api_client, tmp_path) -> None:
    from tests.conftest import make_docx

    reference = make_docx(tmp_path / "et.docx", ["Текст эталона"])
    recognized = make_docx(tmp_path / "copy.docx", ["Текст копии"])

    with reference.open("rb") as reference_file, recognized.open("rb") as recognized_file:
        upload = api_client.post(
            "/api/upload",
            data={"document_type": "text_only"},
            files={
                "reference": (reference.name, reference_file, "application/octet-stream"),
                "recognized": (
                    recognized.name,
                    recognized_file,
                    "application/octet-stream",
                ),
            },
        )
    assert upload.status_code == 200, upload.text
    body = upload.json()
    assert any("PDF" in warning for warning in body["recognized"]["warnings"])

    recognize = api_client.post(
        "/api/recognize", json={"session_id": body["session_id"]}
    )
    assert recognize.status_code == 422
    assert "PDF" in recognize.json()["detail"]


def test_sessions_list_and_delete(api_client, tmp_path) -> None:
    reference = make_text_pdf(tmp_path / "et.pdf", ["Текст"])
    recognized = make_scanned_pdf(tmp_path / "sc.pdf")
    session_id = _upload(api_client, "text_only", reference, recognized).json()[
        "session_id"
    ]

    listing = api_client.get("/api/sessions").json()["sessions"]
    assert any(item["session_id"] == session_id for item in listing)

    assert api_client.delete(f"/api/results/{session_id}").status_code == 200
    assert api_client.get(f"/api/results/{session_id}").status_code == 404
