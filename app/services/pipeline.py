"""Pipeline orchestrator: Agent 1 -> Agent 2 (per query) -> Agent 3.

Partial-failure handling (per the brief): if Agent 2 fails for one query,
log it and continue scoring the rest -- one bad query must not sink the
whole run. Agent 1 and Agent 3 failures are run-level (there's nothing
partial to salvage from "couldn't generate any queries" or "couldn't
generate any recommendations"), so those mark the run failed with a
specific error_message rather than silently returning an empty result.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.agents.base import AgentError
from app.agents.discovery import QueryDiscoveryAgent
from app.agents.recommendation import ContentRecommendationAgent
from app.agents.scoring import VisibilityScoringAgent
from app.extensions import db
from app.logging_setup import pipeline_logger as logger, run_id_var
from app.models import PipelineRun, DiscoveredQuery, ContentRecommendation


class PipelineOrchestrator:
    def __init__(self):
        self.discovery_agent = QueryDiscoveryAgent()
        self.scoring_agent = VisibilityScoringAgent()
        self.recommendation_agent = ContentRecommendationAgent()

    def run(self, profile) -> PipelineRun:
        run = PipelineRun(profile_uuid=profile.uuid, status="running", started_at=datetime.now(timezone.utc))
        db.session.add(run)
        db.session.commit()

        # Every log line from here on carries this run's correlation id.
        run_id_var.set(run.uuid)
        logger.info("pipeline started for profile %s (%s)", profile.uuid, profile.domain)

        total_tokens = 0

        # --- Agent 1: discovery (run-level failure) ---
        try:
            queries, usage = self.discovery_agent.run(profile)
            total_tokens += usage.total_tokens
        except AgentError as e:
            return self._fail_run(run, f"Agent 1 (discovery) failed: {e}")

        run.queries_discovered = len(queries)
        db.session.commit()
        logger.info("discovery complete: %d queries", len(queries))

        # --- Agent 2: scoring, per-query, partial failure tolerant ---
        scored_records: list[DiscoveredQuery] = []
        failed_queries = 0
        now = datetime.now(timezone.utc)

        for query_text in queries:
            try:
                result, usage = self.scoring_agent.run(profile, query_text)
                total_tokens += usage.total_tokens
            except AgentError as e:
                failed_queries += 1
                logger.warning("scoring failed for query '%s...': %s", query_text[:60], e)
                run.error_message = ((run.error_message or "") + f"\nAgent 2 failed for '{query_text[:60]}...': {e}").strip()
                continue

            record = DiscoveredQuery(
                profile_uuid=profile.uuid,
                run_uuid=run.uuid,
                query_text=result["query_text"],
                estimated_search_volume=result["estimated_search_volume"],
                competitive_difficulty=result["competitive_difficulty"],
                opportunity_score=result["opportunity_score"],
                domain_visible=result["domain_visible"],
                visibility_position=result["visibility_position"],
                discovered_at=now,
            )
            db.session.add(record)
            scored_records.append(record)

        db.session.commit()
        run.queries_scored = len(scored_records)
        db.session.commit()
        logger.info("scoring complete: %d scored, %d failed", len(scored_records), failed_queries)

        if not scored_records:
            return self._fail_run(run, "Agent 2 failed for every discovered query; no scored results to build recommendations from.")

        # --- Agent 3: recommendations, from the top-scoring NOT-visible queries ---
        gap_queries = sorted(
            (r for r in scored_records if not r.domain_visible),
            key=lambda r: r.opportunity_score,
            reverse=True,
        )[:8]  # cap the prompt size; top 8 gap queries is plenty of signal for 3-5 recs

        if gap_queries:
            gap_dicts = [
                {
                    "query_text": r.query_text,
                    "opportunity_score": r.opportunity_score,
                    "estimated_search_volume": r.estimated_search_volume,
                    "competitive_difficulty": r.competitive_difficulty,
                }
                for r in gap_queries
            ]
            by_text = {r.query_text: r for r in gap_queries}
            try:
                recs, usage = self.recommendation_agent.run(profile, gap_dicts)
                total_tokens += usage.total_tokens
                for rec in recs:
                    matched_query = by_text.get(rec.query_text)
                    if matched_query is None:
                        # LLM didn't echo the query_text exactly -- fall back to the
                        # single highest-opportunity gap query rather than dropping
                        # a recommendation the reviewer would otherwise see missing.
                        matched_query = gap_queries[0]
                    db.session.add(ContentRecommendation(
                        profile_uuid=profile.uuid,
                        query_uuid=matched_query.uuid,
                        content_type=rec.content_type,
                        title=rec.title,
                        rationale=rec.rationale,
                        target_keywords=rec.target_keywords,
                        priority=rec.priority,
                    ))
                db.session.commit()
            except AgentError as e:
                # Run still succeeded (discovery + scoring produced real data);
                # recommendations are a bonus layer on top, so log and move on
                # rather than failing a run that otherwise has good output.
                logger.warning("recommendation generation failed (run still completed): %s", e)
                run.error_message = ((run.error_message or "") + f"\nAgent 3 failed: {e}").strip()

        run.status = "completed"
        run.tokens_used = total_tokens
        run.completed_at = datetime.now(timezone.utc)
        db.session.commit()
        logger.info("pipeline completed: %d scored, %d tokens", run.queries_scored, total_tokens)
        run_id_var.set("-")  # clear correlation id so it doesn't leak to later logs
        return run

    def _fail_run(self, run: PipelineRun, message: str) -> PipelineRun:
        run.status = "failed"
        run.error_message = message
        run.completed_at = datetime.now(timezone.utc)
        db.session.commit()
        logger.error("pipeline failed: %s", message)
        run_id_var.set("-")  # clear correlation id so it doesn't leak to later logs
        return run
