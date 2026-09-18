#!/usr/bin/env python3
"""
Week analysis — what the model weighted on each pick, patterns across the
picks, and how they relate to the market (PROMPT-WEEK1-ANALYSIS.md, Stage 2 of
PROMPT-PICK-EXPLANATIONS-AND-EDGE-LAB.md).

Analysis only: reads stored explanations (experiments.prediction_explanations),
the live served pick, result and closing spread (experiments.backtest_predictions),
moneylines (raw_nflfastr.schedules) and the line change-log
(raw_lines.line_snapshots). Writes nothing to BigQuery, builds no model,
changes no production behaviour.

Live-pick authority: a game can carry more than one explanation run (an exact
backfill appended without deleting an earlier approximate one). This picks the
same run the API serves — exact over approximate, then newest created_at — and
re-signs pick_direction_contribution toward the LIVE served pick, exactly like
app/queries/explanations.py::get_game_explanation_rows. A game whose
explanation run leans the other way from the live pick keeps
side_mismatch=True and is excluded from every "toward the pick" aggregate
statistic (but not from the per-game sections, which cover all games).

Usage
-----
    python backtests/analyze_week_explanations.py --season 2026 --week 1
    python backtests/analyze_week_explanations.py --season 2026 --week 2
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from google.cloud import bigquery
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtests.explanations import matchup_view  # noqa: E402
from backtests.predict_upcoming import PRODUCTION_EXPERIMENT_ID  # noqa: E402
from features.families import FAMILIES  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
logger = logging.getLogger(__name__)

PROJECT = "nfl-model-471509"
EXPLANATIONS_TABLE = f"{PROJECT}.experiments.prediction_explanations"
PREDS_TABLE = f"{PROJECT}.experiments.backtest_predictions"
SCHEDULES_TABLE = f"{PROJECT}.raw_nflfastr.schedules"
LINE_SNAPSHOTS_TABLE = f"{PROJECT}.raw_lines.line_snapshots"

REPORTS_DIR = ROOT / "backtests" / "reports"

RECONSTRUCTION_TOLERANCE = 1e-4
WEATHER_FEATURES = {"temp", "wind", "roof_dome"}
KEY_NUMBERS = (3, 7)
# Part A.3, PROMPT-FIX-SPREAD-SIGN-AND-LINE-SNAPSHOTS.md: spread-favourite and
# moneyline-favourite must agree at least this often, where moneylines exist.
FAVORITE_AGREEMENT_FLOOR = 0.80

# Dated record of side-mismatches already confirmed against the live pick
# (see HANDOFF-2026-09-18-stage1-finish.md). If a listed week's mismatch set
# no longer matches what's stored, that's new information worth a second
# look, not necessarily a bug — but it changes the report, so main() flags it
# loudly rather than silently accepting a new number.
KNOWN_SIDE_MISMATCHES: dict[tuple[int, int], set[str]] = {
    (2026, 1): {"2026_01_ATL_PIT", "2026_01_GB_MIN", "2026_01_NYJ_TEN"},
    (2026, 2): set(),
}


# ── BigQuery reads ───────────────────────────────────────────────────────────


def fetch_explanations(
    client: bigquery.Client, season: int, week: int, experiment_id: str = PRODUCTION_EXPERIMENT_ID,
) -> pd.DataFrame:
    """
    One row per (game, feature) for the SAME run the API would serve for that
    game: exact over approximate, then newest created_at — the same rule as
    app/queries/explanations.py::get_game_explanation_rows, applied to a whole
    week at once instead of one game.
    """
    query = f"""
        WITH run_summary AS (
          SELECT game_id, run_id,
                 LOGICAL_OR(is_approximate) AS is_approx,
                 MAX(created_at) AS created_at
          FROM `{EXPLANATIONS_TABLE}`
          WHERE experiment_id = @eid AND season = @season AND week = @week
          GROUP BY game_id, run_id
        ),
        best_run AS (
          SELECT game_id, run_id,
                 ROW_NUMBER() OVER (
                   PARTITION BY game_id ORDER BY is_approx ASC, created_at DESC
                 ) AS rn
          FROM run_summary
        )
        SELECT pe.*
        FROM `{EXPLANATIONS_TABLE}` pe
        JOIN best_run br ON br.game_id = pe.game_id AND br.run_id = pe.run_id AND br.rn = 1
        WHERE pe.experiment_id = @eid AND pe.season = @season AND pe.week = @week
        ORDER BY pe.game_id, pe.abs_rank
    """
    params = [
        bigquery.ScalarQueryParameter("eid", "STRING", experiment_id),
        bigquery.ScalarQueryParameter("season", "INT64", season),
        bigquery.ScalarQueryParameter("week", "INT64", week),
    ]
    df = client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=params)).to_dataframe()
    logger.info("Fetched %d explanation rows for %d games", len(df), df["game_id"].nunique())
    return df


def fetch_live_games(
    client: bigquery.Client, season: int, week: int, experiment_id: str = PRODUCTION_EXPERIMENT_ID,
) -> pd.DataFrame:
    """
    The served pick, the line at pick time, and (if graded) result for every
    game. `backtest_predictions.home_spread_close` is a snapshot of
    curated.games' spread taken when predict_upcoming.py generated the pick —
    it never updates after that, unlike curated.games' own column, which
    stays live until kickoff (see snapshot_lines.py). Renamed to
    pick_time_spread here so it can't be confused with the closing line
    (fetch_game_results pulls that separately from curated.games).
    """
    query = f"""
        SELECT game_id, home_team, away_team,
               home_spread_close AS pick_time_spread,
               predicted_home_cover_prob AS live_predicted_home_cover_prob,
               predicted_side AS live_predicted_side,
               actual_home_covered, correct
        FROM `{PREDS_TABLE}`
        WHERE experiment_id = @eid AND season = @season AND week = @week
        ORDER BY game_id
    """
    params = [
        bigquery.ScalarQueryParameter("eid", "STRING", experiment_id),
        bigquery.ScalarQueryParameter("season", "INT64", season),
        bigquery.ScalarQueryParameter("week", "INT64", week),
    ]
    return client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=params)).to_dataframe()


def fetch_game_results(client: bigquery.Client, season: int, week: int) -> pd.DataFrame:
    """
    home_score/away_score/home_spread_close from curated.games — the scores
    tell a push (game played, actual_home_covered NULL because the margin
    equalled the spread exactly) apart from a game that simply hasn't been
    played yet (also NULL). home_spread_close here is CURATED'S OWN current
    value — the closing line (live until kickoff, frozen after — see
    snapshot_lines.py) — renamed closing_spread so it isn't confused with the
    pick-time spread fetch_live_games pulls from backtest_predictions.
    """
    query = """
        SELECT game_id, home_score, away_score,
               home_spread_close AS closing_spread
        FROM `nfl-model-471509.curated.games`
        WHERE season = @season AND week = @week
    """
    params = [
        bigquery.ScalarQueryParameter("season", "INT64", season),
        bigquery.ScalarQueryParameter("week", "INT64", week),
    ]
    return client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=params)).to_dataframe()


def fetch_moneylines(client: bigquery.Client, season: int, week: int) -> pd.DataFrame:
    query = f"""
        SELECT CAST(game_id AS STRING) AS game_id,
               home_moneyline, away_moneyline
        FROM `{SCHEDULES_TABLE}`
        WHERE season = @season AND week = @week
    """
    params = [
        bigquery.ScalarQueryParameter("season", "INT64", season),
        bigquery.ScalarQueryParameter("week", "INT64", week),
    ]
    return client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=params)).to_dataframe()


def fetch_moneyline_population(client: bigquery.Client) -> pd.DataFrame:
    """Per season, how many schedules rows have a moneyline — states the limit honestly."""
    query = f"""
        SELECT season, COUNT(*) AS n_games,
               COUNTIF(home_moneyline IS NOT NULL) AS n_with_home_moneyline
        FROM `{SCHEDULES_TABLE}`
        GROUP BY season ORDER BY season
    """
    return client.query(query).to_dataframe()


def fetch_line_snapshots(client: bigquery.Client, season: int, week: int) -> pd.DataFrame:
    """
    First-seen and closing spread per game from the change-log. Snapshots only
    began 2026-09-09 (`01-DATA-PIPELINE/scripts/snapshot_lines.py`); an empty
    frame for a week means no snapshots exist for it yet, which the market
    section states rather than silently reporting nothing.
    """
    query = f"""
        WITH ranked AS (
          SELECT game_id, captured_at, game_completed, spread_line,
                 ROW_NUMBER() OVER (PARTITION BY game_id ORDER BY captured_at ASC) AS rn_first,
                 ROW_NUMBER() OVER (
                   PARTITION BY game_id
                   ORDER BY game_completed ASC, captured_at DESC
                 ) AS rn_last_pre_kickoff
          FROM `{LINE_SNAPSHOTS_TABLE}`
          WHERE season = @season AND week = @week
        )
        SELECT
          game_id,
          COUNT(*) AS n_snapshots,
          MAX(IF(rn_first = 1, spread_line, NULL)) AS first_seen_spread,
          MAX(IF(rn_first = 1, captured_at, NULL)) AS first_seen_at,
          MAX(IF(rn_last_pre_kickoff = 1, spread_line, NULL)) AS last_seen_spread
        FROM ranked
        GROUP BY game_id
    """
    params = [
        bigquery.ScalarQueryParameter("season", "INT64", season),
        bigquery.ScalarQueryParameter("week", "INT64", week),
    ]
    return client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=params)).to_dataframe()


# ── Pure transforms (unit-testable on synthetic frames) ─────────────────────


def resign_toward_live_pick(exp_df: pd.DataFrame, live_df: pd.DataFrame) -> pd.DataFrame:
    """
    Add live_predicted_side, side_mismatch, and pick_direction_live — the
    stored pick_direction_contribution re-signed toward the LIVE served pick
    whenever the explanation run's own predicted_side disagrees with it.
    Mirrors app/queries/explanations.py's re-signing exactly.
    """
    live_side = live_df.set_index("game_id")["live_predicted_side"]
    merged = exp_df.merge(
        live_side, left_on="game_id", right_index=True, how="left", validate="many_to_one",
    )
    if merged["live_predicted_side"].isna().any():
        missing = sorted(merged.loc[merged["live_predicted_side"].isna(), "game_id"].unique())
        raise ValueError(f"No live served pick found for explained game(s): {missing}")
    merged["side_mismatch"] = merged["predicted_side"] != merged["live_predicted_side"]
    merged["pick_direction_live"] = np.where(
        merged["side_mismatch"], -merged["pick_direction_contribution"], merged["pick_direction_contribution"],
    )
    return merged


def check_reconstruction(exp_df: pd.DataFrame, tol: float = RECONSTRUCTION_TOLERANCE) -> pd.DataFrame:
    """
    Per game: does bias_logodds + sum(contribution_logodds) reconstruct
    logit(predicted_home_cover_prob) (the explanation run's own probability,
    which is what the stored contributions actually sum to) within tol?
    """
    p = exp_df.groupby("game_id")["predicted_home_cover_prob"].first()
    logit_p = np.log(p / (1.0 - p))
    bias = exp_df.groupby("game_id")["bias_logodds"].first()
    contrib_sum = exp_df.groupby("game_id")["contribution_logodds"].sum()
    diff = (bias + contrib_sum - logit_p).abs()
    out = pd.DataFrame({"bias_plus_contrib": bias + contrib_sum, "logit_p": logit_p, "diff": diff})
    out["passed"] = out["diff"] <= tol
    return out.reset_index()


def top_drivers(exp_df: pd.DataFrame, game_id: str, n: int = 5) -> pd.DataFrame:
    """Top-n rows for one game by |pick_direction_live| (toward the live pick)."""
    g = exp_df[exp_df["game_id"] == game_id].copy()
    g["_abs"] = g["pick_direction_live"].abs()
    return g.sort_values("_abs", ascending=False).head(n).drop(columns=["_abs"])


def family_shares(exp_df: pd.DataFrame, game_id: str) -> pd.DataFrame:
    """Per family, this game's summed |pick_direction_live| and its share of the total."""
    g = exp_df[exp_df["game_id"] == game_id]
    by_fam = g.groupby("family")["pick_direction_live"].apply(lambda s: s.abs().sum())
    total = by_fam.sum()
    out = by_fam.sort_values(ascending=False).reset_index(name="abs_contribution")
    out["share"] = out["abs_contribution"] / total if total else 0.0
    return out


