"""Tests for the DataForSEO integration (app/services/seo_data.py).

The assessment requires real third-party data for search volume + difficulty.
These tests exercise the live code path against DataForSEO's *documented*
response shape (HTTP mocked, so no paid account is needed to verify the
parsing is correct), plus the mock default and the fail-closed fallback.
"""
from unittest.mock import patch

import pytest
import requests

from app.services import seo_data


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


# DataForSEO's documented response envelopes for the two endpoints used.
_VOLUME_PAYLOAD = {"tasks": [{"result": [{"search_volume": 1200}]}]}
_DIFFICULTY_PAYLOAD = {"tasks": [{"result": [{"items": [{"keyword_difficulty": 62}]}]}]}


def _live(app):
    app.config["DATA_MODE"] = "live"
    app.config["DATAFORSEO_LOGIN"] = "login"
    app.config["DATAFORSEO_PASSWORD"] = "password"


def test_mock_mode_is_default_and_deterministic(app):
    with app.app_context():
        a = seo_data.get_search_metrics("best seo tool")
        b = seo_data.get_search_metrics("best seo tool")
        assert a["data_source"] == "mock"
        assert a == b  # deterministic for the same query


def test_live_path_parses_documented_response_shape(app):
    _live(app)
    with app.app_context(), patch.object(
        seo_data.requests, "post",
        side_effect=[_FakeResp(_VOLUME_PAYLOAD), _FakeResp(_DIFFICULTY_PAYLOAD)],
    ):
        result = seo_data.get_search_metrics("frase vs surfer seo")
    assert result["search_volume"] == 1200
    assert result["difficulty"] == 62
    assert result["data_source"] == "live"


def test_live_path_fails_closed_to_mock_on_api_error(app):
    _live(app)
    with app.app_context(), patch.object(
        seo_data.requests, "post",
        side_effect=requests.RequestException("boom"),
    ):
        result = seo_data.get_search_metrics("frase vs surfer seo")
    # must not raise -- a DataForSEO outage can't sink a pipeline run
    assert result["data_source"] == "mock_fallback"
    assert result["search_volume"] > 0
