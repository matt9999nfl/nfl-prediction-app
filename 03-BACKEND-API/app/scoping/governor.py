"""
The governor — whether this experiment should run at all.

SOPs define the task; governance decides whether the task should run.  The
scoping tree (Stage 0/2) is the SOP layer: it asks what is needed to build a
valid config, and it has no opinion.  This module has the opinion.

Every check here is DETERMINISTIC. That is deliberate and it is what stops this
layer becoming wallpaper: a governor that depends on a model returning something
useful will, on the day it returns "looks good" to a bad experiment, have taught
the user to skip it. Sample size, duplication and cold-start are arithmetic, so
they are done as arithmetic. The model layer (claude_scoping.review_experiment)
sits on top and adds judgment the arithmetic cannot reach; it is optional and
its absence changes nothing here.

The governor ADVISES. It cannot block a run — see app/routers/scoping.py, where
dispatch does not consult it. A governor with a veto becomes a thing to route
around, and then the honest signal is lost along with the veto.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

VERDICT_PROCEED = "proceed"
VERDICT_CAUTION = "proceed_with_caution"
VERDICT_RECONSIDER = "reconsider"

# Games in a modern regular season: 32 teams x 17 games / 2.
GAMES_PER_SEASON = 272

# Above this hit rate against closing lines on the full game universe, the
# project's own SOP says treat it as a leakage suspect rather than a result.
IMPLAUSIBLE_ATS_THRESHOLD = 0.57


def _concern(severity: str, kind: str, message: str) -> dict[str, str]:
    return {"severity": severity, "kind": kind, "message": message}


def fold_test_seasons(methodology: dict[str, Any]) -> list[int]:
    """
    The seasons the walk-forward runner will actually evaluate, in order.

    THE ONE DEFINITION OF A FOLD.  This is the same algorithm as
    02-MODELING/backtests/walk_forward.py::build_folds_from_config, which is the
    reference: the first test season is `start_season + train_seasons`, every
    fold evaluates exactly ONE season, and `test_seasons` is the STRIDE between
    folds, not the number of seasons inside one.

    FINDING HC-S6-F3.  This module used to compute `folds = span - train_seasons`
    and multiply by `test_seasons`, which is a second, different definition of a
    fold living in the same codebase.  The two agreed only at `test_seasons=1`,
    the single value the old test asserted; at `test_seasons=2` the governor
    reported about 3.5x the games the runner would evaluate, so the sample-size
    check cleared designs it exists to stop.

    The duplication cannot be deleted outright — ADR-012 commitment 1 keeps
    app/scoping/ free of any import outside stdlib, pydantic and its own
    siblings, and the runner module pulls pandas, sklearn and xgboost.  So the
    algorithm is restated here and pinned to the runner's own source by
    tests/test_scoping_folds.py, which fails if the two ever diverge again.

    Cannot be imported here; must not be reimplemented differently.
    """
    start = int(methodology.get("start_season") or 0)
    end = int(methodology.get("end_season") or 0)
    train = int(methodology.get("train_seasons") or 0)
    stride = int(methodology.get("test_seasons") or 1) or 1
    if stride < 1 or train < 0 or start <= 0 or end <= 0:
        return []

    seasons: list[int] = []
    test = start + train
    while test <= end:
        seasons.append(test)
        test += stride
    return seasons


def evaluated_games(methodology: dict[str, Any], games_per_season: int = GAMES_PER_SEASON) -> int:
    """
    Games the walk-forward harness will actually evaluate, before any slice.

    One fold, one season, so this is simply the fold count times the games in a
    season.  This is the number that matters for whether a result means
    anything — not the span of seasons, which is what people quote.

    Known overstatement, FINDING HC-S6-F4, unruled and NOT fixed here:
    `games_per_season` is a flat 272, but 2015-2020 were 16-game seasons (256)
    and one 2022 game was cancelled.  On the tree's default window that is 1,904
    reported against 1,871 real — 1.8%, in the same direction as F3 was.
    Escalated in 00-PROJECT-LEAD/HYPOTHESIS-CHAT-QUESTIONS.md (HC-S6-Q4).
    """
    return max(0, len(fold_test_seasons(methodology)) * games_per_season)


def check_sample_size(
    config: dict[str, Any],
    slice_fraction: Optional[float] = None,
) -> list[dict[str, str]]:
    """
    Does the design leave enough games for the result to mean anything?

    `slice_fraction` is the real proportion of games surviving the game-universe
    filter, counted from curated.games by the caller. When it is None the slice
    is not applied and the check reports on the unsliced number only.
    """
    concerns: list[dict[str, str]] = []
    methodology = config.get("methodology") or {}
    evaluation = config.get("evaluation") or {}
    min_sample = int(evaluation.get("min_sample") or 0)

    base = evaluated_games(methodology)
    if base == 0:
        return [_concern(
            SEVERITY_HIGH, "sample_size",
            "This design evaluates zero games: the training window is as long as "
            "the season span, so no fold has anything held out. Widen the seasons "
            "or shorten the training window.",
        )]

    effective = int(base * slice_fraction) if slice_fraction is not None else base

    if slice_fraction is not None and effective < min_sample:
        concerns.append(_concern(
            SEVERITY_HIGH, "sample_size",
            f"The slice leaves about {effective:,} games, below your own minimum of "
            f"{min_sample:,}. At that size the result cannot distinguish an edge "
            f"from noise — a 3-point swing in hit rate is a handful of games.",
        ))
    elif effective < min_sample:
        concerns.append(_concern(
            SEVERITY_HIGH, "sample_size",
            f"This design evaluates about {effective:,} games, below your own "
            f"minimum of {min_sample:,}.",
        ))
    elif slice_fraction is not None and slice_fraction < 0.25:
        concerns.append(_concern(
            SEVERITY_MEDIUM, "sample_size",
            f"The slice keeps only {slice_fraction:.0%} of games (about {effective:,}). "
            f"It clears your minimum, but narrow slices are where spurious edges live.",
        ))
    return concerns


def check_threshold_plausibility(config: dict[str, Any]) -> list[dict[str, str]]:
    """The project's own rule: an implausibly high bar is a leakage suspect."""
    evaluation = config.get("evaluation") or {}
    if evaluation.get("metric") != "ats_hit_rate":
        return []
    threshold = float(evaluation.get("success_threshold") or 0)
    if threshold >= IMPLAUSIBLE_ATS_THRESHOLD:
        return [_concern(
            SEVERITY_HIGH, "implausible_threshold",
            f"A success threshold of {threshold:.0%} ATS against closing lines is "
            f"above the level this project treats as a leakage suspect "
            f"({IMPLAUSIBLE_ATS_THRESHOLD:.0%}). If the run clears it, the first "
            f"question is whether the app is wrong, not whether the edge is real.",
        )]
    if 0 < threshold <= 0.5:
        return [_concern(
            SEVERITY_MEDIUM, "trivial_threshold",
            f"A threshold of {threshold:.0%} is at or below a coin flip, so the "
            f"experiment cannot fail. Set a bar the hypothesis could miss.",
        )]
    return []


