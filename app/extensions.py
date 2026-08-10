"""Shared extension instances, created here (not in __init__) to avoid
circular imports between app/__init__.py and app/models/*.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy()
migrate = Migrate()
# Rate limiter keyed by client IP. Storage backend is configured via
# RATELIMIT_STORAGE_URI (defaults to in-memory -- fine for this assessment;
# swap to redis:// for multi-process production).
limiter = Limiter(key_func=get_remote_address)
