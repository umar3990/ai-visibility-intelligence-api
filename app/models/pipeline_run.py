from app.extensions import db
from app.models.mixins import UUIDPKMixin, TimestampMixin


class PipelineRun(UUIDPKMixin, TimestampMixin, db.Model):
    __tablename__ = "pipeline_runs"

    profile_uuid = db.Column(db.String(36), db.ForeignKey("business_profiles.uuid"), nullable=False, index=True)
    status = db.Column(db.String(32), nullable=False, default="running")  # running|completed|failed
    queries_discovered = db.Column(db.Integer, nullable=False, default=0)
    queries_scored = db.Column(db.Integer, nullable=False, default=0)
    tokens_used = db.Column(db.Integer, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "run_uuid": self.uuid,
            "profile_uuid": self.profile_uuid,
            "status": self.status,
            "queries_discovered": self.queries_discovered,
            "queries_scored": self.queries_scored,
            "tokens_used": self.tokens_used,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
