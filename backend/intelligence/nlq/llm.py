"""
LLM abstraction layer.
Switching providers: set LLM_PROVIDER=openai (or gemini) in .env.
Switching models:    set LLM_MODEL=<model_name> in .env.
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from config import LLM_PROVIDER, LLM_MODEL, GOOGLE_API_KEY, OPENAI_API_KEY


# ── System prompt for the answer narrator ────────────────────────────────────
_ANSWER_SYSTEM_PROMPT = """You are a media analytics assistant. Your job is to answer a user's question
directly and concisely using the actual query results provided.

RULES:
- Answer in 1–3 sentences maximum.
- Use specific names, numbers, and percentages from the data — never be vague.
- Never say "based on the data", "the query shows", "the results indicate", or similar meta-phrases.
  Just state the answer as a fact.
- For "which X is highest/lowest" questions: name the winner and its value, then optionally mention second place.
- For trend questions: describe the direction and the key turning point or peak/trough with its value.
- For comparison questions: highlight the most notable contrast with real numbers.
- For totals/counts: give the exact number and any useful context from the data.
- For distribution/mix questions: name the top 1–2 categories and their share or count.
- If the data is empty, say "No data was found for this query."
- Do NOT repeat the question back. Do NOT describe the chart. Do NOT explain what the numbers mean conceptually.
"""


def call_llm(system_prompt: str, user_message: str) -> dict:
    """
    Call 1: generate SQL + chart spec from a question.
    Returns parsed JSON dict from the model response.
    """
    if LLM_PROVIDER == "gemini":
        return _call_gemini(system_prompt, user_message)
    elif LLM_PROVIDER == "openai":
        return _call_openai(system_prompt, user_message)
    else:
        raise ValueError(f"Unknown LLM_PROVIDER '{LLM_PROVIDER}'. Use 'gemini' or 'openai'.")


def generate_answer(question: str, data_rows: list) -> str:
    """
    Call 2: given the actual query results, produce a direct plain-English answer.
    Sends only the top 15 rows to keep the call cheap.
    Returns a string (falls back gracefully on any error).
    """
    if not data_rows:
        return "No data was found for this query."

    sample = data_rows[:15]
    user_message = f"Question: {question}\n\nQuery results (top {len(sample)} rows):\n{json.dumps(sample, default=str)}"

    try:
        if LLM_PROVIDER == "gemini":
            return _call_gemini_text(_ANSWER_SYSTEM_PROMPT, user_message)
        elif LLM_PROVIDER == "openai":
            return _call_openai_text(_ANSWER_SYSTEM_PROMPT, user_message)
    except Exception:
        pass

    # Silent fallback — don't break the response if answer generation fails
    return ""


# ── Gemini ────────────────────────────────────────────────────────────────────

def _call_gemini(system_prompt: str, user_message: str) -> dict:
    try:
        import google.genai as genai
    except ImportError:
        raise ImportError("google-genai is not installed. Run: pip install google-genai")

    if not GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY is not set in .env")

    client = genai.Client(api_key=GOOGLE_API_KEY)
    response = client.models.generate_content(
        model=LLM_MODEL,
        contents=user_message,
        config={
            "system_instruction": system_prompt,
            "response_mime_type": "application/json",
        },
    )
    return json.loads(response.text)


def _call_gemini_text(system_prompt: str, user_message: str) -> str:
    try:
        import google.genai as genai
    except ImportError:
        raise ImportError("google-genai is not installed. Run: pip install google-genai")

    client = genai.Client(api_key=GOOGLE_API_KEY)
    response = client.models.generate_content(
        model=LLM_MODEL,
        contents=user_message,
        config={"system_instruction": system_prompt},
    )
    return response.text.strip()


# ── OpenAI ────────────────────────────────────────────────────────────────────

def _call_openai(system_prompt: str, user_message: str) -> dict:
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("openai is not installed. Run: pip install openai")

    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set in .env")

    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


def _call_openai_text(system_prompt: str, user_message: str) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("openai is not installed. Run: pip install openai")

    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
    )
    return response.choices[0].message.content.strip()
