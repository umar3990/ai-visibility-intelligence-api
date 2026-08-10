"""Opportunity score formula.

opportunity_score (0.0-1.0) estimates how valuable it would be for the
target domain to appear in the AI answer for a given query. Four weighted
factors, each normalized to 0-1 before weighting so the weights are directly
interpretable as "percent of the score this factor controls":

  volume_score      (0.35) -- log-scaled search volume. Raw volume is
                               heavy-tailed (10 to 50,000+), so a linear
                               scale would let one viral query dominate the
                               ranking. Log scaling keeps a 10k-volume query
                               from being treated as "infinitely" better
                               than a 1k-volume one.

  difficulty_score   (0.25) -- inverted competitive_difficulty (0-100 -> 1-0).
                               Lower difficulty = easier to actually capture
                               the opportunity, so it should raise the score.

  visibility_gap     (0.30) -- the core "gap" signal. Not appearing at all
                               is the whole reason this platform exists, so
                               it gets the second-highest weight after
                               volume: not_visible=1.0, unknown=0.5,
                               visible=0.15 (a visible domain still has
                               upside from improving position, just much
                               less than a domain that's invisible).

  intent_score       (0.10) -- commercial/comparison intent ("best", "vs",
                               "compare", "alternative", "top") scores 1.0,
                               informational queries score 0.4. Given lowest
                               weight because it's a coarse keyword heuristic,
                               not a real intent classifier -- it should
                               nudge the ranking, not dominate it.

Weights sum to 1.0, so the output is naturally bounded to [0, 1] as long as
each component is bounded to [0, 1], which is enforced below.

This is a documented starting point, not a claim of the single correct
formula -- the brief is explicit that there isn't one.
"""
import math
import re

_VOLUME_CAP = 10_000  # volume above this is treated as equally "high opportunity"
_COMMERCIAL_PATTERN = re.compile(
    r"\b(best|vs\.?|versus|compare|comparison|alternative|top \d+|review|pricing|cost)\b",
    re.IGNORECASE,
)

WEIGHT_VOLUME = 0.35
WEIGHT_DIFFICULTY = 0.25
WEIGHT_VISIBILITY_GAP = 0.30
WEIGHT_INTENT = 0.10


def _volume_score(volume: int | None) -> float:
    if not volume or volume <= 0:
        return 0.0
    return min(1.0, math.log10(volume + 1) / math.log10(_VOLUME_CAP + 1))


def _difficulty_score(difficulty: int | None) -> float:
    if difficulty is None:
        return 0.5  # unknown difficulty -- neutral, don't punish or reward
    difficulty = max(0, min(100, difficulty))
    return (100 - difficulty) / 100


def _visibility_gap_score(domain_visible: bool | None) -> float:
    if domain_visible is None:
        return 0.5
    return 0.15 if domain_visible else 1.0


def _intent_score(query_text: str) -> float:
    return 1.0 if _COMMERCIAL_PATTERN.search(query_text or "") else 0.4


def compute_opportunity_score(
    query_text: str,
    estimated_search_volume: int | None,
    competitive_difficulty: int | None,
    domain_visible: bool | None,
) -> float:
    score = (
        WEIGHT_VOLUME * _volume_score(estimated_search_volume)
        + WEIGHT_DIFFICULTY * _difficulty_score(competitive_difficulty)
        + WEIGHT_VISIBILITY_GAP * _visibility_gap_score(domain_visible)
        + WEIGHT_INTENT * _intent_score(query_text)
    )
    return round(max(0.0, min(1.0, score)), 4)