def imputed_and_weather_rows(exp_df: pd.DataFrame, game_id: str) -> pd.DataFrame:
    """Rows for one game with was_imputed=True or in the weather family — known-buggy, called out regardless of rank."""
    g = exp_df[exp_df["game_id"] == game_id]
    flagged = g[g["was_imputed"] | (g["family"] == "weather")]
    return flagged.sort_values("abs_rank")


def plain_english_summary(game_row: pd.Series, top_df: pd.DataFrame) -> str:
    """Two-sentence template summary, generated from the numbers — no free text."""
    pick_team = game_row["home_team"] if game_row["live_predicted_side"] == "home" else game_row["away_team"]
    opp_team = game_row["away_team"] if game_row["live_predicted_side"] == "home" else game_row["home_team"]
    fams = list(dict.fromkeys(top_df["family"].tolist()))[:2]
    fam_phrase = fams[0] if len(fams) < 2 else f"{fams[0]} and {fams[1]}"
    s1 = f"The model favours {pick_team} over {opp_team}, driven mainly by {fam_phrase}."
    top1 = top_df.iloc[0]
    team1 = game_row["home_team"] if top1["side"] == "home" else (
        game_row["away_team"] if top1["side"] == "away" else "game context"
    )
    pctile_txt = f", {team1} at the {_ordinal(top1['league_pctile'])} league percentile," if pd.notna(top1["league_pctile"]) else ""
    s2 = (
        f"Top single driver: {top1['feature']} ({top1['family']}){pctile_txt} "
        f"contributing {top1['pick_direction_live']:+.3f} log-odds toward the pick."
    )
    return s1 + " " + s2


