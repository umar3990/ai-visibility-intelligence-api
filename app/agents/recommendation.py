"""Agent 3: Content Recommendation.

Given the top-scoring queries where the target domain is NOT appearing,
generates 3-5 specific, actionable content recommendations.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.services.llm_client import LLMResponse

SYSTEM_PROMPT = """You are a content strategist for an AI-visibility platform. \
Given a set of high-opportunity queries where a business's domain is NOT \
currently appearing in AI-generated answers, recommend specific content to \
close that gap.

Rules:
- Generate 3 to 5 recommendations. No fewer than 3, no more than 5.
- Each recommendation must target one or more of the specific queries given \
-- do not write generic advice.
- content_type must be one of: blog_post, landing_page, faq, comparison_page.
- rationale must explain specifically why this content addresses the query \
gap (reference the query's topic, not just "improves SEO").
- target_keywords must be 3-6 concrete keywords/topics to cover, not \
single words repeated from the title.
- priority: "high" for queries with opportunity_score >= 0.7, "medium" for \
0.4-0.69, "low" below 0.4.
- Return ONLY valid JSON, no markdown fences, matching exactly this schema:
{"recommendations": [{"query_text": "...", "content_type": "...", "title": \
"...", "rationale": "...", "target_keywords": ["...", "..."], "priority": \
"high|medium|low"}]}

query_text must exactly match one of the queries given to you, so it can be \
mapped back to the right query record."""

USER_PROMPT_TEMPLATE = """Business: {name} ({domain}), industry: {industry}

High-opportunity queries where {domain} is NOT currently visible:
{queries_block}

Generate content recommendations to close these visibility gaps."""


class RecommendationItem(BaseModel):
    query_text: str
    content_type: str
    title: str
    rationale: str
    target_keywords: list[str] = Field(min_length=1)
    priority: str


class RecommendationOutput(BaseModel):
    recommendations: list[RecommendationItem] = Field(min_length=3, max_length=5)


class ContentRecommendationAgent(BaseAgent):
    name = "ContentRecommendationAgent"

    def run(self, profile, gap_queries: list[dict]) -> tuple[list[RecommendationItem], LLMResponse]:
        queries_block = "\n".join(
            f"- \"{q['query_text']}\" (opportunity_score={q['opportunity_score']}, "
            f"volume={q['estimated_search_volume']}, difficulty={q['competitive_difficulty']})"
            for q in gap_queries
        )
        user_prompt = USER_PROMPT_TEMPLATE.format(
            name=profile.name, domain=profile.domain, industry=profile.industry,
            queries_block=queries_block,
        )
        result, usage = self.call_llm_json(SYSTEM_PROMPT, user_prompt, RecommendationOutput)
        return result.recommendations, usage