def check_slice_is_also_a_feature(config: dict[str, Any]) -> list[dict[str, str]]:
    """
    Conditioning on X while also feeding X to the model answers a different
    question than the one usually intended, and the two get conflated.
    """
    methodology = config.get("methodology") or {}
    universe = methodology.get("game_universe")
    if not universe:
        return []
    field = universe.get("field")
    columns = {(f or {}).get("column") for f in (config.get("features") or [])}
    if field in columns:
        return [_concern(
            SEVERITY_MEDIUM, "slice_is_feature",
            f"You are restricting the universe to a subset by `{field}` and also "
            f"giving `{field}` to the model as an input. Inside the slice that "
            f"column barely varies, so it contributes little — you are likely "
            f"asking a narrower question than you think.",
        )]
    return []


def check_cold_start(config: dict[str, Any], current_season: Optional[int]) -> list[dict[str, str]]:
    """Week 1 of any season rests on the prior-season-average fallback."""
    if current_season is None:
        return []
    methodology = config.get("methodology") or {}
    end_season = int(methodology.get("end_season") or 0)
    if end_season >= current_season:
        return [_concern(
            SEVERITY_MEDIUM, "cold_start",
            f"This includes season {end_season}, which is in progress or has not "
            f"finished. Early-week games in it rest on the prior-season-average "
            f"cold-start fallback, so a result driven by them is not comparable "
            f"to a late-season one.",
        )]
    return []


