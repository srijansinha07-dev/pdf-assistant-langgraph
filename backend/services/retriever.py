"""
services/retriever.py
─────────────────────
Multi-stage hybrid retriever:
  1. Query classification (PAGE / FORMULA / CONCEPT / EXACT)
  2. Semantic search (ChromaDB)
  3. BM25 keyword search
  4. Score boosting for formula/OCR chunks
  5. Cross-encoder reranking
"""
from __future__ import annotations

import re
from typing import Optional

from rank_bm25 import BM25Okapi

from config import TOP_K_BM25, TOP_K_FINAL, TOP_K_SEMANTIC, RERANKER_MODEL
from models import Chunk, QueryType, RetrievalResult
from services import vectorstore as vs

# ── Optional reranker ──────────────────────────────────────────────────────
try:
    from sentence_transformers import CrossEncoder

    if RERANKER_MODEL:
        _reranker = CrossEncoder(
            RERANKER_MODEL
        )
        RERANKER_OK = True
    else:
        _reranker = None
        RERANKER_OK = False

except Exception:
    _reranker = None
    RERANKER_OK = False


# ── Regex & keyword sets ───────────────────────────────────────────────────
FORMULA_SYMBOLS_RE = re.compile(
    r'[μσαβρΣΩ∑√±∞≈≠≤≥∈∉]'
    r'|H[_0-9]*\s*[:=]'
    r'|[zZtTFp]\s*[=<>≤≥]'
    r'|\b(alpha|beta|sigma|mu|rho)\b'
    r'|[_^]\s*\{?[a-zA-Z0-9]+\}?'
    r'|={1,2}',
    re.IGNORECASE,
)

FORMULA_KEYWORDS = {
    "formula", "equation", "test statistic", "z-test", "t-test", "f-test",
    "population proportion", "null hypothesis", "alternative hypothesis",
    "confidence interval", "critical value", "p-value", "significance",
    "standard error", "sample mean", "sample size", "degrees of freedom",
    "chi-square", "chi square", "anova", "regression", "correlation",
}

PAGE_PATTERN = re.compile(
    r'\b(page|pg\.?|slide)\s*(\d+)\b'
    r'|\bpage\s+number\s+(\d+)\b',
    re.IGNORECASE,
)

EXACT_SIGNALS = frozenset([
    "exactly", "verbatim", "quote", "written about", "word for word",
    "what does it say", "what is written",
])


# ── BM25 index (per doc, lazily built) ────────────────────────────────────
_bm25_cache: dict[str, tuple[BM25Okapi, list[Chunk]]] = {}

def _get_bm25(doc_id: str, chunks: list[Chunk]) -> BM25Okapi:
    if doc_id not in _bm25_cache:
        tokenized = [_tokenize(c.text) for c in chunks]
        _bm25_cache[doc_id] = (BM25Okapi(tokenized), chunks)
    return _bm25_cache[doc_id]


def invalidate_bm25(doc_id: str):
    _bm25_cache.pop(doc_id, None)


# ── Public API ─────────────────────────────────────────────────────────────

def classify(query: str) -> tuple[QueryType, Optional[int]]:
    q = query.lower()

    m = PAGE_PATTERN.search(query)
    if m:
        nums = [g for g in m.groups() if g and g.isdigit()]
        return QueryType.PAGE, int(nums[0]) if nums else None

    if any(kw in q for kw in FORMULA_KEYWORDS) or FORMULA_SYMBOLS_RE.search(query):
        return QueryType.FORMULA, None

    if any(s in q for s in EXACT_SIGNALS):
        return QueryType.EXACT, None

    return QueryType.CONCEPT, None


def retrieve(
    doc_id: str,
    query:  str,
    chunks: list[Chunk],
    pages:  list[dict],
) -> RetrievalResult:
    qtype, target_page = classify(query)

    if qtype == QueryType.PAGE:
        return _page_retrieve(doc_id, target_page, pages)

    candidates = _hybrid(doc_id, query, chunks, qtype)
    final      = _rerank(query, candidates)

    return RetrievalResult(chunks=final, query_type=qtype, target_page=target_page)


# ── Retrieval modes ────────────────────────────────────────────────────────

def _page_retrieve(doc_id: str, page_num: Optional[int], pages: list[dict]) -> RetrievalResult:
    page_map = {p["page_num"]: p for p in pages}
    pd = page_map.get(page_num)
    if not pd:
        return RetrievalResult(chunks=[], query_type=QueryType.PAGE, target_page=page_num)
    chunk = Chunk(
        text=pd["text"], page=page_num, chunk_id=f"page_{page_num}",
        doc_id=doc_id, has_formula=bool(FORMULA_SYMBOLS_RE.search(pd["text"])),
        ocr_sourced=pd.get("ocr_used", False), score=1.0,
    )
    return RetrievalResult(chunks=[chunk], query_type=QueryType.PAGE, target_page=page_num)


