"""
routers/documents.py
────────────────────
/api/documents — upload, list, delete, page preview
"""
from __future__ import annotations

import asyncio
import base64
import shutil
from pathlib import Path

from fastapi import Header
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from config import UPLOAD_DIR
from models import DocumentInfo, IndexStatus, PagePreviewResponse, UploadResponse
from services import docstore

router = APIRouter(prefix="/api/documents", tags=["documents"])


# ── Upload ─────────────────────────────────────────────────────────────────

@router.post("", response_model=UploadResponse)
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    x_user_id: str = Header(...),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted.")

    doc_id   = docstore.new_doc_id()
    pdf_path = UPLOAD_DIR / f"{doc_id}.pdf"

    # Save file
    with pdf_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    # Quick page count via PyMuPDF
    import fitz
    doc   = fitz.open(str(pdf_path))
    pages = len(doc)
    doc.close()

    info = docstore.register(
        doc_id=doc_id,
        user_id=x_user_id,
        name=file.filename,
        pdf_path=str(pdf_path),
        pages=pages,
    )

    # Index in background
    background_tasks.add_task(_index_document, doc_id, str(pdf_path))

    return UploadResponse(
        doc_id=doc_id,
        name=file.filename,
        pages=pages,
        status=IndexStatus.PROCESSING,
    )


# ── List ───────────────────────────────────────────────────────────────────

@router.get("", response_model=list[DocumentInfo])
async def list_documents( x_user_id: str = Header(...)):
    return docstore.list_docs(x_user_id)


# ── Single document ────────────────────────────────────────────────────────

@router.get("/{doc_id}", response_model=DocumentInfo)
async def get_document(doc_id: str,x_user_id: str = Header(...)):
    info = docstore.get_info(doc_id)
    if not info:
        raise HTTPException(404, "Document not found.")
    if info.user_id != x_user_id:
        raise HTTPException(403,"Unauthorized.")
    return info


# ── Delete ─────────────────────────────────────────────────────────────────

@router.delete("/{doc_id}")
async def delete_document(
    doc_id: str,
    x_user_id: str = Header(...)
):
    from services import vectorstore
    from services.retriever import (
        invalidate_bm25
    )

    # ── Validate ownership ─────────────────────
    info = docstore.get_info(
        doc_id
    )

    if not info:
        raise HTTPException(
            404,
            "Document not found."
        )

    if info.user_id != x_user_id:
        raise HTTPException(
            403,
            "Unauthorized."
        )

    # ── Delete PDF file ────────────────────────
    pdf_path = (
        docstore.get_pdf_path(
            doc_id
        )
    )

    if pdf_path:
        Path(pdf_path).unlink(
            missing_ok=True
        )

    # ── Delete embeddings/cache ───────────────
    vectorstore.delete_collection(
        doc_id
    )

    invalidate_bm25(
        doc_id
    )

    # ── Remove doc from registry ──────────────
    docstore.delete_doc(
        doc_id
    )

    return {
        "ok": True
    }


# ── Page preview ───────────────────────────────────────────────────────────

@router.get("/{doc_id}/pages/{page_num}", response_model=PagePreviewResponse)
async def get_page(doc_id: str, page_num: int):
    from services.extractor import render_page_image
    info = docstore.get_info(doc_id)
    if not info:
        raise HTTPException(404, "Document not found.")
    if page_num < 1 or page_num > info.pages:
        raise HTTPException(400, f"Page {page_num} out of range (1–{info.pages}).")

    pages    = docstore.get_pages(doc_id)
    page_map = {p["page_num"]: p for p in pages}
    pd       = page_map.get(page_num, {})

    # Render image
    pdf_path = docstore.get_pdf_path(doc_id)
    img_bytes = render_page_image(pdf_path, page_num) if pdf_path else None
    img_b64   = base64.b64encode(img_bytes).decode() if img_bytes else None

    return PagePreviewResponse(
        doc_id=doc_id,
        page=page_num,
        text=pd.get("text", ""),
        ocr_used=pd.get("ocr_used", False),
        image_b64=img_b64,
    )


