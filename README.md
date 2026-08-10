# AI Visibility Intelligence API

A simplified version of an AI-visibility pipeline: register a business profile, run a 3-agent
pipeline that discovers commercially-relevant questions, scores them for opportunity, and
generates content recommendations to close visibility gaps.

## Setup (target: under 5 minutes)

```bash
cp .env.example .env
# Fill in ANTHROPIC_API_KEY (or OPENAI_API_KEY + set LLM_PROVIDER=openai).
# DataForSEO credentials are optional -- without them the app runs in
# DATA_MODE=mock automatically, with every mock response clearly flagged
# via "data_source": "mock" in the API output.

docker-compose up
# API is live at http://localhost:5000, SQLite persisted in a named volume.
```

Without Docker:

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in at least one LLM key
flask db upgrade
python run.py           # http://localhost:5000
```

Run the test suite (26 tests, all using mocked LLM/HTTP responses -- no API key required):

```bash
pytest tests/ -v
```

## Architecture decisions

**App structure.** Standard Flask app-factory pattern (`create_app()`) with blueprints per
resource (`profiles`, `pipeline`). `app/extensions.py` holds bare `db`/`migrate` instances
to avoid the classic circular-import problem between the factory and the models.

**Agent separation.** Each agent (`app/agents/discovery.py`, `scoring.py`,
`recommendation.py`) is a standalone class with its own system prompt, user prompt template,
and Pydantic output schema. They share only a stateless `BaseAgent` helper
(`app/agents/base.py`) for the "call LLM, parse JSON, retry once on failure" logic -- no
shared mutable state between agents, so each is independently unit-testable (see
`tests/test_agents.py`), and a bug in one agent's prompt can't leak into another's.

**Orchestrator + partial failure.** `app/services/pipeline.py` runs Agent 1 → Agent 2 (per
query) → Agent 3. If Agent 2 fails for one query after its repair retry, that query is
skipped and logged to `PipelineRun.error_message`, and the loop continues -- one bad query
can't sink a run of otherwise-good results. Agent 1 failure is run-level (nothing to
salvage from zero queries), so it fails the run. Agent 3 failure is logged but does **not**
fail the run, since discovery + scoring already produced valid, useful output at that point
-- recommendations are a bonus layer on top. This behavior is directly exercised in
`tests/test_agents.py` and validated end-to-end during development (a query engineered to
always return malformed JSON gets skipped while the other 9 succeed, and the run still
reports `status: "completed"`).

**JSON validation & retry.** Every agent call goes through `BaseAgent.call_llm_json()`:
strip markdown fences defensively → `json.loads()` → validate against a Pydantic schema. On
either failure, one repair prompt is sent back to the model with the specific parse/validation
error and the original bad output, asking for a corrected JSON-only response. If that also
fails, an `AgentError` is raised (never an unhandled crash) for the caller to catch and
isolate.

**Data model.** UUID string primary keys (portable across SQLite dev and Postgres prod,
no native UUID column type dependency). `competitors` and `target_keywords` are stored as
JSON columns rather than a normalized join table -- they're read as whole lists, never
queried/filtered element-wise, so normalizing them would add migration complexity without
a real query benefit here.

**Error responses.** Every error returns the same envelope --
`{"error": {"code": "...", "message": "..."}}` -- via a shared `APIError` hierarchy and
Flask error handlers in `app/api/errors.py`, so clients can branch on `code` instead of
parsing message strings. Rate-limit rejections (429) use the same envelope with
`"code": "RATE_LIMITED"`.

**Structured logging with correlation IDs.** `app/logging_setup.py` configures JSON log
output and a `run_id` correlation id (a `ContextVar` set once by the orchestrator), so every
log line emitted during a pipeline run carries that run's id -- one `grep` reconstructs a
single run's full story out of interleaved output. Call sites just use `logger.*`; they don't
have to thread the id through.

**Rate limiting.** The expensive pipeline-trigger endpoint (`POST /profiles/{uuid}/run`) is
rate limited via Flask-Limiter (default `10 per minute`, configurable with `RUN_RATELIMIT`).
Other endpoints are unthrottled. Storage is in-memory by default; set `RATELIMIT_STORAGE_URI`
to a `redis://` URL for multi-process production.

## Agent design rationale

- **Agent 1 (Discovery)** generates 10-20 natural-language questions (schema-enforced via
  Pydantic `min_length=10, max_length=20`). Prompt explicitly bans keyword-fragment output
  ("best SEO tool") in favor of real chat-style questions, and requires a mix of comparison,
  best-of, and evaluative question types so Agent 2 has varied intent to score.
