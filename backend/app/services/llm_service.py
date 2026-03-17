"""
LLM abstraction layer.

Supports OpenAI (GPT-4o), Google Gemini, and Groq interchangeably.
Switch providers by setting LLM_PROVIDER=openai|gemini|groq in .env.

All callers use `call_llm(prompt)` — provider details are hidden here.
"""

import time
from typing import Optional

from app.config.settings import get_settings
from app.utils.logger import get_logger

logger = get_logger("nlq.llm")


def _is_quota_error(exc: Exception) -> bool:
    """Return True if the exception is a 429 / quota-exceeded error."""
    msg = str(exc).lower()
    return "429" in msg or "quota" in msg or "rate limit" in msg or "resource_exhausted" in msg


def _parse_retry_delay(exc: Exception, fallback: float = 5.0) -> float:
    """Extract the suggested retry delay (seconds) from a Gemini 429 error message."""
    import re
    match = re.search(r'retry_delay\s*\{\s*seconds:\s*(\d+(?:\.\d+)?)', str(exc))
    if match:
        return float(match.group(1)) + 1.0  # add 1s buffer
    return fallback


def _retry_llm(fn, *args, max_retries: int = 3, **kwargs):
    """
    Call fn(*args, **kwargs) with retries on quota/rate-limit errors.
    Uses the retry_delay from the API response when available, otherwise exponential backoff.
    Raises the last exception if all retries are exhausted.
    """
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            if _is_quota_error(exc) and attempt < max_retries - 1:
                wait = _parse_retry_delay(exc, fallback=5.0 * (2 ** attempt))
                logger.warning(
                    "LLM quota/rate-limit error (attempt %d/%d) — retrying in %.1fs.",
                    attempt + 1, max_retries, wait,
                )
                time.sleep(wait)
            else:
                raise


def call_llm(prompt: str, system: Optional[str] = None) -> str:
    """
    Send a prompt to the configured LLM and return the text response.

    Args:
        prompt:  User-side prompt content.
        system:  Optional system instruction (used where supported).

    Returns:
        Plain text response from the LLM.
    """
    settings = get_settings()
    provider = settings.llm_provider.lower()

    logger.info("LLM call → provider=%s, prompt_len=%d", provider, len(prompt))

    if provider == "openai":
        return _retry_llm(_call_openai, prompt, system)
    elif provider == "gemini":
        return _retry_llm(_call_gemini, prompt, system)
    elif provider == "groq":
        return _retry_llm(_call_groq, prompt, system)
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: '{provider}'. Use 'openai', 'gemini', or 'groq'.")


# ── OpenAI ────────────────────────────────────────────────────────────────────

def _call_openai(prompt: str, system: Optional[str]) -> str:
    from openai import OpenAI  # lazy import — only needed if provider=openai

    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=messages,
        temperature=0.2,
    )
    text = response.choices[0].message.content or ""
    logger.info("OpenAI response received (%d chars).", len(text))
    return text.strip()


# ── Gemini ────────────────────────────────────────────────────────────────────

def _call_gemini(prompt: str, system: Optional[str]) -> str:
    import google.generativeai as genai  # lazy import — only needed if provider=gemini

    settings = get_settings()
    genai.configure(api_key=settings.gemini_api_key)

    full_prompt = f"{system}\n\n{prompt}" if system else prompt
    model = genai.GenerativeModel(settings.gemini_model)
    response = model.generate_content(full_prompt)
    text = response.text or ""
    logger.info("Gemini response received (%d chars).", len(text))
    return text.strip()


# ── Groq ──────────────────────────────────────────────────────────────────────

def _call_groq(prompt: str, system: Optional[str]) -> str:
    from groq import Groq  # lazy import — only needed if provider=groq

    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key)

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=settings.groq_model,
        messages=messages,
        temperature=0.2,
    )
    text = response.choices[0].message.content or ""
    logger.info("Groq response received (%d chars).", len(text))
    return text.strip()


# ── Answer generator (Step 5) ─────────────────────────────────────────────────

def generate_answer(question: str, sql: str, data: list, user_role: str | None = None) -> str:
    """
    Produce a short plain-English analytics answer given the question,
    the SQL that was run, and the rows returned.
    Role-aware: tailors tone and focus to the user's persona.
    """
    from app.services.role_config import get_role_config

    role_cfg = get_role_config(user_role)
    system_prompt = role_cfg.answer_persona if role_cfg else "You are a helpful data analytics assistant."

    # Limit data preview to 20 rows to stay within token limits
    preview = data[:20]

    role_instruction = (
        f"\nYou are answering for a {role_cfg.display_name}. {role_cfg.answer_persona}"
        if role_cfg else ""
    )

    prompt = f"""A user asked the following analytics question:{role_instruction}

Question: {question}

SQL executed:
{sql}

Results (up to 20 rows):
{preview}

Generate a clear, concise analytics answer in 2–4 sentences.
Focus on key numbers, trends, or comparisons visible in the data.
Do not mention SQL or technical details.
"""
    return call_llm(prompt, system=system_prompt)