def family_push_stats(exp_df: pd.DataFrame, mismatched_game_ids: set[str]) -> pd.DataFrame:
    """
    Per family: mean |net contribution| per game, and the fraction of games
    where the family's net contribution pushed toward the picked side — given
    both over all games and excluding side-mismatch games.
    """
    fam_game = exp_df.groupby(["game_id", "family"])["pick_direction_live"].sum().reset_index(name="net")
    all_games = fam_game.groupby("family")["net"]
    clean = fam_game[~fam_game["game_id"].isin(mismatched_game_ids)].groupby("family")["net"]

    out = pd.DataFrame({
        "family": sorted(fam_game["family"].unique()),
    })
    out = out.set_index("family")
    out["mean_abs_contribution_16"] = all_games.apply(lambda s: s.abs().mean())
    out["pushed_toward_pick_frac_16"] = all_games.apply(lambda s: (s > 0).mean())
    out["n_games_16"] = all_games.size()
    out["pushed_toward_pick_frac_13"] = clean.apply(lambda s: (s > 0).mean())
    out["n_games_13"] = clean.size()
    return out.reset_index().sort_values("mean_abs_contribution_16", ascending=False)


def family_game_matrix(exp_df: pd.DataFrame) -> pd.DataFrame:
    """game_id x family matrix of net pick_direction_live — the input to clustering."""
    fam_game = exp_df.groupby(["game_id", "family"])["pick_direction_live"].sum().unstack("family").fillna(0.0)
    return fam_game.reindex(columns=FAMILIES, fill_value=0.0)


def cluster_games(matrix: pd.DataFrame, distance_threshold: float = 0.7) -> pd.DataFrame:
    """
    Hierarchical (average-linkage) clustering on cosine distance between
    games' family-level pick-direction vectors. n is small (16), so this is
    kept simple: cut the tree at a fixed cosine-distance threshold rather than
    fitting a target cluster count. Returns game_id -> cluster_id, plus each
    cluster's dominant family (largest mean |contribution| within the group).
    """
    from scipy.spatial.distance import pdist

    values = matrix.to_numpy()
    # A game whose vector is all-zero has no defined cosine distance; guard
    # against it even though it shouldn't occur with real per-feature rows.
    norms = np.linalg.norm(values, axis=1)
    if (norms == 0).any():
        raise ValueError("cluster_games: at least one game has an all-zero family vector")

    dist = pdist(values, metric="cosine")
    Z = linkage(dist, method="average")
    labels = fcluster(Z, t=distance_threshold, criterion="distance")

    out = pd.DataFrame({"game_id": matrix.index, "cluster": labels})
    dominant = {}
    for cluster_id, sub in out.groupby("cluster"):
        game_ids = sub["game_id"]
        sub_matrix = matrix.loc[game_ids]
        mean_abs = sub_matrix.abs().mean().sort_values(ascending=False)
        dominant[cluster_id] = list(mean_abs.head(2).index)
    out["dominant_families"] = out["cluster"].map(dominant)
    return out.sort_values(["cluster", "game_id"]).reset_index(drop=True)


def top_driver_shapes(exp_df: pd.DataFrame) -> pd.DataFrame:
    """
    Per game, the single top-ranked driver's (family, side) — a "shape" like
    ("OL pass protection", "home"). Grouping and counting these across games
    is the recurring-matchup-shape view.
    """
    top1 = exp_df[exp_df["abs_rank"] == 1][["game_id", "family", "side", "feature"]].copy()
    return top1.rename(columns={"family": "shape_family", "side": "shape_side", "feature": "shape_feature"})


