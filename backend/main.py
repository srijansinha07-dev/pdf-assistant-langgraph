"""
main.py — FastAPI application entry point.
"""

import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import CORS_ORIGINS
from routers import chat, documents
from services import docstore

app = FastAPI(
    title="PDF Assistant API",
    description="OCR-aware PDF assistant",
    version="1.0.0",
)

# ── CORS ────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ─────────────────────────────────────────────
app.include_router(documents.router)
app.include_router(chat.router)


# ── Startup ─────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    print("🚀 SERVER STARTED")

    try:
        docstore.load_from_disk()
        print("✅ DOCSTORE LOADED")
    except Exception as e:
        print(f"❌ DOCSTORE ERROR: {e}")


# ── Routes ──────────────────────────────────────────────
@app.get("/")
def root():
    return {
        "message": "server working"
    }


@app.get("/api/health")
def health():
    return {
        "status": "ok"
    }


# ── Run ─────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                8000
            )
        ),
    )