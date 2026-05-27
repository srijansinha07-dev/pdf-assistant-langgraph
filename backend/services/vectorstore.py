"""
services/vectorstore.py
───────────────────────
ChromaDB vector store.

One Chroma collection per document.
Uses lightweight MiniLM embeddings through
Chroma's embedding function to reduce
Render RAM usage.
"""

from __future__ import annotations

import re

import chromadb
from chromadb.config import Settings
from chromadb.utils.embedding_functions import (
    SentenceTransformerEmbeddingFunction,
)

from config import (
    CHROMA_PATH,
    TOP_K_SEMANTIC,
)
from models import Chunk


# ── Embedding Function ─────────────────────────────────────────────────────

embedding_fn = (
    SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
)


# ── Singleton Chroma Client ────────────────────────────────────────────────

_client: chromadb.ClientAPI | None = None


def _get_client() -> chromadb.ClientAPI:
    global _client

    if _client is None:
        print("INITIALIZING CHROMA CLIENT...")

        _client = (
            chromadb.PersistentClient(
                path=CHROMA_PATH,
                settings=Settings(
                    anonymized_telemetry=False
                ),
            )
        )

        print("CHROMA CLIENT READY")

    return _client


# ── Public API ─────────────────────────────────────────────────────────────

def get_or_create_collection(
    doc_id: str
):
    col_name = _safe_col_name(
        doc_id
    )

    return (
        _get_client()
        .get_or_create_collection(
            name=col_name,
            metadata={
                "hnsw:space":
                    "cosine"
            },
            embedding_function=
                embedding_fn,
        )
    )


def collection_exists(
    doc_id: str
) -> bool:
    try:
        col = (
            _get_client()
            .get_collection(
                _safe_col_name(
                    doc_id
                ),
                embedding_function=
                    embedding_fn,
            )
        )

        return (
            col.count() > 0
        )

    except Exception:
        return False


def delete_collection(
    doc_id: str
):
    try:
        _get_client().delete_collection(
            _safe_col_name(
                doc_id
            )
        )

    except Exception:
        pass


def index_chunks(
    doc_id: str,
    chunks: list[Chunk],
    batch_size: int = 6,
) -> None:
    """
    Store chunks in Chroma.

    Embeddings are generated
    automatically by Chroma.
    """

    print(
        "INDEX FUNCTION START"
    )

    col = (
        get_or_create_collection(
            doc_id
        )
    )

    print(
        "COLLECTION READY"
    )

    if col.count() > 0:
        print(
            "COLLECTION EXISTS"
        )
        return

    for i in range(
        0,
        len(chunks),
        batch_size,
    ):
        print(
            f"BATCH "
            f"{i//batch_size + 1}"
        )

        batch = chunks[
            i:i + batch_size
        ]

        texts = [
            c.text
            for c in batch
        ]

        ids = [
            c.chunk_id
            for c in batch
        ]

        metas = [
            {
                "page":
                    c.page,
                "has_formula":
                    int(
                        c.has_formula
                    ),
                "heading":
                    c.section_heading,
                "ocr_sourced":
                    int(
                        c.ocr_sourced
                    ),
                "doc_id":
                    c.doc_id,
            }
            for c in batch
        ]

        print(
            "ADDING TO CHROMA"
        )

        col.add(
            documents=texts,
            ids=ids,
            metadatas=metas,
        )

        print(
            "BATCH COMPLETE"
        )

    print(
        "VECTORSTORE DONE"
    )


def semantic_search(
    doc_id: str,
    query: str,
    top_k: int =
        TOP_K_SEMANTIC,
    where: dict |
        None = None,
) -> list[Chunk]:

    col = (
        get_or_create_collection(
            doc_id
        )
    )

    count = col.count()

    if count == 0:
        return []

    kwargs = dict(
        query_texts=[
            query
        ],
        n_results=min(
            top_k,
            count
        ),
        include=[
            "documents",
            "metadatas",
            "distances",
        ],
    )

    if where:
        kwargs[
            "where"
        ] = where

    results = col.query(
        **kwargs
    )

    chunks = []

    for (
        doc,
        meta,
        dist
    ) in zip(
        results[
            "documents"
        ][0],
        results[
            "metadatas"
        ][0],
        results[
            "distances"
        ][0],
    ):

        chunks.append(
            Chunk(
                text=doc,
                page=meta[
                    "page"
                ],
                chunk_id="",
                doc_id=meta.get(
                    "doc_id",
                    doc_id
                ),
                has_formula=bool(
                    meta.get(
                        "has_formula"
                    )
                ),
                section_heading=
                    meta.get(
                        "heading",
                        ""
                    ),
                ocr_sourced=bool(
                    meta.get(
                        "ocr_sourced"
                    )
                ),
                score=
                    1.0 - dist,
            )
        )

    return chunks


# ── Helpers ────────────────────────────────────────────────────────────────

def _safe_col_name(
    doc_id: str
) -> str:
    """
    Chroma collection names:
    3–63 chars,
    alphanumeric + hyphens
    """

    name = re.sub(
        r"[^a-zA-Z0-9-]",
        "-",
        doc_id,
    )[:60]

    return (
        name
        if len(name) >= 3
        else f"doc-{name}"
    )