"""
LLM abstraction layer.

Supports OpenAI (GPT-4o) and Google Gemini interchangeably.
Switch providers by setting LLM_PROVIDER=openai|gemini in .env.

All callers use `call_llm(prompt)` — provider details are hidden here.
"""

from typing import Optional

from app.config.settings import get_settings
from app.utils.logger import get_logger

logger = get_logger("nlq.llm")


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
        return _call_openai(prompt, system)
    elif provider == "gemini":
        return _call_gemini(prompt, system)
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: '{provider}'. Use 'openai' or 'gemini'.")


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


# ── Answer generator (Step 5) ─────────────────────────────────────────────────

def generate_answer(question: str, sql: str, data: list) -> str:
    """
    Produce a short plain-English analytics answer given the question,
    the SQL that was run, and the rows returned.
    """
    # Limit data preview to 20 rows to stay within token limits
    preview = data[:20]

    prompt = f"""You are a data analyst. A user asked the following question about their data:

Question: {question}

The following SQL query was executed:
{sql}

The query returned these results (up to 20 rows shown):
{preview}

Generate a clear, concise analytics answer in 2–4 sentences.
Focus on key numbers, trends, or comparisons visible in the data.
Do not mention SQL or technical details.
"""
    return call_llm(prompt, system="You are a helpful data analytics assistant.")
