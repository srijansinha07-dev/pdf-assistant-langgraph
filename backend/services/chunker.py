"""
services/chunker.py
───────────────────
Paragraph-based chunker that preserves formulas intact.
Never splits on fixed character count.
"""
from __future__ import annotations

import re

from models import Chunk
from services.extractor import has_formula, FORMULA_RE


def chunk_pages(pages: list[dict], doc_id: str) -> list[Chunk]:
    """
    Convert extracted pages into Chunk objects.

    Strategy:
    - Split on blank lines (paragraph breaks).
    - Keep formula-dense blocks intact regardless of size.
    - Carry the last sentence of each chunk as overlap into the next.
    - Store page number, doc_id, and OCR source flag on every chunk.
    """
    chunks: list[Chunk] = []
    idx           = 0
    last_sentence = ""
    cur_heading   = ""

    for page_data in pages:
        page_num = page_data["page_num"]
        text     = page_data["text"]
        ocr_used = page_data.get("ocr_used", False)

        # Update heading tracker
        for line in text.splitlines():
            s = line.strip()
            if _is_heading(s):
                cur_heading = s

        paragraphs = re.split(r'\n{2,}', text)
        buffer     = last_sentence

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            candidate = (buffer + "\n" + para).strip() if buffer else para

            # Keep formula blocks whole; small blocks can grow
            if _is_formula_block(candidate) or len(candidate) < 900:
                buffer = candidate
            else:
                if buffer:
                    chunks.append(_make(buffer, page_num, idx, doc_id, cur_heading, ocr_used))
                    idx += 1
                    last_sentence = _last_sentence(buffer)
                buffer = para

        if buffer:
            chunks.append(_make(buffer, page_num, idx, doc_id, cur_heading, ocr_used))
            idx += 1
            last_sentence = _last_sentence(buffer)

    return chunks


# ── Helpers ────────────────────────────────────────────────────────────────

def _make(text: str, page: int, idx: int, doc_id: str,
          heading: str, ocr_used: bool) -> Chunk:
    return Chunk(
        text=text,
        page=page,
        chunk_id=f"{doc_id}_chunk_{idx:05d}_p{page}",
        doc_id=doc_id,
        has_formula=has_formula(text),
        section_heading=heading,
        ocr_sourced=ocr_used,
    )


def _is_heading(line: str) -> bool:
    if not line or len(line) > 80:
        return False
    return (
        line.isupper()
        or line.endswith(':')
        or bool(re.match(r'^\d+(\.\d+)*\s+[A-Z]', line))
    )


def _is_formula_block(text: str) -> bool:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return False
    formula_count = sum(1 for l in lines if FORMULA_RE.search(l))
    return formula_count >= max(1, len(lines) // 2)


def _last_sentence(text: str) -> str:
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return parts[-1] if parts else ""
