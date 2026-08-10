"""Structured (JSON) logging with a per-pipeline-run correlation ID.

Every log line emitted during a pipeline run carries the same `run_id`, so a
reviewer (or an on-call engineer) can grep one run's full story out of
interleaved concurrent output. The correlation id is stored in a ContextVar,
set once by the orchestrator, so call sites don't have to thread it through
every function -- any logger.* call inside the run picks it up automatically.
"""
from __future__ import annotations

import json
import logging
from contextvars import ContextVar

# Default "-" means "no active pipeline run" (e.g. plain request logs).
run_id_var: ContextVar[str] = ContextVar("run_id", default="-")

# Module logger the orchestrator uses; configured in configure_logging().
pipeline_logger = logging.getLogger("app.pipeline")


class CorrelationIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = run_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "run_id": getattr(record, "run_id", "-"),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(app) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(CorrelationIdFilter())

    for logger in (app.logger, pipeline_logger):
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False  # don't double-log via the root logger