def spread_family_correlation(exp_df: pd.DataFrame, games_df: pd.DataFrame) -> pd.DataFrame:
    """
    Per family: Pearson r between its net home-cover-oriented contribution
    (contribution_logodds, NOT pick-direction — a fixed orientation is needed
    to correlate against a fixed-orientation spread) and closing_spread,
    across all games in the week. A family tracking the spread is largely
    repeating the market; one that doesn't is where an edge would have to
    come from.
    """
    fam_game = exp_df.groupby(["game_id", "family"])["contribution_logodds"].sum().unstack("family")
    fam_game = fam_game.join(games_df.set_index("game_id")["closing_spread"])
    rows = []
    for fam in FAMILIES:
        if fam not in fam_game.columns:
            continue
        pair = fam_game[[fam, "closing_spread"]].dropna()
        r = pair[fam].corr(pair["closing_spread"]) if len(pair) > 2 else float("nan")
        rows.append({"family": fam, "n_games": len(pair), "corr_with_closing_spread": r})
    return pd.DataFrame(rows).sort_values("corr_with_closing_spread", key=lambda s: s.abs(), ascending=False)


def devig_moneylines(ml_df: pd.DataFrame) -> pd.DataFrame:
    """American-odds moneylines -> de-vigged home win probability."""
    def implied(odds: float) -> float:
        return 100.0 / (odds + 100.0) if odds > 0 else (-odds) / (-odds + 100.0)

    out = ml_df.copy()
    out["home_implied"] = out["home_moneyline"].apply(implied)
    out["away_implied"] = out["away_moneyline"].apply(implied)
    overround = out["home_implied"] + out["away_implied"]
    out["home_devigged_prob"] = out["home_implied"] / overround
    return out


def favorite_or_underdog(spread: float) -> str:
    """
    Which side is favoured by a spread carrying curated.games' convention:
    POSITIVE home_spread_close means the HOME team is favoured (nflverse
    spread_line convention — the opposite of betting notation, where a
    favourite is written negative). Verified from data in
    01-DATA-PIPELINE/scripts/verify_label_convention.py (C1: favourites win
    outright ~66-70% of the time under this reading; the inverted reading
    lands near 30%). Getting this backwards is a recurring failure mode here
    (INC-001, 2026-09-10, 2026-09-14, 2026-09-18) — see test_favorite_or_underdog
    and test_ats_label_fixture_set for the regression guards.
    """
    if pd.isna(spread):
        return "unknown"
    if spread > 0:
        return "home"
    if spread < 0:
        return "away"
    return "pickem"


def near_key_number(spread: float, tolerance: float = 0.5) -> int | None:
    if pd.isna(spread):
        return None
    for k in KEY_NUMBERS:
        if abs(abs(spread) - k) <= tolerance:
            return k
    return None


def favorite_agreement(games: pd.DataFrame, ml_table: pd.DataFrame) -> tuple[float, pd.DataFrame]:
    """
    Data-derived guard: the favourite implied by the closing spread should
    agree with the favourite implied by the de-vigged moneyline on almost
    every game (a moneyline favourite is whichever side prices above 50% —
    home_devigged_prob > 0.5 means home). Returns (agreement_fraction,
    mismatches_df). Disagreement here would mean the spread-sign convention
    in this script is STILL wrong, not just a market quirk (moneyline and
    spread favourites virtually always agree in the NFL).
    """
    merged = games[["game_id", "favorite"]].merge(
        ml_table[["game_id", "home_devigged_prob"]], on="game_id", how="inner",
    )
    merged["moneyline_favorite"] = np.where(merged["home_devigged_prob"] > 0.5, "home", "away")
    merged["agrees"] = merged["favorite"] == merged["moneyline_favorite"]
    frac = merged["agrees"].mean() if len(merged) else float("nan")
    mismatches = merged[~merged["agrees"]].copy()
    return frac, mismatches


def enforce_favorite_agreement(
    games: pd.DataFrame, ml_table: pd.DataFrame, season: int, week: int,
    floor: float = FAVORITE_AGREEMENT_FLOOR,
) -> tuple[float, pd.DataFrame]:
    """
    Raises SystemExit (writing nothing) if the spread-favourite/moneyline-
    favourite agreement falls below `floor`. Split out from run() so the
    guard itself — not just favorite_agreement()'s arithmetic — is directly
    unit-testable without mocking BigQuery.
    """
    agree_frac, mismatches = favorite_agreement(games, ml_table)
    if agree_frac < floor:
        names = ", ".join(mismatches["game_id"].tolist())
        raise SystemExit(
            f"STOP: spread-favourite vs. moneyline-favourite agreement is {agree_frac:.0%} "
            f"(need >= {floor:.0%}) for {season} week {week}. "
            f"Disagreements: {names}. This means the spread-sign convention is wrong again, "
            "not a market quirk. Write this to 00-PROJECT-LEAD/QUESTIONS.md and stop — "
            "nothing was written."
        )
    return agree_frac, mismatches


# ── Report assembly ──────────────────────────────────────────────────────────


def _fmt(x, spec="+.3f"):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "n/a"
    return format(x, spec)


def _ordinal(n: float) -> str:
    i = int(round(n))
    if 10 <= i % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(i % 10, "th")
    return f"{i}{suffix}"


