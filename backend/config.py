import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set. Add it to your .env file.")

# ── LLM settings ─────────────────────────────────────────────────────────────
# To switch providers: set LLM_PROVIDER=openai in .env
# To switch models:    set LLM_MODEL=gemini-1.5-pro  (or gpt-4o, etc.) in .env
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")   # "gemini" | "openai"
LLM_MODEL    = os.getenv("LLM_MODEL",    "gemini-2.5-flash")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
