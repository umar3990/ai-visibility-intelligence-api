from flask import Blueprint, current_app, jsonify, request

from app.api.errors import APIError, NotFoundError
from app.extensions import db, limiter
from app.models import BusinessProfile, DiscoveredQuery, ContentRecommendation, PipelineRun
from app.services.pipeline import PipelineOrchestrator
from app.agents.scoring import VisibilityScoringAgent
from app.utils.scoring import compute_opportunity_score

bp = Blueprint("pipeline", __name__, url_prefix="/api/v1")


def _get_profile_or_404(profile_uuid: str) -> BusinessProfile:
    profile = db.session.get(BusinessProfile, profile_uuid)
    if profile is None:
        raise NotFoundError(f"No profile with uuid {profile_uuid}")
    return profile


@bp.post("/profiles/<profile_uuid>/run")
@limiter.limit(lambda: current_app.config["RUN_RATELIMIT"])
def run_pipeline(profile_uuid):
    profile = _get_profile_or_404(profile_uuid)

    orchestrator = PipelineOrchestrator()
    try:
        run = orchestrator.run(profile)
    except Exception as e:
        # Anything not already caught as an AgentError (e.g. missing API key)
        # -- surface as a clean 502 rather than a bare 500 stack trace, since
        # this is very likely a config problem (missing .env key), not a bug.
        raise APIError(f"Pipeline run failed to start: {e}", status_code=502, code="PIPELINE_ERROR")

    top_queries = (
        DiscoveredQuery.query.filter_by(run_uuid=run.uuid)
        .order_by(DiscoveredQuery.opportunity_score.desc())
        .limit(3)
        .all()
    )
    recommendations = ContentRecommendation.query.filter(
        ContentRecommendation.query_uuid.in_([q.uuid for q in DiscoveredQuery.query.filter_by(run_uuid=run.uuid)])
    ).all()

    return jsonify({
        "run_uuid": run.uuid,
        "status": run.status,
        "queries_discovered": run.queries_discovered,
        "queries_scored": run.queries_scored,
        "top_opportunity_queries": [q.to_dict() for q in top_queries],
        "content_recommendations": [r.to_dict() for r in recommendations],
        "tokens_used": run.tokens_used,
        "error_message": run.error_message,
    }), 201 if run.status == "completed" else 502


@bp.get("/profiles/<profile_uuid>/queries")
def list_queries(profile_uuid):
    _get_profile_or_404(profile_uuid)

    q = DiscoveredQuery.query.filter_by(profile_uuid=profile_uuid)

    min_score = request.args.get("min_score", type=float)
    if min_score is not None:
        q = q.filter(DiscoveredQuery.opportunity_score >= min_score)

    status = request.args.get("status")
    if status == "visible":
        q = q.filter(DiscoveredQuery.domain_visible.is_(True))
    elif status == "not_visible":
        q = q.filter(DiscoveredQuery.domain_visible.is_(False))
    elif status == "unknown":
        q = q.filter(DiscoveredQuery.domain_visible.is_(None))

    page = request.args.get("page", default=1, type=int)
    per_page = request.args.get("per_page", default=20, type=int)
    per_page = max(1, min(per_page, 100))

    q = q.order_by(DiscoveredQuery.opportunity_score.desc())
    pagination = q.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "queries": [item.to_dict() for item in pagination.items],
        "page": page,
        "per_page": per_page,
        "total": pagination.total,
    }), 200


@bp.get("/profiles/<profile_uuid>/recommendations")
def list_recommendations(profile_uuid):
    _get_profile_or_404(profile_uuid)
    recs = ContentRecommendation.query.filter_by(profile_uuid=profile_uuid).all()
    return jsonify({"recommendations": [r.to_dict() for r in recs]}), 200


@bp.post("/queries/<query_uuid>/recheck")
def recheck_query(query_uuid):
    query = db.session.get(DiscoveredQuery, query_uuid)
    if query is None:
        raise NotFoundError(f"No query with uuid {query_uuid}")
    profile = _get_profile_or_404(query.profile_uuid)

    agent = VisibilityScoringAgent()
    try:
        result, usage = agent.run(profile, query.query_text)
    except Exception as e:
        raise APIError(f"Recheck failed: {e}", status_code=502, code="PIPELINE_ERROR")

    query.estimated_search_volume = result["estimated_search_volume"]
    query.competitive_difficulty = result["competitive_difficulty"]
    query.domain_visible = result["domain_visible"]
    query.visibility_position = result["visibility_position"]
    query.opportunity_score = compute_opportunity_score(
        query_text=query.query_text,
        estimated_search_volume=result["estimated_search_volume"],
        competitive_difficulty=result["competitive_difficulty"],
        domain_visible=result["domain_visible"],
    )
    db.session.commit()

    return jsonify(query.to_dict()), 200
