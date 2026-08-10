import pytest
from app import create_app
from app.config import TestConfig
from app.extensions import db as _db


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db(app):
    return _db


class FakeProfile:
    """Lightweight stand-in for a BusinessProfile ORM object, for agent unit
    tests that don't need a real DB row."""
    def __init__(self, name="Frase", domain="frase.io", industry="SEO Content Tools",
                 description="AI-powered content briefs", competitors=None):
        self.name = name
        self.domain = domain
        self.industry = industry
        self.description = description
        self.competitors = competitors or ["surferseo.com", "clearscope.io"]
