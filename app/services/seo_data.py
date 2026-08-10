"""Real search-volume + competition data via DataForSEO.

The assessment requires real third-party data for search volume and
competitive difficulty (not the visibility check itself -- the brief
explicitly says Agent 2 should *simulate* checking visibility, which is
implemented as a live LLM call in agents/scoring.py, not this module).

DataForSEO's Keywords Data (Google Ads) endpoint gives real search_volume
and competition; their Labs "Bulk Keyword Difficulty" endpoint gives a
0-100 difficulty score matching the spec's range directly, so no rescaling
is needed downstream in the scoring formula.

DATA_MODE=mock (default when no credentials are configured) returns
deterministic, clearly-flagged placeholder numbers so the app is fully
runnable end-to-end for review without anyone needing a paid account.
Real numbers require DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD in .env and
DATA_MODE=live.
"""
from __future__ import annotations

import hashlib
import requests
from flask import current_app

_BASE_URL = "https://api.dataforseo.com/v3"


class SEODataError(Exception):
    pass


def _mock_volume_and_difficulty(query_text: str) -> tuple[int, int]:
    """Deterministic pseudo-random numbers derived from the query text, so
    repeated calls for the same query are stable (useful for tests) without
    needing a real API call.
    """
    h = int(hashlib.sha256(query_text.encode()).hexdigest(), 16)
    volume = 50 + (h % 4950)          # 50 - 5000
    difficulty = 10 + ((h >> 16) % 81)  # 10 - 90
    return volume, difficulty


def get_search_metrics(query_text: str) -> dict:
    """Returns {"search_volume": int, "difficulty": int, "data_source": "live"|"mock"}."""
    cfg = current_app.config
    if cfg.get("DATA_MODE") != "live" or not cfg.get("DATAFORSEO_LOGIN"):
        volume, difficulty = _mock_volume_and_difficulty(query_text)
        return {"search_volume": volume, "difficulty": difficulty, "data_source": "mock"}

    auth = (cfg["DATAFORSEO_LOGIN"], cfg["DATAFORSEO_PASSWORD"])
    try:
        vol_resp = requests.post(
            f"{_BASE_URL}/keywords_data/google_ads/search_volume/live",
            auth=auth,
            json=[{"keywords": [query_text], "language_code": "en", "location_code": 2840}],
            timeout=15,
        )
        vol_resp.raise_for_status()
        vol_data = vol_resp.json()
        result = vol_data["tasks"][0]["result"][0]
        volume = result.get("search_volume") or 0

        diff_resp = requests.post(
            f"{_BASE_URL}/dataforseo_labs/google/bulk_keyword_difficulty/live",
            auth=auth,
            json=[{"keywords": [query_text], "language_code": "en", "location_code": 2840}],
            timeout=15,
        )
        diff_resp.raise_for_status()
        diff_data = diff_resp.json()
        diff_items = diff_data["tasks"][0]["result"][0]["items"]
        difficulty = diff_items[0].get("keyword_difficulty", 50) if diff_items else 50

        return {"search_volume": volume, "difficulty": difficulty, "data_source": "live"}
    except (requests.RequestException, KeyError, IndexError) as e:
        current_app.logger.warning(f"DataForSEO call failed, falling back to mock: {e}")
        volume, difficulty = _mock_volume_and_difficulty(query_text)
        return {"search_volume": volume, "difficulty": difficulty, "data_source": "mock_fallback"}
