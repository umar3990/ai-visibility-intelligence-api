import uuid
from datetime import datetime, timezone

from app.extensions import db


def gen_uuid() -> str:
    return str(uuid.uuid4())


class UUIDPKMixin:
    """String(36) UUID primary key -- portable across SQLite (dev) and
    Postgres (prod) without needing the Postgres-only UUID column type.
    """
    uuid = db.Column(db.String(36), primary_key=True, default=gen_uuid)


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