def build_games_frame(
    live_df: pd.DataFrame, exp_df: pd.DataFrame, results_df: pd.DataFrame, known_mismatches: set[str] | None,
) -> pd.DataFrame:
    own_side = exp_df.groupby("game_id")["predicted_side"].first()
    own_prob = exp_df.groupby("game_id")["predicted_home_cover_prob"].first()
    is_approx = exp_df.groupby("game_id")["is_approximate"].first()
    clean_fwd = exp_df.groupby("game_id")["clean_forward"].first()
    repro_diff = exp_df.groupby("game_id")["reproduction_max_diff"].first()

    games = live_df.set_index("game_id").copy()
    games["explanation_predicted_side"] = own_side
    games["explanation_predicted_home_cover_prob"] = own_prob
    games["is_approximate"] = is_approx
    games["clean_forward"] = clean_fwd
    games["reproduction_max_diff"] = repro_diff
    games["side_mismatch"] = games["explanation_predicted_side"] != games["live_predicted_side"]

    results = results_df.set_index("game_id")
    games["closing_spread"] = results["closing_spread"]
    # Favourite/underdog and key-number sections use the CLOSING line, not the
    # line at pick time (PROMPT-FIX-SPREAD-SIGN-AND-LINE-SNAPSHOTS.md Part A.4)
    # — the two can differ (line moves between pick generation and kickoff).
    games["favorite"] = games["closing_spread"].apply(favorite_or_underdog)
    games["picked_is_favorite"] = games["favorite"] == games["live_predicted_side"]
    games["near_key_number"] = games["closing_spread"].apply(near_key_number)
    games["market_disagreement"] = (games["live_predicted_home_cover_prob"] - 0.5).abs()

    scores = results[["home_score", "away_score"]]
    games["played"] = games.index.map(
        lambda gid: bool(pd.notna(scores.at[gid, "home_score"]) and pd.notna(scores.at[gid, "away_score"]))
        if gid in scores.index else False
    )
    games["is_push"] = games["played"] & games["actual_home_covered"].isna()

    if known_mismatches is not None:
        actual = set(games.index[games["side_mismatch"]])
        if actual != known_mismatches:
            logger.warning(
                "Side-mismatch set differs from the recorded one — recorded=%s actual=%s. "
                "New information, not necessarily a defect, but check before trusting "
                "the 'toward the pick' statistics.",
                sorted(known_mismatches), sorted(actual),
            )
    return games.reset_index()


def game_section_markdown(
    game: pd.Series, exp_df: pd.DataFrame, mismatched_ids: set[str],
) -> tuple[str, pd.DataFrame]:
    gid = game["game_id"]
    top = top_drivers(exp_df, gid, n=5)
    shares = family_shares(exp_df, gid)
    flagged = imputed_and_weather_rows(exp_df, gid)
    interaction_note = "Not stored: this run computes per-feature contributions only, no feature-interaction pairs."

    lines = [f"### {game['away_team']} @ {game['home_team']} (`{gid}`)", ""]

    flags = []
    if game["side_mismatch"]:
        flags.append(
            f"**SIDE MISMATCH** — the underlying (approximate) explanation model leans "
            f"{game['explanation_predicted_side'].upper()}; the live served pick is "
            f"{game['live_predicted_side'].upper()}. Excluded from every \"toward the pick\" aggregate below."
        )
    if game["clean_forward"] is False:
        flags.append("**Regenerated after kickoff** (`clean_forward=false`) — not a clean forward pick.")
    if game["is_approximate"]:
        flags.append(
            f"Approximate explanation (reproduction_max_diff={_fmt(game['reproduction_max_diff'], '.4f')})."
        )
    for f in flags:
        lines.append(f"- {f}")
    if flags:
        lines.append("")

    fav = game["favorite"]
    fav_txt = {"home": game["home_team"], "away": game["away_team"], "pickem": "pick'em"}.get(fav, "n/a")
    if not game["played"]:
        result_txt = "not yet played"
    elif game["is_push"]:
        result_txt = "push"
    else:
        result_txt = str(bool(game["actual_home_covered"]))
    lines += [
        f"- Line at pick time (home perspective): {_fmt(game['pick_time_spread'], '+.1f')} · "
        f"Closing line: {_fmt(game['closing_spread'], '+.1f')} — favourite (by closing line): {fav_txt}",
        f"- Live pick: {game['live_predicted_side']} ({game['home_team'] if game['live_predicted_side']=='home' else game['away_team']}), "
        f"P(home cover) = {_fmt(game['live_predicted_home_cover_prob'], '.3f')}",
        f"- Result: home_covered={result_txt}, correct={game['correct'] if pd.notna(game['correct']) else 'n/a'}",
        "",
        "**Top 5 drivers (toward the live pick):**",
        "",
        "| Family | Feature | Side | Raw value | League pctile | Contribution |",
        "|---|---|---|---|---|---|",
    ]
    for _, r in top.iterrows():
        lines.append(
            f"| {r['family']} | {r['feature']} | {r['side']} | {_fmt(r['raw_value'], '.3f')} | "
            f"{_fmt(r['league_pctile'], '.1f')} | {_fmt(r['pick_direction_live'])} |"
        )
    lines.append("")

    mv = matchup_view(exp_df[exp_df["game_id"] == gid])
    lines += ["**Family matchup (home-cover-oriented, not pick-direction):**", "", "| Family | Home | Away | Net |", "|---|---|---|---|"]
    for _, r in mv.sort_values("family").iterrows():
        lines.append(f"| {r['family']} | {_fmt(r['home_contribution'])} | {_fmt(r['away_contribution'])} | {_fmt(r['net'])} |")
    lines.append("")

    top1_share = shares.iloc[0]["share"] if len(shares) else float("nan")
    top3_share = shares.head(3)["share"].sum() if len(shares) else float("nan")
    lines.append(
        f"- Top 1 family carries {top1_share:.0%} of total |contribution|; top 3 carry {top3_share:.0%}."
    )
    lines.append(f"- Strongest interaction pair: {interaction_note}")

    if not flagged.empty:
        lines.append("- Imputed / weather / roof_dome contributions (known-buggy, called out regardless of rank):")
        for _, r in flagged.iterrows():
            note = "imputed" if r["was_imputed"] else "weather family"
            lines.append(f"  - {r['feature']} ({note}): {_fmt(r['pick_direction_live'])} toward the pick")
    else:
        lines.append("- No imputed values or weather/roof_dome contributions in this game.")
    lines.append("")

    lines.append(plain_english_summary(game, top))
    lines.append("")

    return "\n".join(lines), top


