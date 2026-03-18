"""
LIDA insight engine — optional Step 4, only runs when explore=True.

Analyses the Pandas DataFrame from SQL execution and generates additional
chart goals + Vega-Lite specs using LIDA + Altair.
"""

import logging
import sys
import os
from typing import List

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from backend_config import LLM_PROVIDER, LLM_MODEL, GOOGLE_API_KEY, OPENAI_API_KEY, GROQ_API_KEY, LIDA_MAX_GOALS

logger = logging.getLogger("nlq.lida")


def generate_insights(df: pd.DataFrame, question: str, user_role: str = None) -> List[dict]:
    """
    Use LIDA to generate additional visualizations from the query DataFrame.
    Returns a list of {"title": str, "chart_spec": dict} dicts.
    Returns [] if LIDA is not installed, the DataFrame is empty, or any error occurs.
    """
    if df.empty:
        logger.info("LIDA skipped — empty DataFrame.")
        return []

    try:
        from lida import Manager, TextGenerationConfig
    except ImportError:
        logger.warning("LIDA not installed — skipping insights. Run: pip install lida")
        return []

    try:
        lida = _build_lida_manager()
        textgen_config = TextGenerationConfig(n=1, temperature=0.2, use_cache=True)

        logger.info("LIDA summarising DataFrame (%d rows)…", len(df))
        summary = lida.summarize(df, summary_method="default", textgen_config=textgen_config)

        from intelligence.nlq.role_config import get_role_config
        role_cfg = get_role_config(user_role)
        persona = (
            f"You are generating insights for a {role_cfg.display_name}. {role_cfg.lida_context}"
            if role_cfg
            else "You are a data analyst generating insights from query results."
        )

        logger.info("LIDA generating up to %d goals…", LIDA_MAX_GOALS)
        goals = lida.goals(summary, n=LIDA_MAX_GOALS, persona=persona, textgen_config=textgen_config)

        insights = []
        for goal in goals:
            try:
                charts = lida.visualize(
                    summary=summary,
                    goal=goal,
                    textgen_config=textgen_config,
                    library="altair",
                )
                if charts:
                    spec = _extract_spec(charts[0], df=df)
                    insights.append({"title": goal.question, "chart_spec": spec})
            except Exception as chart_exc:
                logger.warning("LIDA chart failed for goal '%s': %s", goal.question, chart_exc)

        logger.info("LIDA generated %d insights.", len(insights))
        return insights

    except Exception as exc:
        logger.error("LIDA insight generation failed: %s", exc, exc_info=True)
        return []


# ── LLM backend adapters ──────────────────────────────────────────────────────

class _GroqTextGen:
    """LIDA-compatible text generator backed by Groq SDK."""

    def __init__(self):
        from groq import Groq
        self._client = Groq(api_key=GROQ_API_KEY)
        self._model = LLM_MODEL
        self.provider = "openai"   # LIDA expects "openai" style interface
        self.model_name = LLM_MODEL

    def generate(self, messages, config=None, **kwargs):
        from types import SimpleNamespace
        if isinstance(messages, list):
            groq_messages = [
                {"role": m.get("role", "user"), "content": m.get("content", "")}
                if isinstance(m, dict) else {"role": "user", "content": str(m)}
                for m in messages
            ]
        else:
            groq_messages = [{"role": "user", "content": str(messages)}]

        response = self._client.chat.completions.create(
            model=self._model,
            messages=groq_messages,
            temperature=getattr(config, "temperature", 0.2) if config else 0.2,
        )
        content = response.choices[0].message.content
        return SimpleNamespace(text=[{"content": content}], config=config)


class _GeminiTextGen:
    """LIDA-compatible text generator backed by google.genai (new SDK)."""

    def __init__(self):
        import google.genai as genai
        self._client = genai.Client(api_key=GOOGLE_API_KEY)
        self._model = LLM_MODEL
        self.provider = "google"
        self.model_name = LLM_MODEL

    def generate(self, messages, config=None, **kwargs):
        from types import SimpleNamespace
        if isinstance(messages, list):
            prompt = "\n".join(
                m.get("content", "") if isinstance(m, dict) else str(m)
                for m in messages
            )
        else:
            prompt = str(messages)
        response = self._client.models.generate_content(model=self._model, contents=prompt)
        return SimpleNamespace(text=[{"content": response.text}], config=config)


def _build_lida_manager():
    from lida import Manager, llm as lida_llm

    if LLM_PROVIDER == "groq":
        text_gen = _GroqTextGen()
        logger.info("LIDA using Groq backend (%s).", LLM_MODEL)
    elif LLM_PROVIDER == "openai":
        text_gen = lida_llm("openai", api_key=OPENAI_API_KEY)
        logger.info("LIDA using OpenAI backend.")
    else:
        text_gen = _GeminiTextGen()
        logger.info("LIDA using Gemini backend (%s).", LLM_MODEL)

    return Manager(text_gen=text_gen)


# ── Spec extraction ───────────────────────────────────────────────────────────

def _extract_spec(chart_object, df: pd.DataFrame = None) -> dict:
    """
    Extract the Vega-Lite spec and embed inline data so the frontend
    can render it without a second API call.
    """
    import json as _json

    spec = getattr(chart_object, "spec", None)
    if spec is None:
        return {}

    if hasattr(spec, "to_dict"):
        try:
            spec_dict = spec.to_dict()
        except Exception:
            return {}
    elif isinstance(spec, dict):
        spec_dict = spec
    else:
        return {}

    # Embed data inline if not already present
    if df is not None and not df.empty:
        has_inline = isinstance(spec_dict.get("data"), dict) and "values" in spec_dict.get("data", {})
        if not has_inline:
            records = _json.loads(df.to_json(orient="records", default_handler=str))
            spec_dict["data"] = {"values": records}

    return spec_dict
