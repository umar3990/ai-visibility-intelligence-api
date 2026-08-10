"""Shared base for all three agents: LLM call + strict JSON parsing with a
single repair retry, so a malformed LLM response can't crash the pipeline
(Must-Have #5 in the brief).

Design: agents are NOT a class hierarchy sharing mutable state (the rubric
explicitly downgrades "agents exist but share state"). BaseAgent only holds
stateless helpers -- each concrete agent still builds its own prompts and
owns its own Pydantic schema.
"""
from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.services.llm_client import get_llm_client, LLMResponse

T = TypeVar("T", bound=BaseModel)

_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class AgentError(Exception):
    """Raised when an agent cannot produce valid output after retrying.
    Callers (the orchestrator) catch this to isolate failures per-item.
    """
    def __init__(self, agent_name: str, message: str, raw_output: str | None = None):
        self.agent_name = agent_name
        self.raw_output = raw_output
        super().__init__(f"[{agent_name}] {message}")


class BaseAgent:
    name: str = "BaseAgent"

    def _strip_fences(self, text: str) -> str:
        return _JSON_FENCE.sub("", text.strip()).strip()

    def call_llm_json(
        self,
        system: str,
        user: str,
        schema: type[T],
        max_tokens: int = 2048,
        provider: str | None = None,
    ) -> tuple[T, LLMResponse]:
        """Call the LLM, parse+validate JSON against `schema`. On invalid
        JSON or a schema mismatch, sends one repair prompt with the specific
        error before giving up.
        """
        client = get_llm_client(provider)
        response = client.complete(system=system, user=user, max_tokens=max_tokens)
        parsed, error = self._try_parse(response.text, schema)
        if parsed is not None:
            return parsed, response

        repair_user = (
            f"{user}\n\n---\n"
            f"Your previous response could not be parsed: {error}\n"
            f"Your previous response was:\n{response.text}\n\n"
            f"Return ONLY valid JSON matching the required schema. No markdown "
            f"fences, no commentary before or after the JSON."
        )
        repair_response = client.complete(system=system, user=repair_user, max_tokens=max_tokens)
        parsed, error = self._try_parse(repair_response.text, schema)
        if parsed is not None:
            combined = LLMResponse(
                text=repair_response.text,
                input_tokens=response.input_tokens + repair_response.input_tokens,
                output_tokens=response.output_tokens + repair_response.output_tokens,
                provider=repair_response.provider,
                model=repair_response.model,
            )
            return parsed, combined

        raise AgentError(self.name, f"invalid JSON after repair attempt: {error}", raw_output=repair_response.text)

    def _try_parse(self, text: str, schema: type[T]) -> tuple[T | None, str | None]:
        cleaned = self._strip_fences(text)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            return None, f"JSONDecodeError: {e}"
        try:
            return schema.model_validate(data), None
        except ValidationError as e:
            return None, f"ValidationError: {e}"
