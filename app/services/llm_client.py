"""Unified LLM client so agents don't care which provider is configured.

Model selection rationale (documented per the assessment's request):
Anthropic Claude is the default here because agents 1-3 all require strict
structured JSON output under a schema defined entirely in the prompt (no
function-calling/tool-use scaffolding is used, to keep the assessment's
prompt-engineering criterion meaningful -- the model has to follow the
written schema, not a passed-in tool spec). Claude models are consistently
strong at instruction-following for "return only JSON matching this shape"
style prompts without wrapping it in markdown fences, which reduces the
amount of defensive parsing needed in `agents/base.py`. OpenAI's GPT-4o is
wired up as a drop-in alternative (same interface) for teams that want
multi-model agents, e.g. a cheaper/faster model for Agent 1's broad query
generation and a stronger model for Agent 3's recommendation reasoning --
switch per-agent by passing a different `provider=` to `get_llm_client()`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from flask import current_app


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    provider: str
    model: str

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class LLMClient(Protocol):
    def complete(self, system: str, user: str, max_tokens: int = 2048) -> LLMResponse:
        ...


class AnthropicClient:
    def __init__(self, api_key: str, model: str):
        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def complete(self, system: str, user: str, max_tokens: int = 2048) -> LLMResponse:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(block.text for block in resp.content if block.type == "text")
        return LLMResponse(
            text=text,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            provider="anthropic",
            model=self._model,
        )


class OpenAIClient:
    def __init__(self, api_key: str, model: str):
        import openai
        self._client = openai.OpenAI(api_key=api_key)
        self._model = model

    def complete(self, system: str, user: str, max_tokens: int = 2048) -> LLMResponse:
        resp = self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        text = resp.choices[0].message.content or ""
        usage = resp.usage
        return LLMResponse(
            text=text,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            provider="openai",
            model=self._model,
        )


def get_llm_client(provider: str | None = None) -> LLMClient:
    cfg = current_app.config
    provider = provider or cfg["LLM_PROVIDER"]

    if provider == "anthropic":
        if not cfg.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is not set (check .env)")
        return AnthropicClient(cfg["ANTHROPIC_API_KEY"], cfg["ANTHROPIC_MODEL"])

    if provider == "openai":
        if not cfg.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is not set (check .env)")
        return OpenAIClient(cfg["OPENAI_API_KEY"], cfg["OPENAI_MODEL"])

    raise ValueError(f"Unknown LLM_PROVIDER: {provider!r} (expected 'anthropic' or 'openai')")
