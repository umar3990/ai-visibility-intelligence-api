"""Application configuration.

Config is loaded from environment variables (via python-dotenv in create_app).
Kept as plain classes rather than a settings library since the surface area
here is small -- Pydantic settings would be overkill for ~8 values.
"""
import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///dev.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic")
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
    ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")

    DATAFORSEO_LOGIN = os.environ.get("DATAFORSEO_LOGIN")
    DATAFORSEO_PASSWORD = os.environ.get("DATAFORSEO_PASSWORD")
    # live: hit the real DataForSEO API. mock: deterministic local data, clearly
    # flagged, so the app is reviewable without anyone having to pay for a plan.
    DATA_MODE = os.environ.get("DATA_MODE", "live")

    # Rate limiting on the expensive pipeline-trigger endpoint. In-memory storage
    # by default (single-process); point RATELIMIT_STORAGE_URI at redis:// for prod.
    RUN_RATELIMIT = os.environ.get("RUN_RATELIMIT", "10 per minute")
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    DATA_MODE = "mock"
    # Dummy keys so the suite runs on a cold clone: the LLM is always mocked in
    # tests, but get_llm_client() still constructs a client and would otherwise
    # raise "API key not set" before the mock is reached. No network calls made.
    ANTHROPIC_API_KEY = "test-anthropic-key"
    OPENAI_API_KEY = "test-openai-key"
    # Off by default so the functional tests aren't affected by request counts;
    # a dedicated test flips it on via RateLimitTestConfig below.
    RATELIMIT_ENABLED = False


class RateLimitTestConfig(TestConfig):
    RATELIMIT_ENABLED = True
    RUN_RATELIMIT = "2 per minute"
