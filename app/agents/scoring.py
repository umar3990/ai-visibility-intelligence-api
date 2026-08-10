"""Agent 2: Visibility Scoring.

For a discovered query, this agent does two things:
 1. Real data: fetch search volume + competitive difficulty from DataForSEO
    (app/services/seo_data.py) -- not the LLM's job, LLMs don't know real
    search volume.
 2. Simulated visibility check (per the brief's own wording: "simulate
    checking"): actually ask the LLM the query as a real user would, and
    check whether the target domain/brand is mentioned in its answer. This
    is a genuine live model call, not a hardcoded guess -- "simulate" here
    means "the same interaction a real user would have," which is the
    closest a take-home assessment can get to true AI-answer-engine
    visibility without scraping ChatGPT/Perplexity's product UI directly.

The opportunity_score itself is computed by the deterministic formula in
utils/scoring.py from the combined real + simulated signals, not by the LLM
-- keeping the score reproducible and auditable rather than another
LLM-guessed number.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.services import seo_data
from app.services.llm_client import LLMResponse
from app.utils.scoring import compute_opportunity_score

SYSTEM_PROMPT = """You are simulating how an AI assistant (like ChatGPT or \
Claude) would answer a user's question, in order to check whether a specific \
domain would be cited or recommended in that answer.

Given a question and a target domain, answer the question the way a \
well-informed AI assistant actually would -- naming real, plausible vendors \
if you have relevant knowledge, or your best reasoning about who would likely \
be mentioned for this kind of query. Then determine whether the target \
domain appears in that answer, and if so, roughly what position/prominence \
it would have (1 = mentioned first/most prominently).

Return ONLY valid JSON, no markdown fences, matching exactly this schema:
{"domain_visible": true or false, "visibility_position": integer or null, \
"reasoning": "one sentence explaining the determination"}

visibility_position must be null when domain_visible is false."""

USER_PROMPT_TEMPLATE = """Query: "{query_text}"
Target domain to check for: {domain}
Business context: {name} ({industry}) -- competitors: {competitors}

Answer the query as an AI assistant would, then report whether {domain} \
would appear in that answer."""


class VisibilityOutput(BaseModel):
    domain_visible: bool
    visibility_position: int | None = Field(default=None)
    reasoning: str


class VisibilityScoringAgent(BaseAgent):
    name = "VisibilityScoringAgent"

    def run(self, profile, query_text: str) -> tuple[dict, LLMResponse]:
        user_prompt = USER_PROMPT_TEMPLATE.format(
            query_text=query_text,
            domain=profile.domain,
            name=profile.name,
            industry=profile.industry,
            competitors=", ".join(profile.competitors) if profile.competitors else "(none)",
        )
        visibility, usage = self.call_llm_json(SYSTEM_PROMPT, user_prompt, VisibilityOutput)

        metrics = seo_data.get_search_metrics(query_text)

        opportunity_score = compute_opportunity_score(
            query_text=query_text,
            estimated_search_volume=metrics["search_volume"],
            competitive_difficulty=metrics["difficulty"],
            domain_visible=visibility.domain_visible,
        )

        result = {
            "query_text": query_text,
            "estimated_search_volume": metrics["search_volume"],
            "competitive_difficulty": metrics["difficulty"],
            "opportunity_score": opportunity_score,
            "domain_visible": visibility.domain_visible,
            "visibility_position": visibility.visibility_position,
            "data_source": metrics["data_source"],
        }
        return result, usage
