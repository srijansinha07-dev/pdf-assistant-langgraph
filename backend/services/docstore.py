"""
services/docstore.py
────────────────────
In-memory document registry.
Maps doc_id → { metadata, pages, chunks }.
Persists metadata to a simple JSON file so it survives restarts.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from config import UPLOAD_DIR
from models import Chunk, DocumentInfo, IndexStatus

_META_FILE = UPLOAD_DIR / "documents.json"

# ── In-memory store ────────────────────────────────────────────────────────
# doc_id → {
#   "info"   : DocumentInfo dict,
#   "pages"  : list[dict],       # raw extracted pages
#   "chunks" : list[Chunk],      # chunked text
# }
_store: dict[str, dict] = {}


# ── Public API ─────────────────────────────────────────────────────────────

def new_doc_id() -> str:
    return uuid.uuid4().hex[:12]


def register(
    doc_id:    str,
    name:      str,
    pdf_path:  str,
    pages:     int,
) -> DocumentInfo:
    info = DocumentInfo(
        doc_id=doc_id,
        name=name,
        pages=pages,
        status=IndexStatus.PENDING,
        ocr_pages=0,
        chunks=0,
        upload_time=datetime.now(timezone.utc).isoformat(),
        suggestions=[],
    )
    _store[doc_id] = {
        "info": info,
        "pages": [],
        "chunks": [],
        "pdf_path": pdf_path,
        "suggestions": [],
        }
    _save()
    return info


def set_status(doc_id: str, status: IndexStatus):
    if doc_id in _store:
        _store[doc_id]["info"].status = status
        _save()


def set_pages(doc_id: str, pages: list[dict]):
    if doc_id in _store:
        ocr_count = sum(1 for p in pages if p.get("ocr_used"))
        _store[doc_id]["pages"]                = pages
        _store[doc_id]["info"].ocr_pages       = ocr_count
        _save()


def set_chunks(doc_id: str, chunks: list[Chunk]):
    if doc_id in _store:
        _store[doc_id]["chunks"]       = chunks
        _store[doc_id]["info"].chunks  = len(chunks)
        _save()


def get_info(doc_id: str) -> DocumentInfo | None:
    entry = _store.get(doc_id)
    return entry["info"] if entry else None


def get_pages(doc_id: str) -> list[dict]:
    return _store.get(doc_id, {}).get("pages", [])


def get_chunks(doc_id: str) -> list[Chunk]:
    return _store.get(doc_id, {}).get("chunks", [])

def get_suggestions(doc_id: str) -> list[str]:
    return _store.get(doc_id, {}).get("suggestions", [])


def set_suggestions(doc_id: str, suggestions: list[str]):
    if doc_id in _store:
        _store[doc_id]["suggestions"] = suggestions
        _store[doc_id]["info"].suggestions = suggestions
        _save()


def get_pdf_path(doc_id: str) -> str | None:
    return _store.get(doc_id, {}).get("pdf_path")


def list_docs() -> list[DocumentInfo]:
    return [v["info"] for v in _store.values()]


def delete_doc(doc_id: str):
    _store.pop(doc_id, None)
    _save()


def load_from_disk():
    """Restore metadata from JSON on startup (pages/chunks are not persisted)."""
    if not _META_FILE.exists():
        return
    try:
        data = json.loads(_META_FILE.read_text())
        for doc_id, entry in data.items():
            info = DocumentInfo(**entry["info"])
            # Mark as error if pdf is missing (user deleted file)
            pdf_path = entry.get("pdf_path", "")
            if not Path(pdf_path).exists():
                info.status = IndexStatus.ERROR
            _store[doc_id] = {
                "info":     info,
                "pages":    [],
                "chunks":   [],
                "pdf_path": pdf_path,
            }
    except Exception:
        pass


# ── Internal ───────────────────────────────────────────────────────────────

def _save():
    try:
        data = {
            doc_id: {
                "info":     v["info"].model_dump(),
                "pdf_path": v.get("pdf_path", ""),
            }
            for doc_id, v in _store.items()
        }
        _META_FILE.write_text(json.dumps(data, indent=2))
    except Exception:
        pass