def render_report(
    season: int, week: int, games: pd.DataFrame, exp_df: pd.DataFrame,
    approximate_note: bool, has_results: bool,
) -> tuple[str, dict[str, pd.DataFrame]]:
    mismatched_ids = set(games.loc[games["side_mismatch"], "game_id"])
    not_clean_ids = set(games.loc[games["clean_forward"] == False, "game_id"])  # noqa: E712

    parts: list[str] = [f"# Week analysis — {season} week {week}", ""]

    if approximate_note:
        parts.append(
            f"**Week {week}'s explanations are approximate** "
            f"(`is_approximate=true`, max diff {games['reproduction_max_diff'].max():.4f}). "
            "Every number below that says \"toward the pick\" is re-signed toward the LIVE served "
            "pick, not the underlying approximate model's own lean — see the side-mismatch flags."
        )
    else:
        parts.append(f"Week {week}'s explanations are exact reproductions of the live picks.")
    parts.append("")

    if mismatched_ids:
        parts.append(
            f"**{len(mismatched_ids)} game(s) disagree on side** between the underlying explanation "
            f"model and the live served pick: {', '.join(sorted(mismatched_ids))}. "
            "Flagged per-game below and excluded from every \"toward the pick\" aggregate statistic."
        )
    else:
        parts.append("No games disagree on side between the underlying explanation model and the live served pick.")
    parts.append("")

    if not_clean_ids:
        parts.append(
            f"**Regenerated after kickoff** (`clean_forward=false`): {', '.join(sorted(not_clean_ids))}."
        )
    else:
        parts.append("No games in this week were regenerated after kickoff.")
    parts.append("")

    if not has_results:
        parts.append(f"Week {week} has not finished playing — result columns are left empty by design.")
        parts.append("")

    # ── 1. Game by game ──────────────────────────────────────────────────
    parts.append("## 1. Game by game")
    parts.append("")
    drivers_rows = []
    for _, game in games.sort_values("game_id").iterrows():
        section, top = game_section_markdown(game, exp_df, mismatched_ids)
        parts.append(section)
        drivers_rows.append(top.copy())
    drivers_csv = pd.concat(drivers_rows, ignore_index=True)

    # ── 2. Patterns across the games ─────────────────────────────────────
    parts.append("## 2. Patterns across the games")
    parts.append("")
    push_stats = family_push_stats(exp_df, mismatched_ids)
    parts.append("**Mean |contribution| by family, and how often it pushed toward the picked side:**")
    parts.append("")
    parts.append("| Family | Mean |contribution| | Toward pick (all games) | Toward pick (excl. side-mismatches) |")
    parts.append("|---|---|---|---|")
    for _, r in push_stats.iterrows():
        parts.append(
            f"| {r['family']} | {_fmt(r['mean_abs_contribution_16'], '.4f')} | "
            f"{r['pushed_toward_pick_frac_16']:.0%} (n={int(r['n_games_16'])}) | "
            f"{r['pushed_toward_pick_frac_13']:.0%} (n={int(r['n_games_13'])}) |"
        )
    parts.append("")

    matrix = family_game_matrix(exp_df)
    clusters = cluster_games(matrix)
    parts.append("**Groups by pick-direction contribution vector (hierarchical, cosine distance, average linkage):**")
    parts.append("")
    for cluster_id, sub in clusters.groupby("cluster"):
        dom = ", ".join(sub.iloc[0]["dominant_families"])
        parts.append(f"- Group {cluster_id} — dominant: {dom} — games: {', '.join(sorted(sub['game_id']))}")
    parts.append("")

    shapes = top_driver_shapes(exp_df)
    shapes = shapes.merge(games[["game_id", "live_predicted_side", "correct"]], on="game_id", how="left")
    parts.append("**Recurring top-driver shapes (family + side of the #1 driver):**")
    parts.append("")
    shape_counts = shapes.groupby(["shape_family", "shape_side"]).size().reset_index(name="count").sort_values("count", ascending=False)
    for _, r in shape_counts.iterrows():
        sub = shapes[(shapes["shape_family"] == r["shape_family"]) & (shapes["shape_side"] == r["shape_side"])]
        game_list = ", ".join(f"{gid} ({side})" for gid, side in zip(sub["game_id"], sub["live_predicted_side"]))
        parts.append(f"- {r['shape_family']} ({r['shape_side']}) — {int(r['count'])} game(s): {game_list}")
    parts.append("")

    # ── 3. Against the market ────────────────────────────────────────────
    parts.append("## 3. Against the market")
    parts.append("")
    parts.append("**Model P(home cover) vs. closing spread, per game (sorted by disagreement with the market):**")
    parts.append("")
    parts.append("| Game | Line at pick time | Closing line | Favourite (closing) | Pick | P(home cover) | |P-0.5| |")
    parts.append("|---|---|---|---|---|---|---|")
    for _, g in games.sort_values("market_disagreement", ascending=False).iterrows():
        fav_txt = {"home": g["home_team"], "away": g["away_team"], "pickem": "pick'em"}.get(g["favorite"], "n/a")
        parts.append(
            f"| {g['game_id']} | {_fmt(g['pick_time_spread'], '+.1f')} | {_fmt(g['closing_spread'], '+.1f')} | "
            f"{fav_txt} | {g['live_predicted_side']} | "
            f"{_fmt(g['live_predicted_home_cover_prob'], '.3f')} | {_fmt(g['market_disagreement'], '.3f')} |"
        )
    parts.append("")

    top_disagree = games.sort_values("market_disagreement", ascending=False).head(3)
    parts.append("Families driving the largest market disagreements:")
    for _, g in top_disagree.iterrows():
        top1 = family_shares(exp_df, g["game_id"]).iloc[0]
        parts.append(
            f"- {g['game_id']} (|P-0.5|={g['market_disagreement']:.3f}): top family {top1['family']} "
            f"({top1['share']:.0%} of total |contribution|)"
        )
    parts.append("")

    dog_games = games[~games["picked_is_favorite"]]
    parts.append(f"**Underdog picks: {len(dog_games)} of {len(games)}.**")
    if len(dog_games):
        dog_mismatched = mismatched_ids & set(dog_games["game_id"])
        dog_push = family_push_stats(exp_df[exp_df["game_id"].isin(dog_games["game_id"])], dog_mismatched)
        parts.append("")
        parts.append("Families pushing toward the pick specifically on underdog picks:")
        parts.append("")
        parts.append("| Family | Toward pick (all underdog picks) | Toward pick (excl. mismatches) |")
        parts.append("|---|---|---|")
        for _, r in dog_push.iterrows():
            parts.append(
                f"| {r['family']} | {r['pushed_toward_pick_frac_16']:.0%} (n={int(r['n_games_16'])}) | "
                f"{r['pushed_toward_pick_frac_13']:.0%} (n={int(r['n_games_13'])}) |"
            )
    parts.append("")

    near3 = games[games["near_key_number"] == 3]
    near7 = games[games["near_key_number"] == 7]
    parts.append(
        f"**Around key numbers:** {len(near3)} game(s) within 0.5 of a 3-point spread "
        f"({', '.join(near3['game_id']) if len(near3) else 'none'}); "
        f"{len(near7)} game(s) within 0.5 of a 7-point spread "
        f"({', '.join(near7['game_id']) if len(near7) else 'none'})."
    )
    parts.append("")

    line_snap_note = games.attrs.get("line_snapshot_note", "")
    if line_snap_note:
        parts.append(line_snap_note)
        parts.append("")

    ml_note = games.attrs.get("moneyline_note", "")
    if ml_note:
        parts.append(ml_note)
        parts.append("")

    ml_table = games.attrs.get("moneyline_table")
    if ml_table is not None and not ml_table.empty:
        parts.append("| Game | Home devigged win prob (moneyline) | Model P(home cover) |")
        parts.append("|---|---|---|")
        for _, r in ml_table.iterrows():
            parts.append(
                f"| {r['game_id']} | {_fmt(r['home_devigged_prob'], '.3f')} | "
                f"{_fmt(r['live_predicted_home_cover_prob'], '.3f')} |"
            )
        parts.append(
            "Note: moneyline win probability and P(home cover) measure different things "
            "(straight-up win vs. ATS cover) — shown side by side, not equated."
        )
        parts.append("")

    agree_frac = games.attrs.get("favorite_agreement_frac")
    if agree_frac is not None:
        mismatches = games.attrs.get("favorite_agreement_mismatches")
        if mismatches is not None and not mismatches.empty:
            detail = "; ".join(
                f"{r['game_id']} (spread favours {r['favorite']}, moneyline favours {r['moneyline_favorite']})"
                for _, r in mismatches.iterrows()
            )
            parts.append(
                f"**Favourite check (closing spread vs. de-vigged moneyline): {agree_frac:.0%} agree.** "
                f"Disagreements: {detail}."
            )
        else:
            parts.append(
                f"**Favourite check (closing spread vs. de-vigged moneyline): {agree_frac:.0%} agree "
                "— no disagreements.**"
            )
        parts.append("")

    corr = spread_family_correlation(exp_df, games)
    parts.append("**Per-family correlation with the closing spread (home-cover-oriented, not pick-direction):**")
    parts.append("")
    parts.append("| Family | n games | corr with closing spread |")
    parts.append("|---|---|---|")
    for _, r in corr.iterrows():
        parts.append(f"| {r['family']} | {int(r['n_games'])} | {_fmt(r['corr_with_closing_spread'], '.3f')} |")
    parts.append("")

    # ── 4. Hand-off list ─────────────────────────────────────────────────
    parts.append("## 4. Hand-off list — testable on 2015-2025")
    parts.append("")
    hyps = build_hypotheses(push_stats, corr, shape_counts, dog_push if len(dog_games) else None, near3, near7)
    for i, h in enumerate(hyps, 1):
        parts.append(f"{i}. {h}")
    parts.append("")

    report = "\n".join(parts)
    csvs = {
        "drivers": drivers_csv,
        "family_push_stats": push_stats,
        "clusters": clusters,
        "family_spread_correlation": corr,
        "games": games,
    }
    return report, csvs