def _hybrid(
    doc_id: str,
    query: str,
    chunks: list[Chunk],
    qtype: QueryType,
) -> list[Chunk]:

    query_lower = query.lower()

    # ── Improve vague legal queries ─────────────────────
    if any(word in query_lower for word in [
        "summarize",
        "agreement",
        "contract",
        "clauses",
        "obligations",
        "terms",
        "legal",
    ]):
        query += (
            " agreement contract parties "
            "clauses obligations terms recitals"
        )

    # ── Formula queries ─────────────────────────────────
    if qtype == QueryType.FORMULA:

        sem_formula = vs.semantic_search(
            doc_id,
            query,
            top_k=TOP_K_SEMANTIC,
            where={
                "has_formula": {"$eq": 1}
            },
        )

        sem_all = vs.semantic_search(
            doc_id,
            query,
            top_k=max(2, TOP_K_SEMANTIC // 2),
        )

        kw = _bm25_search(
            doc_id,
            query,
            chunks,
            top_k=TOP_K_BM25,
        )

        candidates = _merge(
            sem_formula,
            sem_all,
            kw,
        )

        # Boost formula-heavy chunks
        for c in candidates:

            if c.has_formula:
                c.score += 0.25

            if c.ocr_sourced:
                c.score += 0.10

    # ── General / concept queries ──────────────────────
    else:

        sem = vs.semantic_search(
            doc_id,
            query,
            top_k=max(TOP_K_SEMANTIC, 10),
        )

        kw = _bm25_search(
            doc_id,
            query,
            chunks,
            top_k=10,
        )

        candidates = _merge(
            sem,
            kw,
        )

        query_words = {
            word
            for word in query_lower.split()
            if len(word) > 3
        }

        # Legal / OCR boilerplate junk
        legal_boilerplate = [
            "verification",
            "deponent",
            "signature",
            "seal",
            "notary",
            "annexure",
            "witness",
            "stamp",
            "sworn",
            "affirmed",
            "attested",
            "executant",
        ]

        for c in candidates:
            text = c.text.lower()

            # ── Reward keyword overlap ────────────────
            overlap = sum(
                1
                for word in query_words
                if word in text
            )

            c.score += overlap * 0.08

            # ── Penalize legal junk pages ─────────────
            junk_hits = sum(
                1
                for word in legal_boilerplate
                if word in text
            )

            c.score -= junk_hits * 0.15

            # ── Prefer meaningful chunks ──────────────
            if len(text.split()) > 100:
                c.score += 0.08

            # Penalize OCR garbage
            if text.count("*") > 5:
                c.score -= 0.20

        # ── Final reranking ───────────────────────────
        candidates.sort(
            key=lambda x: x.score,
            reverse=True,
        )

        # Keep richer context for long docs
        candidates = candidates[:8]

    return candidates


def _bm25_search(doc_id: str, query: str, chunks: list[Chunk], top_k: int) -> list[Chunk]:
    if not chunks:
        return []
    bm25, stored = _get_bm25(doc_id, chunks)
    scores       = bm25.get_scores(_tokenize(query))
    ranked       = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]
    results      = []
    for i, score in ranked:
        if score > 0:
            c = stored[i]
            results.append(Chunk(
                text=c.text, page=c.page, chunk_id=c.chunk_id,
                doc_id=c.doc_id, has_formula=c.has_formula,
                section_heading=c.section_heading, ocr_sourced=c.ocr_sourced,
                score=float(score),
            ))
    return results


def _rerank(query: str, chunks: list[Chunk]) -> list[Chunk]:
    if not chunks:
        return []
    if not RERANKER_OK or _reranker is None:
        return sorted(chunks, key=lambda c: c.score, reverse=True)[:TOP_K_FINAL]
    pairs  = [(query, c.text) for c in chunks]
    scores = _reranker.predict(pairs)
    for c, s in zip(chunks, scores):
        c.score = float(s)
    return sorted(chunks, key=lambda c: c.score, reverse=True)[:TOP_K_FINAL]


# ── Utils ──────────────────────────────────────────────────────────────────

def _merge(*lists) -> list[Chunk]:
    seen: dict[str, Chunk] = {}
    for lst in lists:
        for c in lst:
            key = c.text[:120]
            if key not in seen or c.score > seen[key].score:
                seen[key] = c
    return list(seen.values())


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r'[A-Za-z0-9μσαβρΣH₀₁_]+|[=<>≤≥±√∑]', text.lower())
    return tokens or text.lower().split()
