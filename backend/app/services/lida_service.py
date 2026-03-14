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


def generate_insights(df: pd.DataFrame, question: str) -> List[LidaInsight]:
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
        goals = lida.goals(
            summary,
            n=settings.lida_max_goals,
            textgen_config=textgen_config,
        )

        insights: List[LidaInsight] = []
        for goal in goals:
            try:
                charts = lida.visualize(
                    summary=summary,
                    goal=goal,
                    textgen_config=textgen_config,
                    library="vega-lite",
                )
                if charts:
                    spec = _extract_spec(charts[0])
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


def _build_lida_manager(settings):
    """Build a LIDA Manager using the configured LLM provider."""
    from lida import Manager, llm as lida_llm

    if settings.llm_provider == "openai":
        text_gen = lida_llm("openai", api_key=settings.openai_api_key)
    else:
        # LIDA supports openai-compatible endpoints; use openai adapter with Gemini key
        # as LIDA's native Gemini support varies by version
        text_gen = lida_llm("openai", api_key=settings.openai_api_key)
        logger.warning(
            "LIDA does not have a native Gemini adapter. "
            "Using OpenAI adapter — ensure OPENAI_API_KEY is set as fallback."
        )

    return Manager(text_gen=text_gen)


def _extract_spec(chart_object) -> dict:
    """
    Pull the chart spec out of a LIDA chart object.
    LIDA chart objects expose .spec (dict) or .raster (base64 image).
    """
    if hasattr(chart_object, "spec") and chart_object.spec:
        return chart_object.spec if isinstance(chart_object.spec, dict) else {}
    return {}
