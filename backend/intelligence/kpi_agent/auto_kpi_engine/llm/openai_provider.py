"""OpenAI LLM provider."""

from __future__ import annotations

from typing import Any, Optional

from llm.llm_service import LLMProvider
from config.settings import settings


class OpenAIProvider(LLMProvider):
    """OpenAI API backend using the official `openai` SDK."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None) -> None:
        self._api_key = api_key or settings.openai_api_key
        self._model = model or settings.openai_model
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from openai import OpenAI  # type: ignore
            except ImportError as exc:
                raise ImportError("Install OpenAI SDK: pip install openai") from exc
            self._client = OpenAI(api_key=self._api_key)
        return self._client

    def generate(self, prompt: str, temperature: float = 0.2, max_tokens: int = 2048) -> str:
        client = self._get_client()
        response = client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()
