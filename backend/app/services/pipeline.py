"""Document import pipeline: store -> parse (OCR/PDF/DOCX/XLSX/audio/text) -> extract -> NEEDS_REVIEW.

Idempotent and restart-safe: re-processing a document is harmless; documents stuck in
QUEUED/ANALYZING after a crash are re-queued on startup.
"""
import hashlib
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import SessionLocal
from ..models import Document
from .extraction import engine, parsers

log = logging.getLogger("pipeline")


def store_bytes(data: bytes) -> tuple[str, str]:
    sha = hashlib.sha256(data).hexdigest()
    path = Path(settings.storage_dir) / sha[:2] / sha
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)  # atomic: never leave a half-written original
    return sha, str(path)


def register_upload(db: Session, data: bytes, filename: str, procurement_id: int | None, user_id: int) -> tuple[Document, bool]:
    """Returns (document, created). Same bytes in the same procurement => existing doc (idempotent)."""
    kind = parsers.sniff(data, filename)  # raises UnsupportedFile
    sha, path = store_bytes(data)
    existing = db.scalar(select(Document).where(Document.sha256 == sha, Document.procurement_id == procurement_id))
    if existing:
        return existing, False
    doc = Document(procurement_id=procurement_id, filename=filename[:500], kind=kind, sha256=sha, path=path, status="QUEUED", uploaded_by=user_id)
    db.add(doc)
    db.flush()
    return doc, True


def process_document(doc_id: int) -> None:
    db = SessionLocal()
    try:
        doc = db.get(Document, doc_id)
        if not doc or doc.status == "PROCESSED":
            return
        doc.status, doc.error = "ANALYZING", None
        db.commit()
        try:
            data = Path(doc.path).read_bytes()
            parsed = parsers.parse(data, doc.filename)
            doc.extracted_text = parsed.text[:500_000]
            result = engine.extract(parsed)
            result["blocks_total"] = len(parsed.blocks)
            doc.extraction = result
            doc.status = "NEEDS_REVIEW"  # always: a human verifies before anything is used
            if not result["lines"]:
                result["warnings"].append("no_lines_extracted")
        except parsers.EngineUnavailable as e:
            doc.status, doc.error = "ERROR", str(e)
        except parsers.UnsupportedFile as e:
            doc.status, doc.error = "ERROR", f"Файл не принят: {e}"
        except Exception as e:
            log.exception("processing failed for document %s", doc_id)
            doc.status, doc.error = "ERROR", f"Не удалось обработать файл ({type(e).__name__}). Попробуйте ещё раз или введите данные вручную"
        db.commit()
    finally:
        db.close()


def requeue_stuck() -> list[int]:
    db = SessionLocal()
    try:
        ids = [d.id for d in db.scalars(select(Document).where(Document.status.in_(["QUEUED", "ANALYZING"])))]
        return ids
    finally:
        db.close()
