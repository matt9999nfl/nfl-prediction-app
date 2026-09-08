"""
Requirement D — the governor's honesty, checked against an independent count.

The rule for this module: never check the governor's arithmetic with the
governor's arithmetic. `governor.evaluated_games` and `GAMES_PER_SEASON` are
the things under test, so the reference number is built from two sources that
owe the governor nothing:

  1. real per-season game counts, paged out of the deployed /api/v1/games
     endpoint (the `live_season_game_counts` fixture), and
  2. the fold enumeration the RUNNER actually performs, restated here from
     02-MODELING/backtests/walk_forward.py::build_folds_from_config.

The implementation's own test for this (tests/test_scoping_governor.py::
test_evaluated_games_counts_folds_not_seasons) asserts `== 6 * 272`, which
restates the formula rather than checking it, and it does so at test_seasons=1
— the one value where the formula and the runner agree.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def independent_folds(start_season: int, end_season: int, train_seasons: int,
                      test_seasons: int) -> list[int]:
    """
    The test seasons the walk-forward runner will actually evaluate.

    Restated from 02-MODELING/backtests/walk_forward.py::build_folds_from_config:
    the first test season is start + train_seasons, each fold tests exactly ONE
    season, and `test_seasons` is the STRIDE between folds — not the number of
    seasons inside a fold.
    """
    seasons: list[int] = []
    test = start_season + train_seasons
    while test <= end_season:
        seasons.append(test)
        test += test_seasons
    return seasons


def independent_evaluated_games(counts: dict[int, int], start_season: int,
                                end_season: int, train_seasons: int,
                                test_seasons: int) -> int:
    """Real games in the seasons the runner will evaluate. No constants."""
    return sum(
        counts[season]
        for season in independent_folds(start_season, end_season, train_seasons, test_seasons)
        if season in counts
    )


def _methodology(**over) -> dict:
    base = {
        "type": "walk_forward",
        "start_season": 2015,
        "end_season": 2025,
        "train_seasons": 4,
        "test_seasons": 1,
        "game_universe": None,
    }
    base.update(over)
    return base


def _config(methodology=None, **over) -> dict:
    config = {
        "name": "governor arithmetic check",
        "target": "ats_cover",
        "features": [{"dataset": "curated", "column": "home_ol_sack_rate"}],
        "evaluation": {"metric": "ats_hit_rate", "success_threshold": 0.53, "min_sample": 500},
        "methodology": methodology or _methodology(),
        "model": {"type": "xgboost", "hyperparams": {}},
    }
    config.update(over)
    return config


# ── the independent count itself ─────────────────────────────────────────────


def test_real_season_lengths_are_not_a_single_constant(live_season_game_counts):
    """
    The premise of the two findings below: seasons are not all 272 games.

    Documented here so the findings do not rest on an assumption. 2015-2020 are
    16-game seasons (256 games); 2021 onward are 17-game seasons (272), and one
    2022 game was cancelled.
    """
    counts = live_season_game_counts
    assert counts[2015] != counts[2024], (
        "every season now has the same number of games; the 272 constant may "
        "have become correct and these findings need re-reading"
    )
    assert counts[2015] == 256
    assert counts[2024] == 272


# ── FINDING HC-S6-F3 ─────────────────────────────────────────────────────────


@pytest.mark.xfail(
    strict=True,
    reason=(
        "FINDING HC-S6-F3: evaluated_games treats test_seasons as a per-fold "
        "multiplier (folds * test_seasons * 272). The runner treats it as the "
        "STRIDE between folds and evaluates one season per fold. At "
        "test_seasons=2 the governor reports 3.5x the games that will actually "
        "be evaluated. Implementation deliberately not modified."
    ),
)
def test_evaluated_games_matches_an_independent_count_at_test_seasons_2(
    scoping_api, live_season_game_counts
):
    governor = scoping_api["governor"]
    methodology = _methodology(test_seasons=2)
    reported = governor.evaluated_games(methodology)
    actual = independent_evaluated_games(live_season_game_counts, 2015, 2025, 4, 2)
    assert reported == actual, (
        f"governor says {reported:,} games will be evaluated; the runner will "
        f"evaluate {actual:,} across seasons "
        f"{independent_folds(2015, 2025, 4, 2)}"
    )


# ── FINDING HC-S6-F4 ─────────────────────────────────────────────────────────


@pytest.mark.xfail(
    strict=True,
    reason=(
        "FINDING HC-S6-F4: GAMES_PER_SEASON is a flat 272, but 2015-2020 were "
        "256-game seasons and one 2022 game was cancelled. On the tree's own "
        "default window the reported figure is 1,904 against a real 1,871. "
        "Small on its own; it is the same overstatement direction as F3. "
        "Implementation deliberately not modified."
    ),
)
def test_evaluated_games_matches_an_independent_count_on_the_default_window(
    scoping_api, live_season_game_counts
):
    """The tree's own defaults: 2015-2025, 4 training seasons, 1 held out."""
    governor = scoping_api["governor"]
    reported = governor.evaluated_games(_methodology())
    actual = independent_evaluated_games(live_season_game_counts, 2015, 2025, 4, 1)
    assert reported == actual, (
        f"governor says {reported:,}, real count is {actual:,} across seasons "
        f"{independent_folds(2015, 2025, 4, 1)}"
    )