# ── Background indexing task ───────────────────────────────────────────────

def _index_document(doc_id: str, pdf_path: str):
    try:
        print("1. START INDEX")

        # Lazy imports to avoid startup OOM
        from services.chunker import chunk_pages
        print("2. CHUNKER IMPORTED")

        from services.extractor import extract_pdf
        print("3. EXTRACTOR IMPORTED")

        from services import vectorstore
        print("4. VECTORSTORE IMPORTED")

        # Set processing state
        docstore.set_status(
            doc_id,
            IndexStatus.PROCESSING
        )

        # Extract PDF
        print("5. EXTRACTING PDF")
        pages = extract_pdf(pdf_path)

        print("6. PAGES EXTRACTED")
        docstore.set_pages(
            doc_id,
            pages
        )

        # Chunk document
        print("7. CHUNKING")
        chunks = chunk_pages(
            pages,
            doc_id
        )

        print("8. CHUNKS READY")
        docstore.set_chunks(
            doc_id,
            chunks
        )

        # ── Smart suggestions ─────────────────────
        preview_text = " ".join(
            c.text for c in chunks[:8]
        ).lower()[:4000]

        filename = pdf_path.lower()
        suggestions = []

        # Legal / agreements
        if any(
            word in preview_text
            for word in [
                "agreement",
                "party",
                "parties",
                "clause",
                "whereas",
                "liable",
                "liability",
                "governing law",
                "payment",
                "terms",
                "contract",
                "legal",
                "shall",
                "hereby",
                "jurisdiction",
                "obligation",
            ]
        ) or any(
            word in filename
            for word in [
                "agreement",
                "contract",
                "legal",
                "law",
                "terms",
            ]
        ):
            suggestions = [
                "Summarize this agreement",
                "What are the important clauses?",
                "What obligations are mentioned?",
                "Explain the key terms",
            ]

        # Resume / CV
        elif any(
            word in preview_text
            for word in [
                "experience",
                "education",
                "skills",
                "internship",
                "projects",
                "certifications",
                "linkedin",
                "resume",
                "curriculum vitae",
            ]
        ):
            suggestions = [
                "Summarize this profile",
                "What skills are highlighted?",
                "What projects are mentioned?",
                "Summarize the experience",
            ]

        # Research papers
        elif any(
            word in preview_text
            for word in [
                "abstract",
                "methodology",
                "results",
                "conclusion",
                "experiment",
                "study",
                "literature review",
                "research",
            ]
        ):
            suggestions = [
                "Summarize the key findings",
                "Explain the methodology",
                "What are the main contributions?",
                "Summarize this paper",
            ]

        # Technical / textbook
        elif any(
            word in preview_text
            for word in [
                "equation",
                "formula",
                "theorem",
                "hypothesis",
                "voltage",
                "current",
                "resistance",
                "semiconductor",
                "algorithm",
                "probability",
                "distribution",
                "regression",
                "statistics",
                "mean",
                "variance",
            ]
        ):
            suggestions = [
                "Explain the key concepts",
                "Find important formulas",
                "Summarize this chapter",
                "Quiz me on this topic",
            ]

        # Default
        else:
            suggestions = [
                "Summarize this document",
                "What are the key concepts?",
                "Explain the main topics",
                "What should I know from this PDF?",
            ]

        # Save suggestions
        info = docstore.get_info(doc_id)

        if info:
            info.suggestions = suggestions[:4]

        # Index chunks
        print("9. INDEXING CHUNKS")
        vectorstore.index_chunks(
            doc_id,
            chunks
        )

        print("10. INDEXING DONE")

        # Mark ready
        docstore.set_status(
            doc_id,
            IndexStatus.READY
        )

    except Exception as e:
        print(
            f"[ERROR] Indexing {doc_id}: {e}"
        )

        docstore.set_status(
            doc_id,
            IndexStatus.ERROR
        )