def _fingerprint(config: dict[str, Any]) -> tuple:
    methodology = config.get("methodology") or {}
    model = config.get("model") or {}
    columns = tuple(sorted((f or {}).get("column") or "" for f in (config.get("features") or [])))
    universe = methodology.get("game_universe") or {}
    return (
        config.get("target"),
        columns,
        model.get("type"),
        methodology.get("start_season"),
        methodology.get("end_season"),
        universe.get("field"),
        universe.get("operator"),
        universe.get("value"),
    )


def check_multiple_comparisons(
    config: dict[str, Any],
    prior_configs: Iterable[dict[str, Any]],
    prior_attempts_note: Optional[str] = None,
) -> list[dict[str, str]]:
    """
    How many near-variants of this have already been run?

    This is the check that matters most over a season. Test twenty variants of
    an idea and one clears 55% by luck alone; without this, that one gets
    remembered and the nineteen do not.
    """
    concerns: list[dict[str, str]] = []
    mine = _fingerprint(config)
    my_columns = set(mine[1])

    identical = 0
    near = 0
    for prior in prior_configs or []:
        theirs = _fingerprint(prior)
        if theirs == mine:
            identical += 1
            continue
        if theirs[0] != mine[0]:
            continue
        their_columns = set(theirs[1])
        union = my_columns | their_columns
        if union and len(my_columns & their_columns) / len(union) >= 0.6:
            near += 1

    if identical:
        concerns.append(_concern(
            SEVERITY_HIGH, "duplicate_experiment",
            f"This is identical to {identical} experiment(s) already run. Re-running "
            f"it produces the same answer; if you want a different one, change the "
            f"design rather than the run.",
        ))
    if near >= 3:
        concerns.append(_concern(
            SEVERITY_HIGH, "multiple_comparisons",
            f"{near} close variants of this have already been run. Across that many "
            f"attempts something clears a 53% bar by chance alone, so the usual "
            f"threshold no longer means what it means on a first look. Either raise "
            f"the bar or treat a pass as a hypothesis to re-test, not a result.",
        ))
    elif near:
        concerns.append(_concern(
            SEVERITY_LOW, "multiple_comparisons",
            f"{near} close variant(s) of this have been run before. Worth reading "
            f"those results before this one.",
        ))

    if prior_attempts_note and not (identical or near):
        concerns.append(_concern(
            SEVERITY_LOW, "prior_attempts",
            "You noted earlier attempts at this hypothesis, but none of the saved "
            "experiments closely match this design. Worth checking the log — an "
            "attempt that is not recorded still counts toward how many times you "
            "have looked.",
        ))
    return concerns


def check_falsifier(record_only: dict[str, Any]) -> list[dict[str, str]]:
    """A hypothesis nothing could refute is a pattern search wearing a hypothesis's clothes."""
    falsifier = (record_only or {}).get("falsifier")
    if falsifier is None or not str(falsifier).strip():
        return [_concern(
            SEVERITY_MEDIUM, "no_falsifier",
            "No falsifier was given. Without a result that would make you abandon "
            "this, the run cannot teach you anything — any outcome will look like "
            "partial support.",
        )]
    if len(str(falsifier).strip()) < 12:
        return [_concern(
            SEVERITY_LOW, "weak_falsifier",
            "The falsifier is very short. State the number or outcome that would "
            "actually change your mind, so the run can settle something.",
        )]
    return []


