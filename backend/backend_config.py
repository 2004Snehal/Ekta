import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set. Add it to your .env file.")

# ── LLM settings ─────────────────────────────────────────────────────────────
# To switch providers: set LLM_PROVIDER=openai in .env
# To switch models:    set LLM_MODEL=gemini-1.5-pro  (or gpt-4o, etc.) in .env
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")
LLM_MODEL    = os.getenv("LLM_MODEL",    "mixtral-8x7b-32768")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GROQ_API_KEY   = os.getenv("GROQ_API_KEY")

# ── Vanna / NLQ settings ──────────────────────────────────────────────────────
VANNA_CHROMA_PATH = os.getenv("VANNA_CHROMA_PATH", "./vanna_chroma_db")
MAX_SQL_RETRIES   = int(os.getenv("MAX_SQL_RETRIES", "2"))
LIDA_MAX_GOALS    = int(os.getenv("LIDA_MAX_GOALS", "3"))