- **Agent 2 (Visibility Scoring)** splits real vs. simulated data on purpose: search volume
  and difficulty come from DataForSEO (real, external, verifiable), while `domain_visible` /
  `visibility_position` come from an actual live LLM call that answers the query the way a
  real user would and checks whether the target domain shows up -- this matches the brief's
  own wording ("simulate checking") as closely as a take-home can without scraping a
  production AI-search UI. The opportunity score itself is **not** LLM-generated; it's a
  deterministic function of these inputs (see below), so it's reproducible and auditable.
- **Agent 3 (Recommendations)** only ever sees the top 8 NOT-visible queries by opportunity
  score (capped to keep the prompt focused), and its prompt requires each recommendation's
  `query_text` to exactly echo one of the input queries so the orchestrator can map
  recommendations back to `DiscoveredQuery` rows without a second matching pass.

**Model selection:** Anthropic Claude is the default (`LLM_PROVIDER=anthropic`) because every
agent here depends on strict, prompt-defined JSON output rather than tool-calling, and Claude
is reliably good at following an in-prompt schema without extra wrapping. OpenAI's GPT-4o is
wired up as a same-interface alternative (`LLMClient` protocol in
`app/services/llm_client.py`) -- switching providers, or mixing providers per agent, is a
one-line change, not a rewrite.

## Opportunity score formula

```
opportunity_score = 0.35 * volume_score + 0.25 * difficulty_score
                   + 0.30 * visibility_gap_score + 0.10 * intent_score
```

- `volume_score` -- log10-scaled search volume (caps the influence of one viral outlier query)
- `difficulty_score` -- inverted `competitive_difficulty` (lower difficulty = more capturable)
- `visibility_gap_score` -- **the core signal**: 1.0 if the domain isn't visible at all, 0.5
  if unknown, 0.15 if already visible (still some upside from improving position)
- `intent_score` -- 1.0 for comparison/commercial-intent queries ("vs", "best", "compare",
  "alternative"), 0.4 for informational queries -- lowest weight because it's a keyword
  heuristic, not a real intent classifier, so it nudges rather than dominates the ranking

Full reasoning and normalization details are documented inline in `app/utils/scoring.py`.
Weights sum to 1.0 so the score is naturally bounded to `[0, 1]`. Verified in
`tests/test_scoring_formula.py` that scores are correctly ordered (an invisible domain always
outscores an otherwise-identical visible one; commercial intent always outscores informational).

## Tradeoffs (honest)

- **No async pipeline.** The brief says synchronous is fine for the core requirement, and
  given the assessment's own tight turnaround, I prioritized correctness and test coverage
  of the synchronous path over building Celery + a status-polling endpoint. The orchestrator
  is already structured so wrapping `PipelineOrchestrator.run()` in a background task would
  be a small follow-up, not a redesign.
- **DataForSEO live path is unit-tested but not run against a paid account** -- the live
  integration is implemented against DataForSEO's documented request/response shape and
  covered by tests that mock the HTTP layer with that exact shape (`tests/test_seo_data.py`),
  so the parsing is verified; it just hasn't been exercised against a real paid key (I can't
  create an account on the candidate's behalf). `DATA_MODE=mock` is the default so the app is
  reviewable cold, and the live path fails closed to mock data (with a logged warning) if the
  API errors, rather than crashing a pipeline run. Add `DATAFORSEO_LOGIN`/`DATAFORSEO_PASSWORD`
  and set `DATA_MODE=live` to use real search-volume/difficulty data.
- **No frontend** -- out of scope per the brief.
- **Competitors/keywords as JSON columns, not normalized tables** -- explained above; would
  revisit if the API needed to filter/query by individual competitor or keyword.

## AI tool disclosure

Built with Claude (Anthropic) as a coding assistant for scaffolding, boilerplate, and initial
test-writing, per the brief's explicit allowance. All architectural decisions above --
agent separation, the opportunity score formula and its weights, the partial-failure
strategy, and the real-vs-simulated data split in Agent 2 -- were specified and reviewed
before implementation, not accepted as default output.

## Project structure

```
app/
  __init__.py          # create_app() factory
  config.py            # Config / TestConfig
  extensions.py         # db, migrate, limiter
  logging_setup.py      # JSON logging + run_id correlation id
  models/               # BusinessProfile, PipelineRun, DiscoveredQuery, ContentRecommendation
  agents/                # base.py (shared JSON parse/retry) + one file per agent
  services/
    llm_client.py        # Anthropic/OpenAI abstraction
    seo_data.py            # DataForSEO integration (+ mock fallback)
    pipeline.py             # orchestrator
  api/
    profiles.py            # POST/GET profiles
    pipeline.py             # run (rate limited) / queries / recommendations / recheck
    errors.py               # consistent error envelope
  utils/scoring.py         # opportunity score formula
tests/                      # 26 tests: agents (mocked LLM), API, scoring, rate limiting, DataForSEO
migrations/                  # real Alembic migration, generated + applied
docker-compose.yml
Dockerfile
```
