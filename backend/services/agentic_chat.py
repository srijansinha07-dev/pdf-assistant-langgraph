"""
services/agentic_chat.py
────────────────────────
Production-grade deterministic planner + intent workflows.

Important guarantees:
- qa/page_lookup continue through run_chat_graph() exactly as-is.
- Non-QA workflows reuse LangGraph-like robustness patterns:
  retrieval grading, query rewriting, grounding checks, bounded retries, fallback.
- Retrieval implementation remains untouched (reuses services.retriever.retrieve).
- API contract remains unchanged.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal


Intent = Literal[
    "qa",
    "tutor",
    "comparison",
    "reasoning",
    "synthesis",
    "summary",
    "quiz",
    "revision",
    "formula",
    "page_lookup",
]

CONTEXT_CHAR_LIMIT = 4200
MAX_RETRIEVAL_RETRIES = 2
MAX_REASONING_PASSES = 2
MAX_ANSWER_RETRIES = 1

PAGE_PATTERN = re.compile(
    r"\b(page|pg\.?|slide)\s*(\d+)\b|\bpage\s+number\s+(\d+)\b",
    re.IGNORECASE,
)


@dataclass
class Plan:
    intent: Intent
    retrieval_query: str


@dataclass
class AgentState:
    doc_id: str
    query: str
    chunks_all: list
    pages_all: list
    doc_info: Any
    query_type: Any = None
    classified_query: str = ""
    retrieved_chunks: list | None = None
    context: str = ""
    retrieval_grade: str = ""
    answer: str = ""
    answer_grade: str = ""


def run_agentic_chat(
    doc_id: str,
    query: str,
    chunks_all: list,
    pages_all: list,
    doc_info: Any,
) -> dict:
    plan = plan_intent(query)

    # Explicitly preserve existing QA/page behavior.
    if plan.intent in {"qa", "page_lookup"}:
        return _fallback_to_qa(doc_id, query, chunks_all, pages_all, doc_info)

    state = AgentState(
        doc_id=doc_id,
        query=query,
        chunks_all=chunks_all,
        pages_all=pages_all,
        doc_info=doc_info,
        classified_query=plan.retrieval_query,
        retrieved_chunks=[],
    )

    if plan.intent == "comparison":
        return _run_comparison_workflow(state)
    if plan.intent == "reasoning":
        return _run_reasoning_workflow(state)
    if plan.intent == "formula":
        return _run_formula_workflow(state)
    if plan.intent == "tutor":
        return _run_single_retrieval_workflow(
            state,
            query_hint="definition explanation intuition misconception",
            answer_style=(
                "Teach like an expert instructor using this exact structure:\n"
                "1) Intuition first: simple mental model in 2-4 lines\n"
                "2) Why this concept exists: what problem it solves\n"
                "3) Step-by-step explanation: logical progression (3-6 steps)\n"
                "4) Analogy: one concrete analogy grounded in context\n"
                "5) Technical explanation: precise terms/equations from context\n"
                "6) Common misconceptions: only if supported by context\n"
                "7) Exam-oriented takeaway: what to remember under time pressure\n"
                "Avoid generic textbook wording."
            ),
        )
    if plan.intent == "summary":
        return _run_summary_synthesis_workflow(
            state,
            mode="summary",
            query_hint="key points highlights important topics",
        )
    if plan.intent == "synthesis":
        return _run_summary_synthesis_workflow(
            state,
            mode="synthesis",
            query_hint="themes relationships structure across document",
        )
    if plan.intent == "quiz":
        return _run_single_retrieval_workflow(
            state,
            query_hint="key concepts definitions formulas examples",
            answer_style=(
                "Generate 6 grounded Q/A pairs with increasing difficulty:\n"
                "- Q1-Q2: basic recall\n"
                "- Q3-Q4: conceptual understanding\n"
                "- Q5: application\n"
                "- Q6: reasoning/integration\n"
                "Format:\n"
                "Q1 (Easy): ...\nA1: ...\n"
                "...\n"
                "Q6 (Hard): ...\nA6: ...\n"
                "Each answer must be explicitly supported by context."
            ),
        )
    if plan.intent == "revision":
        return _run_single_retrieval_workflow(
            state,
            query_hint="key topics priorities revision plan roadmap",
            answer_style=(
                "1) High-priority topics\n"
                "2) Medium-priority topics\n"
                "3) 3-step revision roadmap\n"
                "4) Final checklist\n"
                "5) Top exam traps (only if evidenced)"
            ),
        )

    return _fallback_to_qa(doc_id, query, chunks_all, pages_all, doc_info)


def plan_intent(query: str) -> Plan:
    q = query.strip().lower()

    if _is_page_lookup(q):
        return Plan(intent="page_lookup", retrieval_query=query)
    if _is_formula(q):
        return Plan(intent="formula", retrieval_query=query)
    if _is_quiz(q):
        return Plan(intent="quiz", retrieval_query=query)
    if _is_revision(q):
        return Plan(intent="revision", retrieval_query=query)
    if _is_comparison(q):
        return Plan(intent="comparison", retrieval_query=query)
    if _is_reasoning(q):
        return Plan(intent="reasoning", retrieval_query=query)
    if _is_summary(q):
        return Plan(intent="summary", retrieval_query=query)
    if _is_synthesis(q):
        return Plan(intent="synthesis", retrieval_query=query)
    if _is_tutor(q):
        return Plan(intent="tutor", retrieval_query=query)
    return Plan(intent="qa", retrieval_query=query)


# ─────────────────────────────────────────────────────────────────────────────
# Reusable node-like primitives
# ─────────────────────────────────────────────────────────────────────────────

def _retrieve_context(state: AgentState, query: str) -> AgentState:
    from services import retriever as ret_svc

    result = ret_svc.retrieve(
        doc_id=state.doc_id,
        query=query,
        chunks=state.chunks_all,
        pages=state.pages_all,
    )
    return AgentState(
        **{
            **state.__dict__,
            "classified_query": query,
            "query_type": result.query_type,
            "retrieved_chunks": result.chunks,
            "context": _build_context(result.chunks),
        }
    )


def _grade_context(state: AgentState) -> AgentState:
    chunks = state.retrieved_chunks or []
    has_chunks = len(chunks) > 0
    enough_context = len(state.context.strip()) >= 120
    state.retrieval_grade = "good" if (has_chunks and enough_context) else "weak"
    return state


def _rewrite_query_if_weak(state: AgentState, original_query: str) -> str:
    prompt = (
        "Rewrite this query to retrieve better grounded evidence from a PDF.\n"
        f"Original query: {original_query}\n"
        f"Current retrieval query: {state.classified_query}\n"
        "Rewritten query (one concise line):"
    )
    rewritten = _safe_generate(prompt, fallback=state.classified_query, max_tokens=48).strip('"\'').strip()
    return rewritten or state.classified_query


def _ground_answer(state: AgentState, task_prompt: str) -> AgentState:
    prompt = (
        "You are a strict document-grounded assistant.\n"
        "Rules:\n"
        "- Use ONLY CONTEXT\n"
        "- Do not use outside knowledge\n"
        "- If context is insufficient, clearly state that\n\n"
        "Quality bar:\n"
        "- Explain relationships and meaning, not just copied facts\n"
        "- Prefer structured sections and concise bullets\n"
        "- Avoid generic textbook filler language\n\n"
        f"CONTEXT:\n{state.context}\n\n"
        f"REQUEST: {state.query}\n\n"
        f"{task_prompt}"
    )
    answer = _safe_generate(
        prompt,
        fallback="The document does not contain enough grounded information to answer this request.",
        max_tokens=460,
    )
    state.answer = answer
    state.answer_grade = _grade_answer_grounding(state.context, answer)
    return state


def _fallback_to_qa(
    doc_id: str,
    query: str,
    chunks_all: list,
    pages_all: list,
    doc_info: Any,
) -> dict:
    from services.langgraph_chat import run_chat_graph
    return run_chat_graph(
        doc_id=doc_id,
        query=query,
        chunks_all=chunks_all,
        pages_all=pages_all,
        doc_info=doc_info,
    )


def _retrieve_with_retries(state: AgentState, base_query: str, query_hint: str = "") -> AgentState:
    current_query = f"{base_query} {query_hint}".strip()
    attempt = 0
    latest = state
    while attempt <= MAX_RETRIEVAL_RETRIES:
        latest = _retrieve_context(latest, current_query)
        latest = _grade_context(latest)
        if latest.retrieval_grade == "good":
            return latest
        if attempt >= MAX_RETRIEVAL_RETRIES:
            return latest
        current_query = _rewrite_query_if_weak(latest, base_query)
        attempt += 1
    return latest


# ─────────────────────────────────────────────────────────────────────────────
# Intent workflows (bounded, deterministic)
# ─────────────────────────────────────────────────────────────────────────────

def _run_single_retrieval_workflow(state: AgentState, query_hint: str, answer_style: str) -> dict:
    state = _retrieve_with_retries(state, state.query, query_hint=query_hint)
    if state.retrieval_grade != "good":
        return _fallback_to_qa_result(state)

    state = _ground_answer(state, f"Respond using this format:\n{answer_style}")
    if state.answer_grade == "weak":
        # bounded single regeneration on suspicious answer
        state = _ground_answer(state, f"Regenerate and stay strictly grounded.\nFormat:\n{answer_style}")
    return _pack_result(state.answer, state.retrieved_chunks or [], state.query_type, state.doc_info)


def _run_summary_synthesis_workflow(state: AgentState, mode: str, query_hint: str) -> dict:
    # Broad coverage retrieval + dedupe.
    state = _retrieve_with_retries(state, state.query, query_hint=query_hint)
    if state.retrieval_grade != "good":
        return _fallback_to_qa_result(state)

    broad = _retrieve_with_retries(state, f"{state.query} overview", query_hint="major sections key ideas")
    merged_chunks = _dedupe_chunks((state.retrieved_chunks or []) + (broad.retrieved_chunks or []), limit=10)
    merged_context = _build_context(merged_chunks)
    if len(merged_context.strip()) < 120:
        return _fallback_to_qa_result(state)

    merged_state = AgentState(**{**state.__dict__, "retrieved_chunks": merged_chunks, "context": merged_context})
    if mode == "summary":
        task = (
            "Produce grounded study-friendly notes, not prose paragraphs.\n"
            "Structure:\n"
            "1) Topic map (main sections)\n"
            "2) Core concepts (bullet list)\n"
            "3) Must-remember facts/formulas\n"
            "4) High-yield revision cues"
        )
    else:
        task = (
            "Produce a document-level synthesis (deep, not shallow summary).\n"
            "Structure:\n"
            "1) Major themes\n"
            "2) Concept hierarchy (foundational -> intermediate -> advanced)\n"
            "3) Relationships/dependencies between concepts\n"
            "4) What matters most and why\n"
            "5) One-paragraph document-level understanding"
        )
    merged_state = _ground_answer(merged_state, task)
    if merged_state.answer_grade == "weak":
        merged_state = _ground_answer(merged_state, f"Regenerate strictly grounded.\n{task}")
    return _pack_result(merged_state.answer, merged_chunks, merged_state.query_type, merged_state.doc_info)


def _run_reasoning_workflow(state: AgentState) -> dict:
    # Pass 1: primary evidence retrieval.
    pass1 = _retrieve_with_retries(state, state.query, query_hint="evidence premise conclusion relationship")
    if pass1.retrieval_grade != "good":
        return _fallback_to_qa_result(state)

    # Pass 2: bridge retrieval (bounded max two passes, no recursion).
    bridge_query = _identify_bridge_query(pass1)
    pass2 = _retrieve_with_retries(pass1, bridge_query, query_hint="cause effect link implication")
    if pass2.retrieval_grade != "good":
        return _fallback_to_qa_result(state)

    merged_chunks = _dedupe_chunks((pass1.retrieved_chunks or []) + (pass2.retrieved_chunks or []), limit=10)
    merged_context = _build_context(merged_chunks)
    merged_state = AgentState(**{**pass2.__dict__, "retrieved_chunks": merged_chunks, "context": merged_context})
    merged_state = _ground_answer(
        merged_state,
        (
            "Provide explicit causal reasoning (not fact listing).\n"
            "Structure:\n"
            "1) Causal chain (3-6 steps with [P#] tags): A -> B -> C ...\n"
            "2) Mechanism: why each link follows from prior step\n"
            "3) Final conclusion\n"
            "4) Uncertainty / missing evidence\n"
            "If the query asks 'why', answer with cause-effect links."
        ),
    )
    if merged_state.answer_grade == "weak":
        merged_state = _ground_answer(
            merged_state,
            (
                "Regenerate with stricter causal logic.\n"
                "Use only evidence explicitly in context.\n"
                "Format:\n"
                "1) Causal chain with [P#]\n"
                "2) Mechanism\n"
                "3) Conclusion\n"
                "4) Uncertainty"
            ),
        )
    return _pack_result(merged_state.answer, merged_chunks, merged_state.query_type, merged_state.doc_info)


def _run_comparison_workflow(state: AgentState) -> dict:
    concept_a, concept_b = _extract_comparison_targets(state.query)

    a_state = _retrieve_with_retries(state, concept_a, query_hint="definition properties usage")
    if a_state.retrieval_grade != "good":
        return _fallback_to_qa_result(state)

    b_state = _retrieve_with_retries(state, concept_b, query_hint="definition properties usage")
    if b_state.retrieval_grade != "good":
        return _fallback_to_qa_result(state)

    merged_chunks = _dedupe_chunks((a_state.retrieved_chunks or []) + (b_state.retrieved_chunks or []), limit=10)
    merged_context = _build_context(merged_chunks)
    merged_state = AgentState(**{**state.__dict__, "retrieved_chunks": merged_chunks, "context": merged_context, "query_type": a_state.query_type})
    merged_state = _ground_answer(
        merged_state,
        (
            f"Compare '{concept_a}' vs '{concept_b}' using only context.\n"
            "Output structure:\n"
            "1) Purpose of each concept\n"
            "2) Similarities\n"
            "3) Differences\n"
            "4) When each is used\n"
            "5) Tradeoffs\n"
            "6) Intuition (how to mentally distinguish them quickly)\n"
            "Avoid shallow side-by-side definitions."
        ),
    )
    if merged_state.answer_grade == "weak":
        merged_state = _ground_answer(
            merged_state,
            (
                f"Regenerate strict grounded comparison for '{concept_a}' vs '{concept_b}'.\n"
                "Use only explicit evidence and keep the same 6-section structure."
            ),
        )
    return _pack_result(merged_state.answer, merged_chunks, merged_state.query_type, merged_state.doc_info)


def _run_formula_workflow(state: AgentState) -> dict:
    state = _retrieve_with_retries(state, state.query, query_hint="formula equation symbol derivation example")
    if state.retrieval_grade != "good":
        return _fallback_to_qa_result(state)

    has_example_evidence = _has_worked_example_evidence(state.context)
    if has_example_evidence:
        task = (
            "Output:\n"
            "1) Formula (exact from context)\n"
            "2) Intuition behind the formula\n"
            "3) When to use it\n"
            "4) Why each variable matters\n"
            "5) Worked example (must use only context values)\n"
            "6) Interpretation of the result"
        )
    else:
        task = (
            "Output:\n"
            "1) Formula (exact from context)\n"
            "2) Intuition behind the formula\n"
            "3) When to use it\n"
            "4) Why each variable matters\n"
            "5) Worked example: state that context lacks enough numeric evidence\n"
            "6) Interpretation guidance from available context"
        )
    state = _ground_answer(state, task)
    if state.answer_grade == "weak":
        state = _ground_answer(state, "Regenerate and remain strictly grounded.\n" + task)
    return _pack_result(state.answer, state.retrieved_chunks or [], state.query_type, state.doc_info)


def _fallback_to_qa_result(state: AgentState) -> dict:
    return _fallback_to_qa(
        doc_id=state.doc_id,
        query=state.query,
        chunks_all=state.chunks_all,
        pages_all=state.pages_all,
        doc_info=state.doc_info,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _safe_generate(prompt: str, fallback: str, max_tokens: int = 420) -> str:
    try:
        from services.langgraph_chat import _groq_call
        return _groq_call(prompt, max_tokens=max_tokens)
    except Exception as e:
        print(f"[Agentic] Generation error: {e}")
        return fallback


def _grade_answer_grounding(context: str, answer: str) -> str:
    if not answer or "LLM ERROR" in answer:
        return "weak"
    suspicious = (
        "typically ",
        "usually ",
        "in general ",
        "based on my knowledge",
        "commonly",
    )
    low_conf = any(s in answer.lower() for s in suspicious)
    if not low_conf:
        return "grounded"

    prompt = (
        f"Context: {context[:500]}\n\n"
        f"Answer: {answer[:350]}\n\n"
        "Is this answer grounded in the context? Reply with one word: grounded or weak."
    )
    raw = _safe_generate(prompt, fallback="grounded", max_tokens=6).lower()
    return "grounded" if "grounded" in raw else "weak"


def _build_context(chunks: list) -> str:
    parts = []
    size = 0
    for c in chunks:
        tag = "FORMULA" if c.has_formula else ("OCR" if c.ocr_sourced else "TEXT")
        block = f"[P{c.page}|{tag}]\n{c.text}"
        if size + len(block) > CONTEXT_CHAR_LIMIT:
            break
        parts.append(block)
        size += len(block)
    return "\n\n".join(parts)


def _dedupe_chunks(chunks: list, limit: int) -> list:
    seen = {}
    for c in chunks:
        key = (c.page, c.text[:140])
        if key not in seen or c.score > seen[key].score:
            seen[key] = c
    merged = list(seen.values())
    merged.sort(key=lambda x: x.score, reverse=True)
    return merged[:limit]


def _extract_comparison_targets(query: str) -> tuple[str, str]:
    q = query.strip()
    q_lower = q.lower()
    for sep in [" vs ", " versus ", " compare ", " difference between "]:
        sep_lower = sep.lower()
        if sep_lower in q_lower:
            idx = q_lower.find(sep_lower)
            left = q[:idx].strip()
            right = q[idx + len(sep):].strip()
            return left or q, right or q
    return q, q + " alternative"


def _identify_bridge_query(state: AgentState) -> str:
    prompt = (
        "Given the user query and retrieved evidence, write one bridge retrieval query "
        "to find missing relationships. Keep it concise.\n\n"
        f"User query: {state.query}\n"
        f"Current evidence excerpt:\n{state.context[:800]}\n\n"
        "Bridge query:"
    )
    bridge = _safe_generate(prompt, fallback=f"{state.query} relationship cause effect", max_tokens=40).strip()
    return bridge or f"{state.query} relationship cause effect"


def _has_worked_example_evidence(context: str) -> bool:
    has_numbers = bool(re.search(r"\d", context))
    has_operator = bool(re.search(r"[=+\-*/]", context))
    has_signal = any(s in context.lower() for s in ("example", "given", "calculate", "solve", "substitute"))
    return has_numbers and has_operator and has_signal


def _pack_result(answer: str, retrieved_chunks: list, query_type: Any, doc_info: Any) -> dict:
    from models import QueryType

    return {
        "answer": answer,
        "query_type": query_type or QueryType.CONCEPT,
        "retrieved_chunks": retrieved_chunks or [],
        "doc_info": doc_info,
    }


def _is_page_lookup(q: str) -> bool:
    return bool(PAGE_PATTERN.search(q)) or "page lookup" in q


def _is_formula(q: str) -> bool:
    return any(
        s in q
        for s in (
            "formula",
            "equation",
            "derive",
            "compute",
            "calculate",
            "worked example",
            "test statistic",
        )
    )


def _is_quiz(q: str) -> bool:
    return any(s in q for s in ("quiz", "mcq", "questions", "test me"))


def _is_revision(q: str) -> bool:
    return any(s in q for s in ("revision", "revise", "roadmap", "study plan"))


def _is_comparison(q: str) -> bool:
    return any(s in q for s in ("compare", "comparison", "vs", "difference between", "similarities"))


def _is_reasoning(q: str) -> bool:
    return any(s in q for s in ("why", "reason", "because", "infer", "implication", "how does this lead"))


def _is_summary(q: str) -> bool:
    return any(s in q for s in ("summary", "summarize", "notes", "tl;dr", "key points"))


def _is_synthesis(q: str) -> bool:
    return any(s in q for s in ("synthesize", "synthesis", "big picture", "overall themes", "connect"))


def _is_tutor(q: str) -> bool:
    return any(s in q for s in ("teach", "explain like", "tutor", "intuition", "misconception"))
