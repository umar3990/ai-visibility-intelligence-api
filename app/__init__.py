from flask import Flask
from dotenv import load_dotenv

from app.config import Config
from app.extensions import db, migrate, limiter
from app.api.errors import register_error_handlers
from app.logging_setup import configure_logging


def create_app(config_object: type = Config) -> Flask:
    load_dotenv()

    app = Flask(__name__)
    app.config.from_object(config_object)

    configure_logging(app)

    db.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)

    register_error_handlers(app)

    from app.api.profiles import bp as profiles_bp
    from app.api.pipeline import bp as pipeline_bp
    app.register_blueprint(profiles_bp)
    app.register_blueprint(pipeline_bp)

    from app import models  # noqa: F401  -- registers models with SQLAlchemy metadata

    @app.get("/health")
    def health():
        return {"status": "ok"}, 200

    return app
