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
LLM_BASE_URL = "https://openrouter.ai/api/v1"

# ── Change model names here ───────────────────────────────────────────────────

# NLQ / SQL generation (Vanna), LIDA, KPI registry, answer generation
QWEN_CODER_MODEL   = "meta-llama/llama-3.2-3b-instruct"

# Insight Narrator, Chart Insight Agent
QWEN_INSIGHT_MODEL = "meta-llama/llama-3.2-3b-instruct"

# Global Parameters
LLM_MAX_TOKENS     = 4096
LLM_TEMPERATURE    = 0.2

# ─────────────────────────────────────────────────────────────────────────────


def make_openai_client():
    """Return an openai.OpenAI client pointed at the configured provider."""
    from openai import OpenAI
    return OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