def test_the_error_is_an_overstatement_not_an_understatement(
    scoping_api, live_season_game_counts
):
    """
    Direction matters more than size here.

    The sample-size check exists to stop an under-powered experiment. An
    overstatement makes it quieter exactly when the design is thinner than the
    user thinks — which is the failure mode that stays invisible.
    """
    governor = scoping_api["governor"]
    for test_seasons in (1, 2, 3):
        methodology = _methodology(test_seasons=test_seasons)
        reported = governor.evaluated_games(methodology)
        actual = independent_evaluated_games(
            live_season_game_counts, 2015, 2025, 4, test_seasons
        )
        assert reported >= actual, (
            f"at test_seasons={test_seasons} the governor understates "
            f"({reported:,} vs {actual:,}) — that would be a different finding"
        )


# ── FINDING HC-S6-F5: the consequence ────────────────────────────────────────


@pytest.mark.xfail(
    strict=True,
    reason=(
        "FINDING HC-S6-F5: because of F3, the governor returns zero concerns "
        "and a 'proceed' verdict for a design that evaluates ~1,072 games "
        "against a stated minimum of 1,500. The check that exists to catch an "
        "under-powered experiment is silent on one. Implementation "
        "deliberately not modified."
    ),
)
def test_the_governor_is_not_silent_on_a_design_that_misses_its_own_minimum(
    scoping_api, live_season_game_counts
):
    governor = scoping_api["governor"]
    methodology = _methodology(test_seasons=2)
    config = _config(
        methodology=methodology,
        evaluation={"metric": "ats_hit_rate", "success_threshold": 0.53, "min_sample": 1500},
    )
    actual = independent_evaluated_games(live_season_game_counts, 2015, 2025, 4, 2)
    assert actual < 1500, "fixture is wrong — the design must genuinely miss the minimum"

    result = governor.review(
        config,
        record_only={"falsifier": "below 50% ATS in every fold", "mechanism": "market lag"},
        prior_configs=[],
        slice_fraction=None,
        current_season=2026,
    )
    assert any(c["kind"] == "sample_size" for c in result["concerns"]), (
        f"the design evaluates about {actual:,} games against a minimum of "
        f"1,500 and the governor raised no sample-size concern. Verdict: "
        f"{result['verdict']!r}, concerns: {result['concerns']!r}"
    )


# ── FINDING HC-S6-F6: a failed slice count is indistinguishable from no slice ─


def test_a_failed_slice_count_is_reported_as_if_no_slice_were_applied(scoping_api):
    """
    FINDING HC-S6-F6 (documented as a passing test, because the behaviour is
    what it is — the finding is that this behaviour is wrong).

    app/routers/scoping.py catches any exception from sq.slice_fraction, logs a
    warning, and leaves `fraction = None`. governor.check_sample_size treats
    None as "the slice is not applied and the check reports on the unsliced
    number only". So a BigQuery failure and a config with no filter produce
    byte-identical governor output, and the response's `slice_fraction: null`
    is the only trace — indistinguishable from the legitimate no-filter case.

    The failure degrades toward silence and toward a LARGER apparent sample,
    which is the unsafe direction.
    """
    governor = scoping_api["governor"]
    sliced = _config(
        methodology=_methodology(
            game_universe={"field": "div_game", "operator": "eq", "value": True}
        ),
        evaluation={"metric": "ats_hit_rate", "success_threshold": 0.53, "min_sample": 1500},
    )

    # What the user sees when the count SUCCEEDS (div_game is about 36% of games).
    with_real_count = governor.check_sample_size(sliced, slice_fraction=0.365)
    # What the user sees when the count FAILS and the exception is swallowed.
    with_failed_count = governor.check_sample_size(sliced, slice_fraction=None)

    assert with_real_count, "a 36% slice of 1,904 games is below 1,500 and must be flagged"
    assert not with_failed_count, (
        "behaviour changed: a failed slice count now produces a concern. "
        "Re-read this finding."
    )
    assert with_real_count != with_failed_count, (
        "a failed BigQuery count produces the same advice as a sound one"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "FINDING HC-S6-F3 (sharpest form): at test_seasons=3 the governor "
        "reports 5,712 evaluated games from a 2015-2025 window that contains "
        "2,895 games in total. An estimate cannot exceed the universe it is "
        "drawn from. Implementation deliberately not modified."
    ),
)
def test_evaluated_games_never_exceeds_the_games_that_exist_in_the_window(
    scoping_api, live_season_game_counts
):
    """
    The form of F3 that needs no agreement about fold semantics.

    Whatever `test_seasons` is taken to mean, the number of games a backtest
    evaluates cannot be larger than the number of games played in the seasons
    it covers. Each game is evaluated at most once — walk-forward never tests
    the same season twice.
    """
    governor = scoping_api["governor"]
    counts = live_season_game_counts
    universe = sum(counts[season] for season in range(2015, 2026) if season in counts)

    for test_seasons in (1, 2, 3):
        reported = governor.evaluated_games(_methodology(test_seasons=test_seasons))
        assert reported <= universe, (
            f"at test_seasons={test_seasons} the governor reports {reported:,} "
            f"evaluated games from a window containing only {universe:,}"
        )
