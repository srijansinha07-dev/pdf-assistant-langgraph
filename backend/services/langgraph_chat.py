"""
services/langgraph_chat.py
──────────────────────────
LangGraph RAG pipeline. Token-optimized version.

Token budget per normal query
  Answer generation input:  ~600-700  (down from ~950)
  Answer generation output: ~300      (down from 900 max)
  Answer grader input:      ~150      (down from ~530)
  Answer grader output:     ~1
  ─────────────────────────────────
  Total:                    ~1050-1150 (down from ~2300-2400)
"""
from __future__ import annotations

from typing import Any, Optional, TypedDict


# ─────────────────────────────────────────────────────────────────────────────
# State
# ─────────────────────────────────────────────────────────────────────────────

class GraphState(TypedDict):
    doc_id: str
    query: str
    chunks_all: list
    pages_all: list
    classified_query: str
    query_type: Any
    target_page: Optional[int]
    retrieved_chunks: list
    retrieval_grade: str
    answer: str
    answer_grade: str
    retry_count: int
    answer_retry_count: int
    context: str
    ocr_used: bool
    fallback: bool
    doc_info: Any


MAX_RETRIEVAL_RETRIES = 2
MAX_ANSWER_RETRIES    = 1

# ── Context limits (chars) ────────────────────────────────────────────────
# Caps how many chars of retrieved text go into each prompt.
# 3000 chars ≈ 750 tokens — enough for dense answers, avoids bloat.
CONTEXT_CHAR_LIMIT        = 3000
# Answer grader only needs a hint of context, not the full thing.
GRADER_CONTEXT_CHAR_LIMIT = 400
GRADER_ANSWER_CHAR_LIMIT  = 300


# ─────────────────────────────────────────────────────────────────────────────
# Shared system instruction (single copy, referenced in every prompt)
# ─────────────────────────────────────────────────────────────────────────────
# Kept to one tight paragraph instead of an 8-rule numbered list.
_RULES = (
    "Answer using ONLY the CONTEXT provided. "
    "Never use outside knowledge. "
    "If the answer is absent from the context, say: "
    "\"The document does not contain this information.\""
)


# ─────────────────────────────────────────────────────────────────────────────
# Groq helper
# ─────────────────────────────────────────────────────────────────────────────

def _groq_call(prompt: str, max_tokens: int = 300) -> str:
    """Lazy Groq import — avoids startup memory hit on Railway."""
    from groq import Groq
    from config import GROQ_API_KEY, GROQ_MODEL

    client = Groq(api_key=GROQ_API_KEY)
    resp = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Prompt builders  (optimized — no repeated boilerplate, tight char limits)
# ─────────────────────────────────────────────────────────────────────────────

def _concept_prompt(query: str, context: str) -> str:
    ctx = context[:CONTEXT_CHAR_LIMIT]
    return (
        f"{_RULES}\n\n"
        f"CONTEXT:\n{ctx}\n\n"
        f"QUESTION: {query}\n\n"
        "Answer concisely using only the context above. "
        "No chunk labels, no meta-commentary."
    )


def _formula_prompt(query: str, context: str) -> str:
    ctx = context[:CONTEXT_CHAR_LIMIT]
    return (
        f"{_RULES}\n\n"
        f"CONTEXT:\n{ctx}\n\n"
        f"QUESTION: {query}\n\n"
        "If the formula is in the context, state it exactly and explain it in 1-2 lines. "
        "If not found, say: \"The document does not explicitly contain this formula.\""
    )


def _page_prompt(query: str, context: str, page_num: int | None, ocr_used: bool) -> str:
    ctx = context[:CONTEXT_CHAR_LIMIT]
    ocr = " (OCR-extracted, minor errors possible)" if ocr_used else ""
    return (
        f"{_RULES}\n\n"
        f"PAGE {page_num} CONTENT{ocr}:\n{ctx}\n\n"
        f"QUESTION: {query}\n\n"
        "Summarise the page content faithfully. List key points present on the page."
    )


def _exact_prompt(query: str, context: str) -> str:
    ctx = context[:CONTEXT_CHAR_LIMIT]
    return (
        f"{_RULES}\n\n"
        f"CONTEXT:\n{ctx}\n\n"
        f"QUESTION: {query}\n\n"
        "Quote the most relevant passage(s) verbatim and state the page number."
    )


def _build_prompt(query, context, qtype, page_num, ocr_used) -> str:
    from models import QueryType
    if qtype == QueryType.FORMULA:
        return _formula_prompt(query, context)
    if qtype == QueryType.PAGE:
        return _page_prompt(query, context, page_num, ocr_used)
    if qtype == QueryType.EXACT:
        return _exact_prompt(query, context)
    return _concept_prompt(query, context)


# ─────────────────────────────────────────────────────────────────────────────
# Node implementations
# ─────────────────────────────────────────────────────────────────────────────

