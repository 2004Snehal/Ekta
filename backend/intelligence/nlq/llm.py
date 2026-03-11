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


def call_llm(system_prompt: str, user_message: str) -> dict:
    """
    Call the configured LLM with a system prompt + user message.
    Returns parsed JSON dict from the model response.
    Raises ValueError on bad JSON or missing keys.
    """
    if LLM_PROVIDER == "gemini":
        return _call_gemini(system_prompt, user_message)
    elif LLM_PROVIDER == "openai":
        return _call_openai(system_prompt, user_message)
    else:
        raise ValueError(f"Unknown LLM_PROVIDER '{LLM_PROVIDER}'. Use 'gemini' or 'openai'.")


def _call_gemini(system_prompt: str, user_message: str) -> dict:
    try:
        import google.generativeai as genai
    except ImportError:
        raise ImportError("google-generativeai is not installed. Run: pip install google-generativeai")

    if not GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY is not set in .env")

    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel(
        model_name=LLM_MODEL,
        system_instruction=system_prompt,
        generation_config={"response_mime_type": "application/json"},
    )
    response = model.generate_content(user_message)
    return json.loads(response.text)


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
