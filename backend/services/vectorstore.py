"""
services/vectorstore.py
───────────────────────
ChromaDB vector store with nomic-embed-text embeddings via Ollama.
One ChromaDB collection per document (doc_id as collection name).
"""

from __future__ import annotations


import re

import chromadb
import ollama
from chromadb.config import Settings

from config import CHROMA_PATH, EMBED_MODEL, TOP_K_SEMANTIC
from models import Chunk


# ── Singleton client ───────────────────────────────────────────────────────
_embedder = None


def _get_embedder():
    global _embedder

    if _embedder is None:
        print("LOADING EMBEDDER...")

        from sentence_transformers import SentenceTransformer

        _embedder = SentenceTransformer(
            "all-MiniLM-L6-v2",
            device="cpu"
        )

        print("EMBEDDER LOADED")

    return _embedder


_client: chromadb.ClientAPI | None = None

def _get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=CHROMA_PATH,
            settings=Settings(anonymized_telemetry=False),
        )
    return _client


# ── Public API ─────────────────────────────────────────────────────────────

def get_or_create_collection(doc_id: str):
    col_name = _safe_col_name(doc_id)
    return _get_client().get_or_create_collection(
        name=col_name,
        metadata={"hnsw:space": "cosine"},
    )


def collection_exists(doc_id: str) -> bool:
    try:
        col = _get_client().get_collection(_safe_col_name(doc_id))
        return col.count() > 0
    except Exception:
        return False


def delete_collection(doc_id: str):
    try:
        _get_client().delete_collection(_safe_col_name(doc_id))
    except Exception:
        pass


def index_chunks(doc_id: str, chunks: list[Chunk], batch_size: int = 6) -> None:
    """Embed and store chunks. Skips if collection already populated."""
    col = get_or_create_collection(doc_id)
    if col.count() > 0:
        return

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i: i + batch_size]
        texts = [c.text for c in batch]
        ids   = [c.chunk_id for c in batch]
        metas = [
            {
                "page":        c.page,
                "has_formula": int(c.has_formula),
                "heading":     c.section_heading,
                "ocr_sourced": int(c.ocr_sourced),
                "doc_id":      c.doc_id,
            }
            for c in batch
        ]
        embs = _embed(texts)
        col.add(documents=texts, embeddings=embs, ids=ids, metadatas=metas)


def semantic_search(
    doc_id: str,
    query:  str,
    top_k:  int = TOP_K_SEMANTIC,
    where:  dict | None = None,
) -> list[Chunk]:
    col   = get_or_create_collection(doc_id)
    count = col.count()
    if count == 0:
        return []

    q_emb  = _embed([query])[0]
    kwargs = dict(
        query_embeddings=[q_emb],
        n_results=min(top_k, count),
        include=["documents", "metadatas", "distances"],
    )
    if where:
        kwargs["where"] = where

    results = col.query(**kwargs)
    chunks  = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        chunks.append(Chunk(
            text=doc,
            page=meta["page"],
            chunk_id="",
            doc_id=meta.get("doc_id", doc_id),
            has_formula=bool(meta.get("has_formula")),
            section_heading=meta.get("heading", ""),
            ocr_sourced=bool(meta.get("ocr_sourced")),
            score=1.0 - dist,
        ))
    return chunks


# ── Helpers ────────────────────────────────────────────────────────────────

def _embed(
    texts: list[str]
) -> list[list[float]]:

    embedder = (
        _get_embedder()
    )

    embeddings = (
        embedder.encode(
            texts,
            convert_to_numpy=True,
            batch_size=2,
        )
    )

    return (
        embeddings.tolist()
    )


def _safe_col_name(doc_id: str) -> str:
    """ChromaDB collection names: 3-63 chars, alphanumeric + hyphens."""
    name = re.sub(r'[^a-zA-Z0-9-]', '-', doc_id)[:60]
    return name if len(name) >= 3 else f"doc-{name}"
