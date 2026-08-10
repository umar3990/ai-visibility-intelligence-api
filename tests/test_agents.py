"""Agent-level unit tests using mocked LLM responses (no real API calls),
per the assessment's bonus criterion: 'Unit tests for agent logic using
mocked LLM responses.'
"""
import json
import pytest
from unittest.mock import patch

from app.agents.base import AgentError
from app.agents.discovery import QueryDiscoveryAgent
from app.agents.scoring import VisibilityScoringAgent
from app.agents.recommendation import ContentRecommendationAgent
from app.services.llm_client import LLMResponse
from tests.conftest import FakeProfile


def _fake_response(text: str) -> LLMResponse:
    return LLMResponse(text=text, input_tokens=10, output_tokens=10, provider="anthropic", model="test-model")


class TestQueryDiscoveryAgent:
    def test_happy_path_returns_10_to_20_queries(self, app):
        valid = json.dumps({"queries": [f"Question {i}?" for i in range(15)]})
        with app.app_context(), patch(
            "app.services.llm_client.AnthropicClient.complete",
            lambda self, system, user, max_tokens=2048: _fake_response(valid),
        ):
            queries, usage = QueryDiscoveryAgent().run(FakeProfile())
        assert 10 <= len(queries) <= 20

    def test_markdown_fenced_json_is_still_parsed(self, app):
        valid = "```json\n" + json.dumps({"queries": [f"Q{i}?" for i in range(10)]}) + "\n```"
        with app.app_context(), patch(
            "app.services.llm_client.AnthropicClient.complete",
            lambda self, system, user, max_tokens=2048: _fake_response(valid),
        ):
            queries, usage = QueryDiscoveryAgent().run(FakeProfile())
        assert len(queries) == 10

    def test_schema_violation_triggers_one_repair_then_recovers(self, app):
        too_few = json.dumps({"queries": ["only one"]})
        valid = json.dumps({"queries": [f"Q{i}?" for i in range(11)]})
        calls = {"n": 0}

        def fake_complete(self, system, user, max_tokens=2048):
            calls["n"] += 1
            return _fake_response(too_few if calls["n"] == 1 else valid)

        with app.app_context(), patch("app.services.llm_client.AnthropicClient.complete", fake_complete):
            queries, usage = QueryDiscoveryAgent().run(FakeProfile())
        assert calls["n"] == 2
        assert len(queries) == 11

    def test_permanently_malformed_output_raises_agent_error_not_a_crash(self, app):
        with app.app_context(), patch(
            "app.services.llm_client.AnthropicClient.complete",
            lambda self, system, user, max_tokens=2048: _fake_response("not json"),
        ):
            with pytest.raises(AgentError):
                QueryDiscoveryAgent().run(FakeProfile())


class TestVisibilityScoringAgent:
    def test_combines_llm_visibility_with_real_seo_metrics(self, app):
        visibility = json.dumps({"domain_visible": False, "visibility_position": None, "reasoning": "x"})
        with app.app_context(), patch(
            "app.services.llm_client.AnthropicClient.complete",
            lambda self, system, user, max_tokens=2048: _fake_response(visibility),
        ):
            result, usage = VisibilityScoringAgent().run(FakeProfile(), "best seo tool")

        assert result["domain_visible"] is False
        assert isinstance(result["estimated_search_volume"], int)
        assert 0 <= result["competitive_difficulty"] <= 100
        assert 0.0 <= result["opportunity_score"] <= 1.0

    def test_same_query_gives_deterministic_mock_data(self, app):
        """DATA_MODE=mock must be stable across calls for the same query text
        -- otherwise tests (and reviewers re-running the app) get flaky scores."""
        visibility = json.dumps({"domain_visible": True, "visibility_position": 1, "reasoning": "x"})
        with app.app_context(), patch(
            "app.services.llm_client.AnthropicClient.complete",
            lambda self, system, user, max_tokens=2048: _fake_response(visibility),
        ):
            r1, _ = VisibilityScoringAgent().run(FakeProfile(), "best seo tool")
            r2, _ = VisibilityScoringAgent().run(FakeProfile(), "best seo tool")
        assert r1["estimated_search_volume"] == r2["estimated_search_volume"]
        assert r1["competitive_difficulty"] == r2["competitive_difficulty"]


class TestContentRecommendationAgent:
    def test_happy_path_returns_3_to_5_recommendations(self, app):
        recs = json.dumps({"recommendations": [
            {
                "query_text": "best seo tool", "content_type": "blog_post", "title": "t",
                "rationale": "r", "target_keywords": ["a", "b"], "priority": "high",
            }
            for _ in range(4)
        ]})
        with app.app_context(), patch(
            "app.services.llm_client.AnthropicClient.complete",
            lambda self, system, user, max_tokens=2048: _fake_response(recs),
        ):
            gap_queries = [{"query_text": "best seo tool", "opportunity_score": 0.8,
                             "estimated_search_volume": 100, "competitive_difficulty": 40}]
            result, usage = ContentRecommendationAgent().run(FakeProfile(), gap_queries)
        assert 3 <= len(result) <= 5

    def test_too_few_recommendations_fails_schema_validation(self, app):
        recs = json.dumps({"recommendations": [
            {"query_text": "x", "content_type": "blog_post", "title": "t", "rationale": "r",
             "target_keywords": ["a"], "priority": "high"}
        ]})  # only 1, schema requires >= 3
        with app.app_context(), patch(
            "app.services.llm_client.AnthropicClient.complete",
            lambda self, system, user, max_tokens=2048: _fake_response(recs),
        ):
            with pytest.raises(AgentError):
                ContentRecommendationAgent().run(FakeProfile(), [
                    {"query_text": "x", "opportunity_score": 0.5, "estimated_search_volume": 10, "competitive_difficulty": 50}
                ])
