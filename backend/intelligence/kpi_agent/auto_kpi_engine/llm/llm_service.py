"""
LLM abstraction layer.
Agents must always call llm.generate(prompt) — never a vendor SDK directly.

Architecture:
    LLMProvider  (abstract base, defined here)
    ├── GroqProvider   → llm/groq_provider.py
    └── OpenAIProvider → llm/openai_provider.py

    LLMService (factory + singleton, defined here)
        Selects provider based on LLM_PROVIDER env variable.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from config.settings import settings

logger = logging.getLogger(__name__)


# ================================================================== #
# Abstract base — import this in provider files
# ================================================================== #

class LLMProvider(ABC):
    """Plug-in interface for any LLM backend."""

    @abstractmethod
    def generate(self, prompt: str, temperature: float = 0.2, max_tokens: int = 2048) -> str:
        """Send *prompt* and return the model's text response."""


# ================================================================== #
# Service / factory
# ================================================================== #

class LLMService:
    """
    Singleton-style service that wraps the configured LLM provider.
    Select provider via environment variable LLM_PROVIDER=groq|openai.
    """

    _instance: Optional["LLMService"] = None

    def __init__(self, provider: Optional[LLMProvider] = None) -> None:
        if provider is not None:
            self._provider = provider
        else:
            # Lazy import to avoid circular deps (providers import LLMProvider from here)
            if settings.llm_provider == "openai":
                from llm.openai_provider import OpenAIProvider  # noqa: PLC0415
                self._provider: LLMProvider = OpenAIProvider()
            else:
                from llm.groq_provider import GroqProvider  # noqa: PLC0415
                self._provider = GroqProvider()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def generate(self, prompt: str, temperature: float = 0.2, max_tokens: int = 2048) -> str:
        logger.debug(
            "LLM generate | provider=%s | prompt_len=%d",
            type(self._provider).__name__,
            len(prompt),
        )
        return self._provider.generate(prompt, temperature=temperature, max_tokens=max_tokens)

    # ------------------------------------------------------------------ #
    # Singleton helper
    # ------------------------------------------------------------------ #

    @classmethod
    def default(cls) -> "LLMService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
