from app.extensions import db
from app.models.mixins import UUIDPKMixin, TimestampMixin


class ContentRecommendation(UUIDPKMixin, TimestampMixin, db.Model):
    __tablename__ = "content_recommendations"

    profile_uuid = db.Column(db.String(36), db.ForeignKey("business_profiles.uuid"), nullable=False, index=True)
    query_uuid = db.Column(db.String(36), db.ForeignKey("discovered_queries.uuid"), nullable=False, index=True)

    content_type = db.Column(db.String(64), nullable=False)  # blog_post|landing_page|faq
    title = db.Column(db.String(500), nullable=False)
    rationale = db.Column(db.Text, nullable=False)
    target_keywords = db.Column(db.JSON, nullable=False, default=list)
    priority = db.Column(db.String(16), nullable=False, default="medium")  # high|medium|low

    def to_dict(self) -> dict:
        return {
            "recommendation_uuid": self.uuid,
            "target_query_uuid": self.query_uuid,
            "content_type": self.content_type,
            "title": self.title,
            "rationale": self.rationale,
            "target_keywords": self.target_keywords,
            "priority": self.priority,
        }
