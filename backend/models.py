"""
models.py — Pydantic schemas and internal dataclasses.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from pydantic import BaseModel


# ── Enums ──────────────────────────────────────────────────────────────────

class QueryType(str, Enum):
    PAGE    = "page"
    FORMULA = "formula"
    CONCEPT = "concept"
    EXACT   = "exact"

class IndexStatus(str, Enum):
    PENDING    = "pending"
    PROCESSING = "processing"
    READY      = "ready"
    ERROR      = "error"

class ConfidenceLevel(str, Enum):
    HIGH   = "high"
    MEDIUM = "medium"
    LOW    = "low"


# ── Internal dataclasses ───────────────────────────────────────────────────

@dataclass
class Chunk:
    text:            str
    page:            int
    chunk_id:        str
    doc_id:          str
    has_formula:     bool  = False
    section_heading: str   = ""
    score:           float = 0.0
    ocr_sourced:     bool  = False


@dataclass
class RetrievalResult:
    chunks:      list[Chunk]    = field(default_factory=list)
    query_type:  QueryType      = QueryType.CONCEPT
    target_page: Optional[int]  = None


# ── API request / response schemas ────────────────────────────────────────

class ChatRequest(BaseModel):
    doc_id:  str
    query:   str
    history: list[dict] = []

class Source(BaseModel):
    doc_id:      str
    doc_name:    str
    page:        int
    text:        str
    ocr_sourced: bool
    confidence:  ConfidenceLevel

class ChatResponse(BaseModel):
    answer:     str
    query_type: QueryType
    sources:    list[Source]

class DocumentInfo(BaseModel):
    doc_id:      str
    name:        str
    pages:       int
    status:      IndexStatus
    ocr_pages:   int
    chunks:      int
    upload_time: str
    suggestions: list[str] = []

class UploadResponse(BaseModel):
    doc_id:  str
    name:    str
    pages:   int
    status:  IndexStatus

class PagePreviewResponse(BaseModel):
    doc_id:     str
    page:       int
    text:       str
    ocr_used:   bool
    image_b64:  Optional[str] = None  # base64 PNG of the rendered page
