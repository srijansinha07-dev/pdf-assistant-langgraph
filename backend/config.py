"""
config.py — centralised configuration for the PDF Assistant backend.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent
UPLOAD_DIR    = BASE_DIR / "uploads"
CHROMA_DIR    = BASE_DIR / "chroma_db"

UPLOAD_DIR.mkdir(exist_ok=True)
CHROMA_DIR.mkdir(exist_ok=True)

# ── Ollama models ──────────────────────────────────────────────────────────
EMBED_MODEL = "nomic-embed-text"
LLM_MODEL   = "mistral"

USE_GROQ = os.getenv(
    "USE_GROQ",
    "False"
).lower() == "true"

GROQ_API_KEY = os.getenv(
    "GROQ_API_KEY",
    ""
)

GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "llama-3.3-70b-versatile"
)
print("USE_GROQ:", USE_GROQ)
print("MODEL:", GROQ_MODEL)
print("KEY EXISTS:", bool(GROQ_API_KEY))
# ── ChromaDB ───────────────────────────────────────────────────────────────
CHROMA_PATH = str(CHROMA_DIR)

# ── OCR ────────────────────────────────────────────────────────────────────
# Pages with fewer meaningful chars than this get OCR'd
OCR_THRESHOLD = 120
OCR_DPI       = 220          # higher = better formula accuracy

# ── Retrieval ──────────────────────────────────────────────────────────────
TOP_K_SEMANTIC = 10
TOP_K_BM25     = 10
TOP_K_FINAL = 6           # chunks sent to LLM after reranking

# ── Reranker ───────────────────────────────────────────────────────────────
RERANKER_MODEL = None

# ── CORS ───────────────────────────────────────────────────────────────────
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",

    # Vercel domains
    "https://lumina-pdf-assistant-iepxl5yae-srijansinha07-devs-projects.vercel.app",
    "https://lumina-pdf-assistant.vercel.app",
]
