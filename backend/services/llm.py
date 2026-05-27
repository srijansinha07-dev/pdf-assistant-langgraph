"""
services/llm.py
───────────────
Ollama / Mistral interface with strict anti-hallucination prompts.
One prompt template per query type.
temperature = 0 throughout.
"""
from __future__ import annotations


from groq import Groq

from config import (
    LLM_MODEL,
    USE_GROQ,
    GROQ_API_KEY,
    GROQ_MODEL,
)
from models import QueryType


SYSTEM_BASE = """You are a strict document analysis assistant.

ABSOLUTE RULES — violating any rule is a critical failure:
1. ONLY use information explicitly present in the CONTEXT below.
2. NEVER use outside knowledge, even if you are certain it is correct.
3. NEVER infer, derive, or reconstruct formulas not literally present in the CONTEXT.
4. NEVER explain concepts not explicitly discussed in the CONTEXT.
5. If the CONTEXT does not contain the answer, output the NOT FOUND template exactly.
6. Do NOT add disclaimers or suggest looking elsewhere.
7. Do NOT say "based on my knowledge", "typically", or "in statistics".
8. Sections marked [OCR] may have minor character errors — trust mathematical meaning.
"""


def answer(
    query: str,
    context: str,
    qtype: QueryType,
    page_num: int | None = None,
    ocr_used: bool = False,
) -> str:

    try:
        print("=== LLM START ===")
        print("USE_GROQ:", USE_GROQ)
        print("GROQ MODEL:", GROQ_MODEL)
        print(
            "GROQ KEY EXISTS:",
            bool(GROQ_API_KEY)
        )

        prompt = _build_prompt(
            query,
            context,
            qtype,
            page_num,
            ocr_used,
        )

        client = Groq(
            api_key=GROQ_API_KEY
        )

        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            temperature=0,
            max_tokens=900,
        )

        print("=== GROQ SUCCESS ===")

        return (
            resp.choices[0]
            .message.content
            .strip()
        )

    except Exception as e:
        print(
            "=== LLM ERROR ==="
        )
        print(str(e))

        return (
            f"LLM ERROR: {str(e)}"
        )


    raise RuntimeError(
    "Groq is not enabled. Check USE_GROQ and GROQ_API_KEY."
)


# ── Prompt builders ────────────────────────────────────────────────────────

def _build_prompt(
    query: str,
    context: str,
    qtype: QueryType,
    page_num: int | None,
    ocr_used: bool,
) -> str:
    if qtype == QueryType.FORMULA:
        return _formula_prompt(query, context)

    if qtype == QueryType.PAGE:
        return _page_prompt(
            query,
            context,
            page_num,
            ocr_used,
        )

    if qtype == QueryType.EXACT:
        return _exact_prompt(
            query,
            context,
        )

    return _concept_prompt(
        query,
        context,
    )


def _formula_prompt(query: str, context: str) -> str:
    return f"""{SYSTEM_BASE}

TASK: The user is asking about a FORMULA or EQUATION.

CONTEXT:
---
{context}
---

QUESTION: {query}

If you find the formula in the CONTEXT, respond in this EXACT format:

FOUND FORMULA:
-------------
Formula:
[exact formula from context — copy symbols verbatim]

Brief explanation:
[1–2 concise lines explaining the formula using only context]

If the formula is NOT in the CONTEXT, respond EXACTLY:

NOT FOUND:
----------
The document does not explicitly contain this formula.

Do NOT invent, derive, or infer any formula under any circumstances."""


def _page_prompt(
    query: str,
    context: str,
    page_num: int | None,
    ocr_used: bool,
) -> str:

    ocr_note = (
        "\nNote: This page was extracted via OCR — minor character errors possible."
        if ocr_used
        else ""
    )

    return f"""{SYSTEM_BASE}

TASK: Return content from page {page_num}.{ocr_note}

PAGE {page_num} CONTENT:
---
{context}
---

QUESTION:
{query}

Respond in this EXACT format:

PAGE CONTENT:
-------------
[Faithful summary using ONLY the content above]

Key points:
- [point 1]
- [point 2]
- [etc.]

Only include points actually present on the page.
"""


def _concept_prompt(query: str, context: str) -> str:
    return f"""{SYSTEM_BASE}

TASK: Answer the user's question using ONLY the provided document context.

CONTEXT:
---
{context}
---

QUESTION:
{query}

STRICT RULES:
1. ONLY use information explicitly present in the context.
2. NEVER use outside knowledge.
3. NEVER explain legal, technical, scientific, or academic terms unless explicitly explained in the document.
4. NEVER say things like:
   - "In legal documents..."
   - "Typically..."
   - "Usually..."
   - "This refers to..."
5. NEVER mention:
   - chunks
   - retrieval
   - OCR
   - source ranking
   - document processing
6. NEVER say "Chunk 1", "Chunk 2", etc.
7. If summarizing:
   - summarize ONLY what appears in the retrieved text.
   - avoid disclaimers.
8. If asked about clauses, obligations, terms, or concepts:
   - extract the relevant information directly from context.
   - do NOT invent definitions.

STYLE:
- Natural and concise.
- Clear paragraphs or bullets when useful.
- No section headers like "Sources", "Supporting text", or "Page".

If the answer is genuinely unavailable, say exactly:
"The document does not explicitly contain enough information to answer this."
"""


def _exact_prompt(query: str, context: str) -> str:
    return f"""{SYSTEM_BASE}

TASK: Quote the exact text from the document.

CONTEXT:
---
{context}
---

QUESTION: {query}

Find and quote the most relevant passage(s) verbatim from the CONTEXT.
State the page number.
Do NOT paraphrase. Do NOT add outside information."""
