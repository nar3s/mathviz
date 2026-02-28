"""
Provider-agnostic LLM client abstraction.

Supported providers:
  - "claude"  → Anthropic Claude API  (pip install anthropic)
  - "openai"  → OpenAI Chat API       (pip install openai)

Usage:
    from generator.llm_client import get_llm_client
    client = get_llm_client(settings)
    text = await client.complete(system="...", user="...", max_tokens=800)

To switch providers: set LLM_PROVIDER, LLM_MODEL, and LLM_API_KEY in .env.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

log = logging.getLogger(__name__)

# ── Per-model pricing (USD per 1M tokens) ─────────────────────────────────────
# Claude: https://www.anthropic.com/pricing
# OpenAI: https://openai.com/pricing
_PRICING: dict[str, tuple[float, float]] = {
    # model-id-prefix → (input $/1M, output $/1M)
    "claude-opus-4-6":   (5.00,  25.00),
    "claude-opus-4-5":   (15.00, 75.00),
    "claude-sonnet-4-6": (3.00,  15.00),
    "claude-sonnet-4-5": (3.00,  15.00),
    "claude-haiku-4-5":  (1.00,   5.00),
    "gpt-4o":            (2.50,  10.00),
    "gpt-4o-mini":       (0.15,   0.60),
    "gpt-4-turbo":       (10.00, 30.00),
    "gpt-3.5-turbo":     (0.50,   1.50),
}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return estimated USD cost for a single call."""
    for prefix, (in_rate, out_rate) in _PRICING.items():
        if model.startswith(prefix):
            return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000
    return 0.0  # unknown model — can't estimate


def _log_usage(model: str, input_tokens: int, output_tokens: int, label: str = "") -> None:
    cost = _estimate_cost(model, input_tokens, output_tokens)
    tag = f"[{label}] " if label else ""
    log.info(
        "%sTokens — in: %d, out: %d | Cost: $%.6f  (model: %s)",
        tag, input_tokens, output_tokens, cost, model,
    )


class LLMClient(ABC):
    """Abstract base for all LLM providers."""

    @abstractmethod
    async def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 800,
        temperature: float = 0.7,
        label: str = "",
    ) -> str:
        """
        Send a system + user prompt and return the model's text response.

        Args:
            system:      System prompt (instructions/persona).
            user:        User message (the actual request).
            max_tokens:  Maximum tokens to generate.
            temperature: Sampling temperature (0.0 = deterministic).
            label:       Short label shown in cost log (e.g. "outline", "chapter:hook").

        Returns:
            The model's response as a plain string.
        """


class ClaudeClient(LLMClient):
    """Anthropic Claude API client (async)."""

    def __init__(self, api_key: str, model: str) -> None:
        try:
            import anthropic as _anthropic
        except ImportError as exc:
            raise ImportError(
                "anthropic package not found. Install with: pip install anthropic"
            ) from exc
        self._client = _anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 800,
        temperature: float = 0.7,
        label: str = "",
    ) -> str:
        response = await self._client.messages.create(
            model=self._model,
            system=system,
            messages=[{"role": "user", "content": user}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        _log_usage(
            self._model,
            response.usage.input_tokens,
            response.usage.output_tokens,
            label=label or "claude",
        )
        return response.content[0].text


class OpenAIClient(LLMClient):
    """OpenAI Chat Completions API client (async)."""

    def __init__(self, api_key: str, model: str) -> None:
        try:
            import openai as _openai
        except ImportError as exc:
            raise ImportError(
                "openai package not found. Install with: pip install openai"
            ) from exc
        self._client = _openai.AsyncOpenAI(api_key=api_key)
        self._model = model

    async def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 800,
        temperature: float = 0.7,
        label: str = "",
    ) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        usage = response.usage
        _log_usage(
            self._model,
            usage.prompt_tokens,
            usage.completion_tokens,
            label=label or "openai",
        )
        return response.choices[0].message.content


def get_llm_client(settings) -> LLMClient:
    """
    Factory: read settings and return the appropriate LLMClient.

    Raises:
        ValueError: if LLM_API_KEY is empty or LLM_PROVIDER is unknown.
    """
    provider = (settings.llm_provider or "").lower()
    if not settings.llm_api_key:
        raise ValueError(
            f"LLM_API_KEY is not set. Add it to .env for provider '{provider}'."
        )
    if provider == "claude":
        return ClaudeClient(api_key=settings.llm_api_key, model=settings.llm_model)
    if provider == "openai":
        return OpenAIClient(api_key=settings.llm_api_key, model=settings.llm_model)
    raise ValueError(
        f"Unknown LLM_PROVIDER: '{provider}'. Supported values: 'claude', 'openai'."
    )
