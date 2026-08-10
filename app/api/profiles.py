from flask import Blueprint, jsonify, request

from app.api.errors import NotFoundError, ValidationAPIError
from app.extensions import db
from app.models import BusinessProfile

bp = Blueprint("profiles", __name__, url_prefix="/api/v1/profiles")

_REQUIRED_FIELDS = ["name", "domain", "industry"]


@bp.post("")
def create_profile():
    data = request.get_json(silent=True) or {}
    missing = [f for f in _REQUIRED_FIELDS if not data.get(f)]
    if missing:
        raise ValidationAPIError(f"Missing required fields: {', '.join(missing)}")

    profile = BusinessProfile(
        name=data["name"],
        domain=data["domain"],
        industry=data["industry"],
        description=data.get("description"),
        competitors=data.get("competitors", []),
        status="created",
    )
    db.session.add(profile)
    db.session.commit()
    return jsonify(profile.to_dict()), 201


@bp.get("/<profile_uuid>")
def get_profile(profile_uuid):
    profile = db.session.get(BusinessProfile, profile_uuid)
    if profile is None:
        raise NotFoundError(f"No profile with uuid {profile_uuid}")
    return jsonify(profile.to_dict(with_stats=True)), 200
