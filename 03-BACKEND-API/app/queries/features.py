"""
Features query layer.

GET /api/v1/features returns the union of:
  1. A hardcoded nflfastR-derived feature catalog (see BACKEND_API_SPEC_PHASE2.md)
  2. Columns from user-uploaded datasets (platform.dataset_columns) where the
     parent dataset has status = 'ready'

NOTE — Ambiguity flagged for PROJECT-LEAD:
  The spec says "platform.dataset_columns WHERE status = 'ready'" but
  `status` is a field on `platform.datasets`, not `platform.dataset_columns`.
  We join through platform.datasets on dataset_id and filter by datasets.status = 'ready'.
  Confirm the intended column location before the table is heavily populated.
"""
from typing import Any

from google.cloud import bigquery

from app.config import settings

PROJECT = settings.bigquery_project


# ── Hardcoded nflfastR catalog ────────────────────────────────────────────────

_PER_TEAM_FEATURES: list[tuple[str, str]] = [
    # (base_name, description)
    ("ol_sack_rate",                    "Sacks allowed per pass attempt, season-to-date"),
    ("ol_qb_hit_rate",                  "QB hits allowed per pass attempt, season-to-date"),
    ("ol_pressure_proxy_rate",          "(Sacks + QB hits) per pass attempt, season-to-date"),
    ("ol_pass_epa_per_att",             "Mean EPA per pass attempt, season-to-date"),
    ("ol_rush_epa_per_att",             "Mean EPA per rush attempt, season-to-date"),
    ("ol_rush_yards_per_att",           "Mean rush yards per attempt, season-to-date"),
    ("qb_epa_per_dropback",             "Mean EPA per dropback, season-to-date"),
    ("qb_cpoe",                         "Mean completion % over expected, season-to-date"),
    ("qb_epa_under_pressure",           "Mean EPA on pressured dropbacks, season-to-date"),
    ("pass_explosive_rate",             "% of pass plays gaining 20+ yards"),
    ("rush_explosive_rate",             "% of rush plays gaining 10+ yards"),
    ("def_epa_per_play",                "Mean EPA allowed per play, season-to-date"),
    ("def_pass_epa_allowed_per_att",    "Mean EPA allowed per pass attempt"),
    ("def_rush_epa_allowed_per_att",    "Mean EPA allowed per rush attempt"),
    ("def_pressure_proxy_rate",         "(Sacks + QB hits generated) per opponent pass attempt"),
    ("def_sack_rate",                   "Sacks generated per opponent pass attempt"),
    ("def_explosive_pass_allowed_rate", "% of opponent pass plays allowing 20+ yards"),
    ("def_explosive_rush_allowed_rate", "% of opponent rush plays allowing 10+ yards"),
    ("rest_days",                       "Days since last game"),
    ("prior_week_margin",               "Score margin in most recent game"),
    ("rolling_3wk_epa_trend",           "Mean team EPA per play over last 3 games"),
    ("season_win_pct",                  "Season-to-date win percentage"),
]

_GAME_CONTEXT_FEATURES: list[tuple[str, str]] = [
    ("rest_differential",   "home_rest_days minus away_rest_days"),
    ("div_game",            "Divisional matchup flag"),
    ("roof_dome",           "1 if dome or retractable-closed"),
    ("temp",                "Game-time temperature (°F)"),
    ("wind",                "Wind speed (mph)"),
]


def _build_catalog() -> list[dict[str, Any]]:
    """Construct the full hardcoded nflfastR feature catalog."""
    catalog: list[dict[str, Any]] = []

    for side in ("home", "away"):
        for base, desc in _PER_TEAM_FEATURES:
            name = f"{side}_{base}"
            catalog.append({
                "feature_id":    f"curated.{name}",
                "semantic_name": name,
                "description":   f"{'Home' if side == 'home' else 'Away'} team — {desc}",
                "dataset":       "curated",
                "data_type":     "numeric",
                "join_key_type": "game_id",
                "license_tag":   "open",
            })

    for base, desc in _GAME_CONTEXT_FEATURES:
        catalog.append({
            "feature_id":    f"curated.{base}",
            "semantic_name": base,
            "description":   desc,
            "dataset":       "curated",
            "data_type":     "numeric",
            "join_key_type": "game_id",
            "license_tag":   "open",
        })

    return catalog


_CATALOG: list[dict[str, Any]] = _build_catalog()


# ── User dataset columns from BigQuery ────────────────────────────────────────


def _run_query(
    client: bigquery.Client,
    query: str,
    params: list[bigquery.ScalarQueryParameter],
) -> list[dict[str, Any]]:
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    rows = list(client.query(query, job_config=job_config).result())
    return [dict(row) for row in rows]


def get_user_dataset_features(client: bigquery.Client) -> list[dict[str, Any]]:
    """
    Fetch ready user-dataset columns from platform.dataset_columns
    joined with platform.datasets where status = 'ready'.
    """
    query = f"""
        SELECT
            dc.dataset_id,
            dc.column_name,
            dc.semantic_name,
            dc.description,
            dc.data_type,
            dc.is_join_key,
            dc.null_rate,
            d.join_key_type,
            COALESCE(d.license_tag, 'open') AS license_tag
        FROM `{PROJECT}.platform.dataset_columns` dc
        JOIN `{PROJECT}.platform.datasets` d
          ON dc.dataset_id = d.dataset_id
        WHERE d.status = 'ready'
          AND dc.is_join_key = FALSE
        ORDER BY dc.dataset_id, dc.column_name
    """
    rows = _run_query(client, query, [])
    features: list[dict[str, Any]] = []
    for r in rows:
        dataset_ref = f"user_datasets.{r['dataset_id']}"
        features.append({
            "feature_id":    f"{dataset_ref}.{r['column_name']}",
            "semantic_name": r["semantic_name"] or r["column_name"],
            "description":   r["description"] or "",
            "dataset":       dataset_ref,
            "data_type":     r["data_type"] or "numeric",
            "join_key_type": r["join_key_type"] or "game_id",
            "license_tag":   r["license_tag"],
        })
    return features


# ── Public entry point ────────────────────────────────────────────────────────


def list_features(
    client: bigquery.Client,
    dataset: str | None = None,
    data_type: str | None = None,
    join_key_type: str | None = None,
) -> list[dict[str, Any]]:
    """
    Return all features (hardcoded catalog + user dataset columns),
    optionally filtered by dataset, data_type, or join_key_type.
    """
    # Build the combined list
    all_features = list(_CATALOG)
    try:
        all_features.extend(get_user_dataset_features(client))
    except Exception:
        # If the platform tables don't exist yet, return the catalog only.
        pass

    # Apply optional filters
    if dataset is not None:
        all_features = [f for f in all_features if f["dataset"] == dataset]
    if data_type is not None:
        all_features = [f for f in all_features if f["data_type"] == data_type]
    if join_key_type is not None:
        all_features = [f for f in all_features if f["join_key_type"] == join_key_type]

    return all_features