def node_classify(state: GraphState) -> GraphState:
    from services import retriever as ret_svc
    qtype, target_page = ret_svc.classify(state["query"])
    return {
        **state,
        "classified_query":   state["query"],
        "query_type":         qtype,
        "target_page":        target_page,
        "retry_count":        0,
        "answer_retry_count": 0,
        "fallback":           False,
    }


def node_retrieve(state: GraphState) -> GraphState:
    from services import retriever as ret_svc
    result = ret_svc.retrieve(
        doc_id=state["doc_id"],
        query=state["classified_query"],
        chunks=state["chunks_all"],
        pages=state["pages_all"],
    )
    context_parts = []
    for i, c in enumerate(result.chunks):
        tag = "FORMULA" if c.has_formula else ("OCR" if c.ocr_sourced else "TEXT")
        context_parts.append(f"[P{c.page}|{tag}]\n{c.text}")
    context  = "\n\n".join(context_parts)
    ocr_used = any(c.ocr_sourced for c in result.chunks)
    return {
        **state,
        "retrieved_chunks": result.chunks,
        "query_type":       result.query_type,
        "target_page":      result.target_page,
        "context":          context,
        "ocr_used":         ocr_used,
    }


def node_grade_retrieval(state: GraphState) -> GraphState:
    """
    Pure heuristic — no LLM call needed here.
    The hybrid retriever (ChromaDB + BM25 + reranker) already scores
    chunks well; grading with another LLM call just burns tokens.
    Weak = zero chunks returned. Good = anything else.
    """
    chunks = state["retrieved_chunks"]
    grade  = "weak" if not chunks else "good"
    print(f"[RETRIEVAL GRADE] {grade} ({len(chunks)} chunks)")
    return {**state, "retrieval_grade": grade}


def node_rewrite_query(state: GraphState) -> GraphState:
    """Rewrite only on retry — tight prompt, no examples needed."""
    prompt = (
        f"Rewrite this search query to retrieve better results from a PDF document.\n"
        f"Original: {state['query']}\n"
        f"Current:  {state['classified_query']}\n"
        f"Rewritten query (one line only):"
    )
    try:
        rewritten = _groq_call(prompt, max_tokens=40).strip('"\'').strip()
        if not rewritten:
            rewritten = state["classified_query"]
    except Exception as e:
        print(f"[LangGraph] Rewrite error: {e}")
        rewritten = state["classified_query"]

    print(f"[QUERY REWRITE] '{state['classified_query']}' -> '{rewritten}'")
    return {
        **state,
        "classified_query": rewritten,
        "retry_count":      state["retry_count"] + 1,
    }


def node_generate_answer(state: GraphState) -> GraphState:
    """Build the answer prompt inline — no llm.py roundtrip needed."""
    prompt = _build_prompt(
        query    = state["classified_query"],
        context  = state["context"],
        qtype    = state["query_type"],
        page_num = state["target_page"],
        ocr_used = state["ocr_used"],
    )
    try:
        # 350 max_tokens covers most answers; saves ~550 vs the old 900 ceiling
        answer = _groq_call(prompt, max_tokens=350)
    except Exception as e:
        print(f"[LangGraph] Generation error: {e}")
        answer = f"LLM ERROR: {e}"

    retry_count = state.get("answer_retry_count", 0)
    if state.get("answer_grade") == "weak":
        retry_count += 1

    return {**state, "answer": answer, "answer_retry_count": retry_count}


def node_grade_answer(state: GraphState) -> GraphState:
    """
    Minimal grounding check — tiny prompt, no context re-send.
    Just checks if the answer contains any hallucination signals.
    Heuristic first; Groq only if answer looks suspicious.
    """
    answer = state.get("answer", "")

    # Fast-path: obvious non-answers need no grading
    if not answer or "LLM ERROR" in answer or "NOT FOUND" in answer.upper():
        return {**state, "answer_grade": "grounded"}

    # Heuristic: if answer cites outside knowledge phrases, call Groq
    hallucination_signals = [
        "typically ", "usually ", "in general ", "it is known ",
        "according to common", "based on my knowledge",
    ]
    needs_check = any(s in answer.lower() for s in hallucination_signals)

    if not needs_check:
        # Trust it — saves ~540 tokens on the vast majority of queries
        return {**state, "answer_grade": "grounded"}

    # Only reaches here for suspicious answers — very short prompt
    ans_snippet = answer[:GRADER_ANSWER_CHAR_LIMIT]
    ctx_snippet = state["context"][:GRADER_CONTEXT_CHAR_LIMIT]
    prompt = (
        f"Context: {ctx_snippet}\n\n"
        f"Answer: {ans_snippet}\n\n"
        "Is this answer grounded in the context? Reply: grounded or weak."
    )
    try:
        raw   = _groq_call(prompt, max_tokens=5).lower()
        grade = "grounded" if "grounded" in raw else "weak"
    except Exception as e:
        print(f"[LangGraph] Answer grader error: {e}")
        grade = "grounded"

    return {**state, "answer_grade": grade}


