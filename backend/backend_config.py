import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set. Add it to your .env file.")

# ── LLM settings — model names and client live in llm_config.py ──────────────
from llm_config import LLM_API_KEY, QWEN_CODER_MODEL, QWEN_INSIGHT_MODEL, make_openai_client

LLM_PROVIDER   = "openrouter"
LLM_MODEL      = QWEN_CODER_MODEL   # default model (NLQ / LIDA / KPI)
OPENAI_API_KEY = LLM_API_KEY        # alias used by some modules
GOOGLE_API_KEY = ""                    # removed — Gemini no longer used
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")

# ── NLQ / RAG settings ────────────────────────────────────────────────────────
CHROMA_PATH     = os.getenv("CHROMA_PATH", "./chroma_db")
MAX_SQL_RETRIES   = int(os.getenv("MAX_SQL_RETRIES", "2"))
LIDA_MAX_GOALS    = int(os.getenv("LIDA_MAX_GOALS", "3"))