def check_unavailable_inputs(
    unavailable: Optional[dict[str, str]] = None,
    config: Optional[dict[str, Any]] = None,
) -> list[dict[str, str]]:
    """
    FINDING HC-S6-F6.  An input that could not be loaded is not an input that
    said "fine".

    `unavailable` maps the name of an input the caller could not obtain to the
    reason.  Each one becomes a HIGH concern naming the check it disabled, so a
    review taken during a storage outage cannot be mistaken for a review of a
    sound experiment.  Silence must never have the same shape as safety.

    Why this lives here and not in check_sample_size: with `slice_fraction=None`
    that function genuinely cannot tell "no filter was applied" from "the count
    failed", and guessing would make an honest no-filter config noisy.  The
    caller knows which of the two happened, so the caller says so.
    """
    if not unavailable:
        return []

    labels = {
        "slice_fraction": (
            "the real proportion of games surviving the game-universe filter"
        ),
        "prior_configs": (
            "the saved experiments this design would be compared against"
        ),
    }
    concerns: list[dict[str, str]] = []
    for name, reason in sorted(unavailable.items()):
        what = labels.get(name, name)
        message = (
            f"This review is incomplete: {what} could not be loaded ({reason}). "
            f"The checks that depend on it did not run, so their silence means "
            f"nothing here."
        )
        if name == "slice_fraction" and (config or {}).get("methodology", {}).get("game_universe"):
            message += (
                " Your design applies a game-universe filter, so the evaluated-game "
                "figure below counts the UNSLICED number and overstates the real "
                "sample. Re-run this review before reading it as a verdict."
            )
        concerns.append(_concern(SEVERITY_HIGH, "upstream_error", message))
    return concerns


def verdict_for(concerns: list[dict[str, str]]) -> str:
    highs = sum(1 for c in concerns if c["severity"] == SEVERITY_HIGH)
    if highs >= 2:
        return VERDICT_RECONSIDER
    if highs == 1:
        return VERDICT_CAUTION
    if concerns:
        return VERDICT_CAUTION if any(
            c["severity"] == SEVERITY_MEDIUM for c in concerns
        ) else VERDICT_PROCEED
    return VERDICT_PROCEED


def review(
    config: dict[str, Any],
    *,
    record_only: Optional[dict[str, Any]] = None,
    prior_configs: Optional[list[dict[str, Any]]] = None,
    slice_fraction: Optional[float] = None,
    current_season: Optional[int] = None,
    unavailable_inputs: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """
    Run every deterministic check.  Returns {concerns, verdict}.

    Advisory only.  Nothing in the dispatch path reads this.

    `unavailable_inputs` is how the caller reports an input it could not load —
    {input_name: reason}.  Each becomes a concern of its own and the verdict is
    never `proceed` while one is present, because a check that could not run is
    not a check that passed (FINDING HC-S6-F6).
    """
    record_only = record_only or {}
    concerns: list[dict[str, str]] = []
    concerns += check_unavailable_inputs(unavailable_inputs, config)
    concerns += check_sample_size(config, slice_fraction)
    concerns += check_threshold_plausibility(config)
    concerns += check_slice_is_also_a_feature(config)
    concerns += check_cold_start(config, current_season)
    concerns += check_multiple_comparisons(
        config, prior_configs or [], (record_only or {}).get("prior_attempts")
    )
    concerns += check_falsifier(record_only)

    order = {SEVERITY_HIGH: 0, SEVERITY_MEDIUM: 1, SEVERITY_LOW: 2}
    concerns.sort(key=lambda c: order.get(c["severity"], 3))

    verdict = verdict_for(concerns)
    if unavailable_inputs and verdict == VERDICT_PROCEED:
        # Belt and braces: an unavailable input is a HIGH concern, so this is
        # already unreachable.  It is here so that a later change to the
        # severity arithmetic cannot quietly restore a clean bill of health to a
        # review that checked nothing.
        verdict = VERDICT_CAUTION
    return {"concerns": concerns, "verdict": verdict}