def node_fallback(state: GraphState) -> GraphState:
    return {
        **state,
        "answer": (
            "I couldn't find enough relevant information in the document. "
            "Try rephrasing your question or asking about a specific page or topic."
        ),
        "fallback": True,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Conditional edges
# ─────────────────────────────────────────────────────────────────────────────

def edge_after_retrieval_grade(state: GraphState) -> str:
    if state["retrieval_grade"] == "good":
        return "generate"
    if state["retry_count"] >= MAX_RETRIEVAL_RETRIES:
        return "fallback"
    return "rewrite"


def edge_after_answer_grade(state: GraphState) -> str:
    if state["answer_grade"] == "grounded":
        return "end"
    if state.get("answer_retry_count", 0) >= MAX_ANSWER_RETRIES:
        return "end"
    return "regenerate"


# ─────────────────────────────────────────────────────────────────────────────
# Graph (lazy singleton)
# ─────────────────────────────────────────────────────────────────────────────

_graph = None


def _build_graph():
    from langgraph.graph import StateGraph, END

    g = StateGraph(GraphState)
    g.add_node("classify",        node_classify)
    g.add_node("retrieve",        node_retrieve)
    g.add_node("grade_retrieval", node_grade_retrieval)
    g.add_node("rewrite_query",   node_rewrite_query)
    g.add_node("generate_answer", node_generate_answer)
    g.add_node("grade_answer",    node_grade_answer)
    g.add_node("fallback",        node_fallback)

    g.set_entry_point("classify")

    g.add_edge("classify",        "retrieve")
    g.add_edge("retrieve",        "grade_retrieval")
    g.add_edge("rewrite_query",   "retrieve")
    g.add_edge("generate_answer", "grade_answer")
    g.add_edge("fallback",        END)

    g.add_conditional_edges(
        "grade_retrieval",
        edge_after_retrieval_grade,
        {"generate": "generate_answer", "rewrite": "rewrite_query", "fallback": "fallback"},
    )
    g.add_conditional_edges(
        "grade_answer",
        edge_after_answer_grade,
        {"end": END, "regenerate": "generate_answer"},
    )
    return g.compile()


def _get_graph():
    global _graph
    if _graph is None:
        _graph = _build_graph()
    return _graph


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def run_chat_graph(
    doc_id: str,
    query: str,
    chunks_all: list,
    pages_all: list,
    doc_info: Any,
) -> dict:
    graph = _get_graph()

    initial_state: GraphState = {
        "doc_id":             doc_id,
        "query":              query,
        "chunks_all":         chunks_all,
        "pages_all":          pages_all,
        "classified_query":   query,
        "query_type":         None,
        "target_page":        None,
        "retrieved_chunks":   [],
        "retrieval_grade":    "",
        "answer":             "",
        "answer_grade":       "",
        "retry_count":        0,
        "answer_retry_count": 0,
        "context":            "",
        "ocr_used":           False,
        "fallback":           False,
        "doc_info":           doc_info,
    }

    try:
        final_state = graph.invoke(initial_state)
    except Exception as e:
        print(f"[LangGraph] Graph error: {e}")
        final_state = _fallback_pipeline(initial_state)

    return {
        "answer":           final_state.get("answer", "An error occurred."),
        "query_type":       final_state.get("query_type"),
        "retrieved_chunks": final_state.get("retrieved_chunks", []),
        "doc_info":         doc_info,
    }


def _fallback_pipeline(state: GraphState) -> GraphState:
    """Direct pipeline used if the graph itself crashes."""
    from services import retriever as ret_svc

    result = ret_svc.retrieve(
        doc_id=state["doc_id"],
        query=state["query"],
        chunks=state["chunks_all"],
        pages=state["pages_all"],
    )
    if not result.chunks:
        return {
            **state,
            "answer":           "The document does not explicitly contain this information.",
            "query_type":       result.query_type,
            "retrieved_chunks": [],
        }

    context_parts = []
    for i, c in enumerate(result.chunks):
        tag = "FORMULA" if c.has_formula else ("OCR" if c.ocr_sourced else "TEXT")
        context_parts.append(f"[P{c.page}|{tag}]\n{c.text}")
    context  = "\n\n".join(context_parts)
    ocr_used = any(c.ocr_sourced for c in result.chunks)

    prompt = _build_prompt(
        query    = state["query"],
        context  = context,
        qtype    = result.query_type,
        page_num = result.target_page,
        ocr_used = ocr_used,
    )
    try:
        answer = _groq_call(prompt, max_tokens=350)
    except Exception as e:
        answer = f"LLM ERROR: {e}"

    return {
        **state,
        "answer":           answer,
        "query_type":       result.query_type,
        "target_page":      result.target_page,
        "retrieved_chunks": result.chunks,
        "context":          context,
        "ocr_used":         ocr_used,
    }