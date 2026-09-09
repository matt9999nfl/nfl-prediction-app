"""
One definition of a fold — FINDING HC-S6-F3.

`governor.fold_test_seasons` and
`02-MODELING/backtests/walk_forward.py::build_folds_from_config` must agree, or
the governor is advising on an experiment other than the one that will run.
They disagreed: the governor read `test_seasons` as a per-fold multiplier and
counted folds as `span - train_seasons`, while the runner treats it as the
stride between folds and evaluates exactly one season per fold. The two agreed
only at `test_seasons=1`, which was the single value the old test asserted, so
the arithmetic checked itself at the one point it happened to be right.

WHY THE RUNNER IS LOADED FROM SOURCE RATHER THAN IMPORTED
---------------------------------------------------------
`import walk_forward` pulls pandas, sklearn and xgboost, none of which the
backend has, and ADR-012 commitment 1 forbids app/scoping/ from importing
anything outside stdlib, pydantic and its own siblings — so the governor cannot
call the runner's function and the duplication cannot be deleted outright.
What can be removed is the DISAGREEMENT: the reference function is read out of
the runner's own file and executed on its own, with no imports, so this test
compares against the code that actually runs rather than against a restatement
of it. Change either definition and this goes red.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

from app.scoping.governor import GAMES_PER_SEASON, evaluated_games, fold_test_seasons


def _walk_forward_path() -> Path | None:
    override = os.getenv("NFL_MODELING_ROOT")
    roots = [Path(override)] if override else []
    here = Path(__file__).resolve()
    roots += [parent / "02-MODELING" for parent in here.parents]
    for root in roots:
        candidate = root / "backtests" / "walk_forward.py"
        if candidate.is_file():
            return candidate
    return None


@pytest.fixture(scope="module")
def runner_build_folds():
    """
    The runner's own build_folds_from_config, lifted out of its module.

    Only that one function is compiled, so none of the runner's heavy imports
    are needed. If the file exists but the function has moved or changed name,
    this FAILS rather than skips — a silent skip is how the disagreement got
    here.
    """
    path = _walk_forward_path()
    if path is None:
        pytest.skip(
            "02-MODELING/backtests/walk_forward.py is not present in this "
            "workspace, so the governor's fold arithmetic could NOT be checked "
            "against the runner. Set NFL_MODELING_ROOT to check it."
        )
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(
        (n for n in tree.body
         if isinstance(n, ast.FunctionDef) and n.name == "build_folds_from_config"),
        None,
    )
    assert node is not None, (
        f"{path} no longer defines build_folds_from_config. The governor's fold "
        f"arithmetic is pinned to it; find where the runner's definition went."
    )
    namespace: dict = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["build_folds_from_config"]


MATRIX = [
    (start, end, train, test)
    for start, end in ((2015, 2024), (2015, 2025), (2018, 2025), (2020, 2022))
    for train in (1, 2, 3, 4, 5, 8)
    for test in (1, 2, 3, 4)
]


@pytest.mark.parametrize("start,end,train,test", MATRIX)
def test_the_governor_counts_the_folds_the_runner_will_build(
    runner_build_folds, start, end, train, test
):
    methodology = {
        "type": "walk_forward", "start_season": start, "end_season": end,
        "train_seasons": train, "test_seasons": test,
    }
    expected = runner_build_folds(start, end, train, test)
    assert fold_test_seasons(methodology) == [season for _train, season in expected], (
        f"governor and runner disagree at start={start} end={end} "
        f"train={train} test={test}"
    )
    assert evaluated_games(methodology) == len(expected) * GAMES_PER_SEASON


def test_the_folds_match_the_runners_hardcoded_phase_one_list(runner_build_folds):
    """
    The runner's FOLDS constant is the Phase 1 spec, written by hand: train
    2015-2018 test 2019, through train 2020-2023 test 2024. The governor must
    count six folds for that window.
    """
    methodology = {"start_season": 2015, "end_season": 2024,
                   "train_seasons": 4, "test_seasons": 1}
    assert fold_test_seasons(methodology) == [2019, 2020, 2021, 2022, 2023, 2024]
    assert evaluated_games(methodology) == 6 * GAMES_PER_SEASON


def test_test_seasons_is_a_stride_not_a_multiplier():
    """
    The finding in one line, checked without the runner.

    At `test_seasons=2` over 2015-2025 with a 4-season training window the
    runner evaluates 2019, 2021, 2023 and 2025 — four seasons. The old formula
    reported `(11 - 4) * 2 * 272` = 3,808 games, roughly 3.5x the truth, and
    the sample-size check cleared designs it exists to stop.
    """
    methodology = {"start_season": 2015, "end_season": 2025,
                   "train_seasons": 4, "test_seasons": 2}
    assert fold_test_seasons(methodology) == [2019, 2021, 2023, 2025]
    assert evaluated_games(methodology) == 4 * GAMES_PER_SEASON
    assert evaluated_games(methodology) < 3808


def test_no_fold_is_evaluated_twice():
    """
    Walk-forward never tests the same season twice, whatever the stride, so the
    count can never exceed the seasons in the window. The sharpest form of the
    finding: at test_seasons=3 the old formula reported 5,712 games from a
    window containing about 2,900.
    """
    for test in (1, 2, 3, 4):
        methodology = {"start_season": 2015, "end_season": 2025,
                       "train_seasons": 4, "test_seasons": test}
        seasons = fold_test_seasons(methodology)
        assert len(seasons) == len(set(seasons))
        assert set(seasons) <= set(range(2015, 2026))


def test_a_window_with_nothing_held_out_evaluates_nothing():
    assert fold_test_seasons({"start_season": 2020, "end_season": 2023,
                              "train_seasons": 4, "test_seasons": 1}) == []
    assert evaluated_games({"start_season": 2020, "end_season": 2023,
                            "train_seasons": 4, "test_seasons": 1}) == 0


@pytest.mark.parametrize("bad", [
    {"start_season": 2015, "end_season": 2025, "train_seasons": 4, "test_seasons": 0},
    {"start_season": 2015, "end_season": 2025, "train_seasons": 4, "test_seasons": None},
    {},
])
def test_a_degenerate_methodology_terminates(bad):
    """A zero or missing stride must not spin forever; it falls back to one."""
    assert isinstance(fold_test_seasons(bad), list)