def build_hypotheses(
    push_stats: pd.DataFrame, corr: pd.DataFrame, shape_counts: pd.DataFrame,
    dog_push: pd.DataFrame | None, near3: pd.DataFrame, near7: pd.DataFrame,
) -> list[str]:
    hyps = []
    top_pushers = push_stats.sort_values("pushed_toward_pick_frac_13", ascending=False).head(2)
    for _, r in top_pushers.iterrows():
        hyps.append(
            f"Picks where {r['family']} is the top driver and it pushed toward the pick "
            f"(true in {r['pushed_toward_pick_frac_13']:.0%} of the {int(r['n_games_13'])} "
            "non-mismatched games) — test ATS performance on 2015-2025 for games where this "
            "family is the #1 driver."
        )
    most_market_like = corr.iloc[0]
    least_market_like = corr.iloc[-1]
    hyps.append(
        f"{most_market_like['family']} correlates most with the closing spread (r={most_market_like['corr_with_closing_spread']:.2f}) "
        "and is largely repeating the market — test whether excluding it from the feature set changes backtest log loss."
    )
    hyps.append(
        f"{least_market_like['family']} correlates least with the closing spread (r={least_market_like['corr_with_closing_spread']:.2f}) "
        "— test whether picks driven by this family beat the market ATS on 2015-2025, independent of the spread."
    )
    if dog_push is not None and len(dog_push):
        top_dog = dog_push.sort_values("pushed_toward_pick_frac_13", ascending=False).iloc[0]
        hyps.append(
            f"Picks where the model backs the underdog and {top_dog['family']} is the top driver — "
            "test ATS performance on 2015-2025 for underdog picks split by this family's direction."
        )
    if len(shape_counts):
        top_shape = shape_counts.iloc[0]
        hyps.append(
            f"Games whose #1 driver is {top_shape['shape_family']} on the {top_shape['shape_side']} side "
            f"({int(top_shape['count'])} of this week's games) — test whether this shape recurs and beats "
            "the market ATS on 2015-2025."
        )
    if len(near3) or len(near7):
        hyps.append(
            "Games within half a point of the 3 or 7 key numbers — test whether the model's calibration "
            "(P(cover) vs. actual cover rate) differs near these numbers on 2015-2025."
        )
    return hyps


