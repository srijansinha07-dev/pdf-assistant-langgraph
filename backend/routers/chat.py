"""
routers/chat.py
───────────────
/api/chat — answer questions about a document.
Returns structured JSON with answer + sources.

Now powered by a LangGraph multi-node RAG pipeline
(services/langgraph_chat.py).  API contract is unchanged.
"""
from __future__ import annotations

from fastapi import Header
from fastapi import APIRouter, HTTPException

from models import (
    ChatRequest, ChatResponse, ConfidenceLevel,
    IndexStatus, QueryType, Source,
)
from services import docstore

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest,x_user_id: str = Header(...)):
    # ── Validate document ─────────────────────────────────────────────────
    info = docstore.get_info(req.doc_id)
    if not info:
        raise HTTPException(404, "Document not found.")
    if info.user_id != x_user_id:
        raise HTTPException(403,"Unauthorized.")
    if info.status != IndexStatus.READY:
        raise HTTPException(400, f"Document is not ready (status: {info.status}).")

    chunks = docstore.get_chunks(req.doc_id)
    pages  = docstore.get_pages(req.doc_id)

    # ── Run LangGraph pipeline ────────────────────────────────────────────
    # Lazy import keeps startup memory low (langgraph not loaded until first call)
    from services.langgraph_chat import run_chat_graph

    result = run_chat_graph(
        doc_id=req.doc_id,
        query=req.query,
        chunks_all=chunks,
        pages_all=pages,
        doc_info=info,
    )

    answer            = result["answer"]
    query_type        = result["query_type"] or QueryType.CONCEPT
    retrieved_chunks  = result["retrieved_chunks"]

    # ── Build sources (same logic as before) ─────────────────────────────
    sources = []
    for c in retrieved_chunks:
        sources.append(Source(
            doc_id=req.doc_id,
            doc_name=info.name,
            page=c.page,
            text=c.text[:400] + ("…" if len(c.text) > 400 else ""),
            ocr_sourced=c.ocr_sourced,
            confidence=_confidence(c.score, c.ocr_sourced),
        ))

    return ChatResponse(
        answer=answer,
        query_type=query_type,
        sources=sources,
    )


# ── Helpers ────────────────────────────────────────────────────────────────

def _confidence(score: float, ocr_sourced: bool) -> ConfidenceLevel:
    base = score
    if ocr_sourced:
        base -= 0.1   # slight penalty for OCR uncertainty
    if base >= 0.6:
        return ConfidenceLevel.HIGH
    if base >= 0.3:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.LOW
