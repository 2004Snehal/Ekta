"""
Central LLM configuration — OpenAI-compatible providers (OpenRouter, Together AI, etc.)

To switch providers:  change LLM_BASE_URL below
To swap models:       change QWEN_CODER_MODEL or QWEN_INSIGHT_MODEL below
API key:              set LLM_API_KEY in .env

Together AI  → https://api.together.xyz/v1
OpenRouter   → https://openrouter.ai/api/v1
"""
import os
from dotenv import load_dotenv

load_dotenv()

LLM_API_KEY  = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = "https://api.together.xyz/v1"

# ── Change model names here ───────────────────────────────────────────────────

# NLQ / SQL generation (Vanna), LIDA, KPI registry, answer generation
QWEN_CODER_MODEL   = "Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8"

# Insight Narrator, Chart Insight Agent
QWEN_INSIGHT_MODEL = "Qwen/Qwen3.5-397B-A17B"

# ─────────────────────────────────────────────────────────────────────────────


def make_openai_client():
    """Return an openai.OpenAI client pointed at the configured provider."""
    from openai import OpenAI
    return OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