# ── CLI ───────────────────────────────────────────────────────────────────────


def run(client: bigquery.Client, season: int, week: int) -> tuple[str, dict[str, pd.DataFrame]]:
    exp_df = fetch_explanations(client, season, week)
    n_games = exp_df["game_id"].nunique()
    if n_games < 16:
        raise SystemExit(
            f"STOP: only {n_games} game(s) have stored explanations for {season} week {week} "
            "(need 16). Write this to 00-PROJECT-LEAD/QUESTIONS.md and stop — see kill-switch in "
            "PROMPT-WEEK1-ANALYSIS.md."
        )

    recon = check_reconstruction(exp_df)
    failed = recon[~recon["passed"]]
    if not failed.empty:
        raise SystemExit(
            f"STOP: {len(failed)} game(s) don't reconstruct their stored probability within "
            f"{RECONSTRUCTION_TOLERANCE}: {failed['game_id'].tolist()}. Write this to "
            "00-PROJECT-LEAD/QUESTIONS.md and stop."
        )

    live_df = fetch_live_games(client, season, week)
    results_df = fetch_game_results(client, season, week)
    exp_resigned = resign_toward_live_pick(exp_df, live_df)

    known = KNOWN_SIDE_MISMATCHES.get((season, week))
    games = build_games_frame(live_df, exp_resigned, results_df, known)

    has_results = bool(games["played"].any())
    approximate = bool(games["is_approximate"].any())

    ml_pop = fetch_moneyline_population(client)
    pop_summary = ", ".join(
        f"{int(r['season'])}: {int(r['n_with_home_moneyline'])}/{int(r['n_games'])}" for _, r in ml_pop.iterrows()
    )
    ml_df = fetch_moneylines(client, season, week)
    ml_df = ml_df[ml_df["game_id"].isin(games["game_id"])]
    week_populated = len(ml_df) == len(games) and ml_df["home_moneyline"].notna().all() and ml_df["away_moneyline"].notna().all()
    if week_populated:
        ml_devig = devig_moneylines(ml_df)
        ml_table = ml_devig.merge(games[["game_id", "live_predicted_home_cover_prob"]], on="game_id", how="left")
        games.attrs["moneyline_table"] = ml_table
        games.attrs["moneyline_note"] = (
            f"Moneyline population by season — {pop_summary}. {season} week {week} is fully populated "
            "for this slate; de-vigged market probability shown below."
        )

        # Data-derived guard (PROMPT-FIX-SPREAD-SIGN-AND-LINE-SNAPSHOTS.md Part
        # A.3): the closing-spread favourite must agree with the de-vigged
        # moneyline favourite on at least 80% of games, or the sign convention
        # in this script is wrong again, not just a market quirk — stop and
        # write nothing rather than publish a report built on a flipped sign.
        agree_frac, mismatches = enforce_favorite_agreement(games, ml_table, season, week)
        games.attrs["favorite_agreement_frac"] = agree_frac
        games.attrs["favorite_agreement_mismatches"] = mismatches
    else:
        games.attrs["moneyline_note"] = (
            f"Moneyline population by season — {pop_summary}. {season} week {week} is not fully "
            "populated; moneyline comparison skipped."
        )

    snaps = fetch_line_snapshots(client, season, week)
    if snaps.empty:
        games.attrs["line_snapshot_note"] = (
            "Line movement: `raw_lines.line_snapshots` has no rows for this week "
            "(the scheduled pipeline has never executed this capture — see "
            "HANDOFF-2026-09-18-spread-sign-and-snapshots.md)."
        )
    elif (snaps["n_snapshots"] <= 1).all():
        games.attrs["line_snapshot_note"] = (
            f"Line movement: {snaps['first_seen_spread'].notna().sum()} of {len(games)} games have "
            "exactly ONE snapshot in `line_snapshots` — a one-time manual catch-up capture "
            f"(see HANDOFF-2026-09-18-spread-sign-and-snapshots.md), not a real change-log. "
            "\"First-seen\" and \"closing\" are the same single observation here; no actual line "
            "movement can be shown yet."
        )
    else:
        n_first_seen = snaps["first_seen_spread"].notna().sum()
        n_moved = (snaps["first_seen_spread"] != snaps["last_seen_spread"]).sum()
        games.attrs["line_snapshot_note"] = (
            f"Line movement: {n_first_seen} of {len(games)} games have a first-seen line in "
            f"`line_snapshots`, {n_moved} of which moved between first-seen and close. "
            "Snapshots only began 2026-09-09, so this is a lower bound, not full coverage."
        )

    report, csvs = render_report(season, week, games, exp_resigned, approximate, has_results)
    return report, csvs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--week", type=int, required=True)
    args = ap.parse_args()

    client = bigquery.Client(project=PROJECT)
    report, csvs = run(client, args.season, args.week)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"week_analysis_{args.season}_wk{args.week:02d}.md"
    report_path.write_text(report, encoding="utf-8")
    logger.info("Wrote %s", report_path)

    for name, df in csvs.items():
        csv_path = REPORTS_DIR / f"week_analysis_{args.season}_wk{args.week:02d}_{name}.csv"
        df.to_csv(csv_path, index=False)
        logger.info("Wrote %s", csv_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
