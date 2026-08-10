"""Agent 1: Query Discovery.

Given a business profile, generates 10-20 realistic, commercially-relevant
natural-language questions users would ask an AI assistant in this space.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.services.llm_client import LLMResponse

SYSTEM_PROMPT = """You are a search-intent research analyst for an AI-visibility \
platform. Your job is to generate the exact questions real buyers type into AI \
assistants (ChatGPT, Claude, Perplexity) when they are researching or comparing \
products in a given competitive space.

Rules:
- Generate 10 to 20 questions. No fewer than 10, no more than 20.
- Every question must be natural language, phrased the way a real person types \
it into a chat box -- not a keyword fragment. "best SEO content tool" is a \
keyword; "What's the best AI tool for writing SEO content briefs?" is a question.
- Mix question types: some direct comparisons ("X vs Y"), some "best of" / \
recommendation questions, some how-to / evaluative questions relevant to \
choosing a vendor in this space.
- Every question must be commercially relevant -- i.e. the answer would \
plausibly mention specific vendors or products, not just general education.
- Do not repeat the same question with trivial rewording.
- Return ONLY valid JSON, no markdown fences, matching exactly this schema:
{"queries": ["question 1", "question 2", ...]}
"""

USER_PROMPT_TEMPLATE = """Business profile:
- Name: {name}
- Domain: {domain}
- Industry: {industry}
- Description: {description}
- Known competitors: {competitors}

Generate the discovery query set for this business."""


class DiscoveryOutput(BaseModel):
    queries: list[str] = Field(min_length=10, max_length=20)


class QueryDiscoveryAgent(BaseAgent):
    name = "QueryDiscoveryAgent"

    def run(self, profile) -> tuple[list[str], LLMResponse]:
        user_prompt = USER_PROMPT_TEMPLATE.format(
            name=profile.name,
            domain=profile.domain,
            industry=profile.industry,
            description=profile.description or "(none provided)",
            competitors=", ".join(profile.competitors) if profile.competitors else "(none provided)",
        )
        result, usage = self.call_llm_json(SYSTEM_PROMPT, user_prompt, DiscoveryOutput)
        return result.queries, usage
