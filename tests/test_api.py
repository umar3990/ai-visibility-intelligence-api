"""API-level tests: request/response shape, status codes, error envelope,
and the orchestrator wired through the real HTTP layer (with the LLM
mocked -- these are not agent unit tests, they're integration tests for
the endpoints themselves)."""
import json
from unittest.mock import patch

from app.services.llm_client import LLMResponse


def _fake_llm(discovery_json, visibility_json, recs_json="{\"recommendations\": []}"):
    def _complete(self, system, user, max_tokens=2048):
        if "search-intent research analyst" in system:
            return LLMResponse(text=discovery_json, input_tokens=1, output_tokens=1, provider="anthropic", model="m")
        if "simulating how an AI assistant" in system:
            return LLMResponse(text=visibility_json, input_tokens=1, output_tokens=1, provider="anthropic", model="m")
        return LLMResponse(text=recs_json, input_tokens=1, output_tokens=1, provider="anthropic", model="m")
    return _complete


def _create_profile(client, **overrides):
    payload = {"name": "Frase", "domain": "frase.io", "industry": "SEO", "competitors": []}
    payload.update(overrides)
    return client.post("/api/v1/profiles", json=payload)


class TestProfileEndpoints:
    def test_create_profile_returns_201_with_uuid(self, client):
        r = _create_profile(client)
        assert r.status_code == 201
        body = r.get_json()
        assert "profile_uuid" in body
        assert body["status"] == "created"

    def test_create_profile_missing_fields_returns_422_with_error_envelope(self, client):
        r = client.post("/api/v1/profiles", json={"name": "Only Name"})
        assert r.status_code == 422
        body = r.get_json()
        assert body["error"]["code"] == "VALIDATION_ERROR"

    def test_get_profile_includes_summary_stats(self, client):
        r = _create_profile(client)
        profile_uuid = r.get_json()["profile_uuid"]
        r2 = client.get(f"/api/v1/profiles/{profile_uuid}")
        assert r2.status_code == 200
        assert "stats" in r2.get_json()

    def test_get_nonexistent_profile_returns_404_with_error_envelope(self, client):
        r = client.get("/api/v1/profiles/does-not-exist")
        assert r.status_code == 404
        assert r.get_json()["error"]["code"] == "NOT_FOUND"


class TestPipelineEndpoint:
    def test_run_pipeline_end_to_end_with_mocked_llm(self, client):
        r = _create_profile(client)
        profile_uuid = r.get_json()["profile_uuid"]

        discovery = json.dumps({"queries": [f"Q{i} about seo tools?" for i in range(10)]})
        visibility = json.dumps({"domain_visible": False, "visibility_position": None, "reasoning": "x"})

        with patch("app.services.llm_client.AnthropicClient.complete", _fake_llm(discovery, visibility)):
            r2 = client.post(f"/api/v1/profiles/{profile_uuid}/run")

        assert r2.status_code == 201
        body = r2.get_json()
        assert body["status"] == "completed"
        assert body["queries_discovered"] == 10
        assert body["queries_scored"] == 10
        assert len(body["top_opportunity_queries"]) <= 3
        assert body["tokens_used"] > 0

    def test_run_pipeline_on_nonexistent_profile_returns_404(self, client):
        r = client.post("/api/v1/profiles/does-not-exist/run")
        assert r.status_code == 404


class TestQueriesEndpoint:
    def _run_pipeline(self, client, profile_uuid):
        discovery = json.dumps({"queries": [f"Q{i} about seo?" for i in range(10)]})
        visibility = json.dumps({"domain_visible": False, "visibility_position": None, "reasoning": "x"})
        with patch("app.services.llm_client.AnthropicClient.complete", _fake_llm(discovery, visibility)):
            client.post(f"/api/v1/profiles/{profile_uuid}/run")

    def test_pagination_respects_per_page(self, client):
        r = _create_profile(client)
        profile_uuid = r.get_json()["profile_uuid"]
        self._run_pipeline(client, profile_uuid)

        r2 = client.get(f"/api/v1/profiles/{profile_uuid}/queries?page=1&per_page=4")
        body = r2.get_json()
        assert len(body["queries"]) == 4
        assert body["total"] == 10

    def test_queries_sorted_by_opportunity_score_descending(self, client):
        r = _create_profile(client)
        profile_uuid = r.get_json()["profile_uuid"]
        self._run_pipeline(client, profile_uuid)

        r2 = client.get(f"/api/v1/profiles/{profile_uuid}/queries")
        scores = [q["opportunity_score"] for q in r2.get_json()["queries"]]
        assert len(scores) == 10  # guard against an empty list trivially "passing"
        assert scores == sorted(scores, reverse=True)

    def test_min_score_filter(self, client):
        r = _create_profile(client)
        profile_uuid = r.get_json()["profile_uuid"]
        self._run_pipeline(client, profile_uuid)

        # With the deterministic mock data these 10 queries score ~0.70-0.85,
        # so a 0.8 threshold returns a real subset (some rows, but not all) --
        # this proves the filter actually filters, rather than an empty list
        # vacuously satisfying the >= bound.
        r2 = client.get(f"/api/v1/profiles/{profile_uuid}/queries?min_score=0.8")
        returned = r2.get_json()["queries"]
        assert 0 < len(returned) < 10
        for q in returned:
            assert q["opportunity_score"] >= 0.8


class TestRateLimiting:
    def test_run_endpoint_returns_429_after_limit(self):
        # RateLimitTestConfig caps the run endpoint at "2 per minute", so the
        # 3rd trigger must be rejected with the consistent error envelope --
        # proving the limiter is wired to the pipeline endpoint specifically.
        from app import create_app
        from app.config import RateLimitTestConfig
        from app.extensions import db as _db

        app = create_app(RateLimitTestConfig)
        with app.app_context():
            _db.create_all()
            client = app.test_client()
            uid = _create_profile(client).get_json()["profile_uuid"]

            discovery = json.dumps({"queries": [f"Q{i} about seo?" for i in range(10)]})
            visibility = json.dumps({"domain_visible": False, "visibility_position": None, "reasoning": "x"})
            with patch("app.services.llm_client.AnthropicClient.complete", _fake_llm(discovery, visibility)):
                codes = [client.post(f"/api/v1/profiles/{uid}/run").status_code for _ in range(3)]

            assert codes[0] == 201
            assert codes[1] == 201
            assert codes[2] == 429
            # the limited response still comes back 429 without the pipeline running;
            # confirm one more time via a fresh call that the envelope is consistent
            blocked = client.post(f"/api/v1/profiles/{uid}/run")
            assert blocked.get_json()["error"]["code"] == "RATE_LIMITED"

            _db.session.remove()
            _db.drop_all()
