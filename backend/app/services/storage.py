"""Filesystem-backed session store.

Layout (no database, no extra infrastructure):

    data/
      images/{session_id}/{tag}-{sha1}.png     -> /static/images/{sid}/...
      {session_id}/
        session.json                           session metadata
        reference.<pdf|docx>                   uploaded file A
        recognized.<pdf|docx>                  uploaded file B
        reference.json                         reference DocumentJSON
        recognized.json                        recognized DocumentJSON
        recognition.json                       GLM usage / timing
        metrics.json                           metrics report
        pages/reference/page-0001.png          reference page renders
        pages/recognized/page-0001.png         scanned page renders
"""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from app.schemas.document import DocumentJSON, DocumentSource, FileInfo
from app.schemas.metrics import MetricsReport
from app.schemas.recognition import RecognitionMeta
from app.schemas.session import SessionMeta
from app.services.images import STATIC_PREFIX

SESSION_FILE = "session.json"
REFERENCE_JSON = "reference.json"
RECOGNIZED_JSON = "recognized.json"
RECOGNITION_JSON = "recognition.json"
METRICS_JSON = "metrics.json"

SOURCE_TO_JSON = {
    DocumentSource.reference: REFERENCE_JSON,
    DocumentSource.recognized: RECOGNIZED_JSON,
}


def new_session_id() -> str:
    return f"{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:8]}"


class SessionNotFound(FileNotFoundError):
    def __init__(self, session_id: str) -> None:
        super().__init__(f"Сессия «{session_id}» не найдена.")
        self.session_id = session_id


class SessionStore:
    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)

    # -- paths ------------------------------------------------------------- #
    def dir(self, session_id: str) -> Path:
        path = self.data_dir / session_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def pages_dir(self, session_id: str, role: str) -> Path:
        path = self.dir(session_id) / "pages" / role
        path.mkdir(parents=True, exist_ok=True)
        return path

    def exists(self, session_id: str) -> bool:
        return (self.data_dir / session_id / SESSION_FILE).exists()

    def static_url(self, path: Path) -> str:
        return f"{STATIC_PREFIX}/{(path).resolve().relative_to(self.data_dir).as_posix()}"

    # -- session metadata -------------------------------------------------- #
    def create(self, document_type) -> SessionMeta:
        meta = SessionMeta(session_id=new_session_id(), document_type=document_type)
        self.write_meta(meta)
        return meta

    def read_meta(self, session_id: str) -> SessionMeta:
        path = self.data_dir / session_id / SESSION_FILE
        if not path.exists():
            raise SessionNotFound(session_id)
        return SessionMeta.model_validate_json(path.read_text("utf-8"))

    def write_meta(self, meta: SessionMeta) -> SessionMeta:
        self.dir(meta.session_id).joinpath(SESSION_FILE).write_text(
            meta.touch().model_dump_json(indent=2), encoding="utf-8"
        )
        return meta

    # -- uploads ----------------------------------------------------------- #
    def save_upload(
        self, session_id: str, role: str, filename: str, blob: bytes, suffix: str
    ) -> FileInfo:
        target = self.dir(session_id) / f"{role}{suffix}"
        target.write_bytes(blob)
        return FileInfo(
            filename=filename,
            stored_path=str(target),
            size_bytes=len(blob),
            extension=suffix,
            mime_type="",
            sha256=hashlib.sha256(blob).hexdigest(),
        )

    def upload_path(self, session_id: str, role: str) -> Path | None:
        for candidate in sorted(self.dir(session_id).glob(f"{role}.*")):
            if candidate.suffix.lower() in {".pdf", ".docx"}:
                return candidate
        return None

    # -- documents --------------------------------------------------------- #
    def document_path(self, session_id: str, source: DocumentSource | str) -> Path:
        source_enum = DocumentSource(source) if isinstance(source, str) else source
        return self.data_dir / session_id / SOURCE_TO_JSON[source_enum]

    def save_document(self, document: DocumentJSON) -> Path:
        target = self.document_path(document.session_id, document.source)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(document.model_dump_json(indent=2), encoding="utf-8")
        return target

    def load_document(
        self, session_id: str, source: DocumentSource | str
    ) -> DocumentJSON | None:
        path = self.document_path(session_id, source)
        if not path.exists():
            return None
        return DocumentJSON.model_validate_json(path.read_text("utf-8"))

    def delete_document(self, session_id: str, source: DocumentSource | str) -> None:
        self.document_path(session_id, source).unlink(missing_ok=True)

    # -- recognition / metrics sidecars ------------------------------------ #
    def _write_json(self, session_id: str, filename: str, payload: str) -> Path:
        target = self.dir(session_id) / filename
        target.write_text(payload, encoding="utf-8")
        return target

    def _read_json(self, session_id: str, filename: str) -> dict | None:
        path = self.data_dir / session_id / filename
        if not path.exists():
            return None
        return json.loads(path.read_text("utf-8"))

    def save_recognition(self, meta: RecognitionMeta) -> None:
        self._write_json(
            meta.session_id, RECOGNITION_JSON, meta.model_dump_json(indent=2)
        )

    def load_recognition(self, session_id: str) -> RecognitionMeta | None:
        payload = self._read_json(session_id, RECOGNITION_JSON)
        return RecognitionMeta.model_validate(payload) if payload else None

    def save_metrics(self, report: MetricsReport) -> None:
        self._write_json(
            report.session_id, METRICS_JSON, report.model_dump_json(indent=2)
        )

    def load_metrics(self, session_id: str) -> MetricsReport | None:
        payload = self._read_json(session_id, METRICS_JSON)
        return MetricsReport.model_validate(payload) if payload else None

    def delete_metrics(self, session_id: str) -> None:
        (self.data_dir / session_id / METRICS_JSON).unlink(missing_ok=True)

    # -- page renders ------------------------------------------------------ #
    def save_page_renders(self, session_id: str, role: str, pages) -> list[str]:
        """Persist page bitmaps of file A or B and return their static URLs."""
        directory = self.pages_dir(session_id, role)
        urls: list[str] = []
        for page in pages:
            filename = f"page-{page.page_number:04d}.png"
            page.image.save(directory / filename, format="PNG", optimize=True)
            urls.append(self.static_url(directory / filename))
        return urls

    def page_render_urls(self, session_id: str, role: str) -> list[str]:
        directory = self.data_dir / session_id / "pages" / role
        if not directory.exists():
            return []
        return [self.static_url(path) for path in sorted(directory.glob("page-*.png"))]

    # -- listing / cleanup ------------------------------------------------- #
    def list_sessions(self) -> list[SessionMeta]:
        metas: list[SessionMeta] = []
        for path in sorted(self.data_dir.glob(f"*/{SESSION_FILE}")):
            try:
                metas.append(SessionMeta.model_validate_json(path.read_text("utf-8")))
            except Exception:  # pragma: no cover - hand-edited/broken file
                continue
        return sorted(metas, key=lambda m: m.created_at, reverse=True)

    def delete_session(self, session_id: str) -> None:
        directory = self.data_dir / session_id
        if directory.exists():
            shutil.rmtree(directory, ignore_errors=True)
        images = self.data_dir / "images" / session_id
        if images.exists():
            shutil.rmtree(images, ignore_errors=True)
