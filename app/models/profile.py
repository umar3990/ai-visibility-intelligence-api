from app.extensions import db
from app.models.mixins import UUIDPKMixin, TimestampMixin


class BusinessProfile(UUIDPKMixin, TimestampMixin, db.Model):
    __tablename__ = "business_profiles"

    name = db.Column(db.String(255), nullable=False)
    domain = db.Column(db.String(255), nullable=False, index=True)
    industry = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    # JSON list of competitor domains, e.g. ["clearscope.io", "frase.io"]
    competitors = db.Column(db.JSON, nullable=False, default=list)
    status = db.Column(db.String(32), nullable=False, default="created")

    pipeline_runs = db.relationship(
        "PipelineRun", backref="profile", lazy="dynamic", cascade="all, delete-orphan"
    )
    queries = db.relationship(
        "DiscoveredQuery", backref="profile", lazy="dynamic", cascade="all, delete-orphan"
    )
    recommendations = db.relationship(
        "ContentRecommendation", backref="profile", lazy="dynamic", cascade="all, delete-orphan"
    )

    def summary_stats(self) -> dict:
        total = self.queries.count()
        if total == 0:
            avg_score = 0.0
        else:
            scores = [q.opportunity_score for q in self.queries if q.opportunity_score is not None]
            avg_score = round(sum(scores) / len(scores), 4) if scores else 0.0
        return {"total_queries_discovered": total, "avg_opportunity_score": avg_score}

    def to_dict(self, with_stats: bool = False) -> dict:
        data = {
            "profile_uuid": self.uuid,
            "name": self.name,
            "domain": self.domain,
            "industry": self.industry,
            "description": self.description,
            "competitors": self.competitors,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
        if with_stats:
            data["stats"] = self.summary_stats()
        return data
