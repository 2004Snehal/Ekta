"""
LIDA insight engine (Step 4 — optional).

Only invoked when request.explore == True.
LIDA analyses the Pandas DataFrame returned by SQL execution and generates
additional chart goals + Vega-Lite / JSON chart specs.

Returns a list of LidaInsight objects.
"""

from typing import List

import pandas as pd

from app.config.settings import get_settings
from app.models.response_models import LidaInsight
from app.utils.logger import get_logger

logger = get_logger("nlq.lida")


def generate_insights(df: pd.DataFrame, question: str, user_role: str | None = None) -> List[LidaInsight]:
    """
    Use LIDA to generate additional visualizations and insights from `df`.

    Args:
        df:        Pandas DataFrame (result of SQL query).
        question:  Original user question (used as context for goal generation).

    Returns:
        List of LidaInsight objects, each with a title and chart_spec dict.
        Returns an empty list if LIDA is unavailable or the DataFrame is empty.
    """
    if df.empty:
        logger.info("LIDA skipped — empty DataFrame.")
        return []

    try:
        from lida import Manager, TextGenerationConfig, llm as lida_llm
    except ImportError:
        logger.warning("LIDA not installed. Install 'lida' to enable insights.")
        return []

    settings = get_settings()

    try:
        lida = _build_lida_manager(settings)
        textgen_config = TextGenerationConfig(
            n=1,
            temperature=0.2,
            use_cache=True,
        )

        logger.info("LIDA: summarising DataFrame (%d rows)…", len(df))
        summary = lida.summarize(df, summary_method="default", textgen_config=textgen_config)

        logger.info("LIDA: generating up to %d goals…", settings.lida_max_goals)
        # Build role-aware persona context for LIDA goal generation
        from app.services.role_config import get_role_config
        role_cfg = get_role_config(user_role)
        persona = (
            f"You are generating insights for a {role_cfg.display_name}. {role_cfg.lida_context}"
            if role_cfg
            else "You are a data analyst generating insights from query results."
        )
        goals = lida.goals(
            summary,
            n=settings.lida_max_goals,
            persona=persona,
            textgen_config=textgen_config,
        )

        insights: List[LidaInsight] = []
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
                    insights.append(
                        LidaInsight(title=goal.question, chart_spec=spec)
                    )
            except Exception as chart_exc:
                logger.warning("LIDA chart generation failed for goal '%s': %s", goal.question, chart_exc)

        logger.info("LIDA generated %d insights.", len(insights))
        return insights

    except Exception as exc:
        logger.error("LIDA insight generation failed: %s", exc, exc_info=True)
        return []


class _GeminiTextGen:
    """
    Minimal LIDA-compatible text generator backed by Google Gemini.
    LIDA calls text_gen.generate(messages, config) and reads result.text[0].content.content.
    """

    def __init__(self, api_key: str, model_name: str):
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model_name)
        self.provider = "google"
        self.model_name = model_name

    def generate(self, messages, config=None, **kwargs):
        from types import SimpleNamespace

        if isinstance(messages, list):
            prompt = "\n".join(
                m.get("content", "") if isinstance(m, dict) else str(m)
                for m in messages
            )
        else:
            prompt = str(messages)

        response = self._model.generate_content(prompt)
        text = response.text
        # LIDA accesses result.text[0]["content"] — must be a dict
        return SimpleNamespace(text=[{"content": text}], config=config)


def _build_lida_manager(settings):
    """Build a LIDA Manager using the configured LLM provider."""
    from lida import Manager, llm as lida_llm

    if settings.llm_provider == "openai":
        text_gen = lida_llm("openai", api_key=settings.openai_api_key)
        logger.info("LIDA using OpenAI backend.")
    else:
        # Use custom Gemini adapter — no OpenAI key needed
        text_gen = _GeminiTextGen(
            api_key=settings.gemini_api_key,
            model_name=settings.gemini_model,
        )
        logger.info("LIDA using Gemini backend (%s).", settings.gemini_model)

    return Manager(text_gen=text_gen)


def _extract_spec(chart_object, df: pd.DataFrame | None = None) -> dict:
    """
    Pull the Vega-Lite spec out of a LIDA chart object and embed the data.

    Altair's to_dict() does not embed the DataFrame by default — the spec
    references a named dataset that only exists in Python memory.
    We inject the data as inline JSON so the frontend can render it.
    """
    import json

    spec = getattr(chart_object, "spec", None)
    if spec is None:
        return {}

    # Altair Chart object → convert to Vega-Lite dict
    if hasattr(spec, "to_dict"):
        try:
            spec_dict = spec.to_dict()
        except Exception:
            return {}
    elif isinstance(spec, dict):
        spec_dict = spec
    else:
        return {}

    # Embed data inline if the spec references a named dataset but has no values
    if df is not None and not df.empty:
        has_inline_data = (
            isinstance(spec_dict.get("data"), dict)
            and "values" in spec_dict.get("data", {})
        )
        if not has_inline_data:
            # Convert DataFrame to records, coercing types for JSON serialisation
            records = json.loads(df.to_json(orient="records", default_handler=str))
            spec_dict["data"] = {"values": records}

    return spec_dict
