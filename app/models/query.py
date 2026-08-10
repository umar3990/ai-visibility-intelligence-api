from app.extensions import db
from app.models.mixins import UUIDPKMixin, TimestampMixin


class DiscoveredQuery(UUIDPKMixin, TimestampMixin, db.Model):
    __tablename__ = "discovered_queries"

    profile_uuid = db.Column(db.String(36), db.ForeignKey("business_profiles.uuid"), nullable=False, index=True)
    run_uuid = db.Column(db.String(36), db.ForeignKey("pipeline_runs.uuid"), nullable=False, index=True)

    query_text = db.Column(db.Text, nullable=False)
    estimated_search_volume = db.Column(db.Integer, nullable=True)
    competitive_difficulty = db.Column(db.Integer, nullable=True)  # 0-100
    opportunity_score = db.Column(db.Float, nullable=True)  # 0.0-1.0
    domain_visible = db.Column(db.Boolean, nullable=True)
    visibility_position = db.Column(db.Integer, nullable=True)
    discovered_at = db.Column(db.DateTime, nullable=False)

    recommendations = db.relationship(
        "ContentRecommendation", backref="target_query", lazy="dynamic", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "query_uuid": self.uuid,
            "query_text": self.query_text,
            "estimated_search_volume": self.estimated_search_volume,
            "competitive_difficulty": self.competitive_difficulty,
            "opportunity_score": self.opportunity_score,
            "domain_visible": self.domain_visible,
            "visibility_position": self.visibility_position,
            "discovered_at": self.discovered_at.isoformat(),
        }
