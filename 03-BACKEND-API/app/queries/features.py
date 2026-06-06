"""
Features query layer.

GET /api/v1/features returns the union of:
  1. A hardcoded nflfastR-derived feature catalog (see BACKEND_API_SPEC_PHASE2.md)
  2. Columns from user-uploaded datasets (platform.dataset_columns) where the
     parent dataset has status = 'ready'

Deprecated features (BUG-002):
  Features are tombstoned (soft-deprecated) rather than deleted. Deprecated
  entries live in _DEPRECATED_CATALOG with deprecated=True.  The default
  list_features() call excludes them; pass include_deprecated=True to get them.
  This preserves interpretability of historical experiments that referenced
  features before they were removed from the active catalog.

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

# Deprecation reason used for all BUG-002 tombstoned features.
_DEPRECATION_REASON = "Feature removed from curated catalog during v2 rebuild"


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

# ── Deprecated features (tombstoned — BUG-002) ────────────────────────────────
#
# These features existed in experiments created before the v2 catalog rebuild.
# They are kept here so that:
#   1. Historical experiments remain interpretable (we know what the feature was).
#   2. The deprecated_features field on experiment detail can return the reason.
#   3. They are NOT returned by list_features() by default (include_deprecated=False).
#
# Column names used here are the exact strings stored in experiment_configs.features[].column.
# Both non-prefixed (old-schema) and prefixed variants are registered where they differ.
_DEPRECATED_FEATURES_RAW: list[tuple[str, str, str]] = [
    # (column_name, description, deprecated_reason)
    ("def_qb_hit_rate",
     "QB hits generated per opponent pass attempt (non-prefixed, deprecated)",
     _DEPRECATION_REASON),
    ("def_rush_yards_allowed_per_att",
     "Rush yards allowed per opponent rush attempt (non-prefixed, deprecated)",
     _DEPRECATION_REASON),
    # The experiments also reference several other non-prefixed features
    # (ol_sack_rate, def_sack_rate, etc.) that are not present in the current
    # home_/away_-prefixed catalog.  Tombstone them all for full audit coverage.
    ("ol_sack_rate",
     "Sacks allowed per pass attempt, non-prefixed (deprecated — use home_ol_sack_rate / away_ol_sack_rate)",
     _DEPRECATION_REASON),
    ("ol_qb_hit_rate",
     "QB hits allowed per pass attempt, non-prefixed (deprecated)",
     _DEPRECATION_REASON),
    ("ol_pressure_proxy_rate",
     "(Sacks + QB hits) per pass attempt, non-prefixed (deprecated)",
     _DEPRECATION_REASON),
    ("ol_pass_epa_per_att",
     "Mean EPA per pass attempt, non-prefixed (deprecated)",
     _DEPRECATION_REASON),
    ("ol_rush_epa_per_att",
     "Mean EPA per rush attempt, non-prefixed (deprecated)",
     _DEPRECATION_REASON),
    ("ol_rush_yards_per_att",
     "Mean rush yards per attempt, non-prefixed (deprecated)",
     _DEPRECATION_REASON),
    ("def_sack_rate",
     "Sacks generated per opponent pass attempt, non-prefixed (deprecated)",
     _DEPRECATION_REASON),
    ("def_pressure_proxy_rate",
     "(Sacks + QB hits generated) per opponent pass attempt, non-prefixed (deprecated)",
     _DEPRECATION_REASON),
    ("def_pass_epa_allowed_per_att",
     "Mean EPA allowed per pass attempt, non-prefixed (deprecated)",
     _DEPRECATION_REASON),
    ("def_rush_epa_allowed_per_att",
     "Mean EPA allowed per rush attempt, non-prefixed (deprecated)",
     _DEPRECATION_REASON),
    ("def_epa_per_play",
     "Mean EPA allowed per play, non-prefixed (deprecated)",
     _DEPRECATION_REASON),
    ("def_explosive_pass_allowed_rate",
     "% of opponent pass plays allowing 20+ yards, non-prefixed (deprecated)",
     _DEPRECATION_REASON),
    ("def_explosive_rush_allowed_rate",
     "% of opponent rush plays allowing 10+ yards, non-prefixed (deprecated)",
     _DEPRECATION_REASON),
    ("qb_cpoe",
     "Mean completion % over expected, non-prefixed (deprecated)",
     _DEPRECATION_REASON),
    ("qb_epa_under_pressure",
     "Mean EPA on pressured dropbacks, non-prefixed (deprecated)",
     _DEPRECATION_REASON),
    ("pass_explosive_rate",
     "% of pass plays gaining 20+ yards, non-prefixed (deprecated)",
     _DEPRECATION_REASON),
    ("rush_explosive_rate",
     "% of rush plays gaining 10+ yards, non-prefixed (deprecated)",
     _DEPRECATION_REASON),
    ("rolling_3wk_epa_trend",
     "Mean team EPA per play over last 3 games, non-prefixed (deprecated)",
     _DEPRECATION_REASON),
    ("rest_days",
     "Days since last game, non-prefixed (deprecated)",
     _DEPRECATION_REASON),
    ("prior_week_margin",
     "Score margin in most recent game, non-prefixed (deprecated)",
     _DEPRECATION_REASON),
    ("season_win_pct",
     "Season-to-date win percentage, non-prefixed (deprecated)",
     _DEPRECATION_REASON),
]

# Set of deprecated column names for fast O(1) lookup.
_DEPRECATED_COLUMN_NAMES: frozenset[str] = frozenset(
    col for col, _, _ in _DEPRECATED_FEATURES_RAW
)

# Map from column name → deprecated_reason for experiment detail enrichment.
DEPRECATED_COLUMN_REASON: dict[str, str] = {
    col: reason for col, _, reason in _DEPRECATED_FEATURES_RAW
}


def _build_deprecated_catalog() -> list[dict[str, Any]]:
    """Build tombstoned catalog entries for deprecated features."""
    catalog: list[dict[str, Any]] = []
    for col, desc, reason in _DEPRECATED_FEATURES_RAW:
        catalog.append({
            "feature_id":         f"curated.{col}",
            "semantic_name":      col,
            "description":        desc,
            "dataset":            "curated",
            "data_type":          "numeric",
            "join_key_type":      "game_id",
            "license_tag":        "open",
            "deprecated":         True,
            "deprecated_reason":  reason,
        })
    return catalog


def _build_catalog() -> list[dict[str, Any]]:
    """Construct the full hardcoded nflfastR active feature catalog."""
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
                "deprecated":    False,
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
            "deprecated":    False,
        })

    return catalog


_CATALOG: list[dict[str, Any]] = _build_catalog()
_DEPRECATED_CATALOG: list[dict[str, Any]] = _build_deprecated_catalog()


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
    include_deprecated: bool = False,
) -> list[dict[str, Any]]:
    """
    Return all features (hardcoded catalog + user dataset columns),
    optionally filtered by dataset, data_type, or join_key_type.

    By default deprecated features are excluded (include_deprecated=False).
    Pass include_deprecated=True to retrieve tombstoned features with their
    deprecation metadata — useful for admin/debug views.
    """
    # Build the combined list (active catalog only by default)
    all_features = list(_CATALOG)
    if include_deprecated:
        all_features.extend(_DEPRECATED_CATALOG)
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


def get_deprecated_features_for_experiment(
    feature_refs: list[dict[str, Any]],
) -> list[dict[str, str | None]]:
    """
    Given a list of feature reference dicts from an experiment config
    (each with at least {"dataset": str, "column": str}), return a list
    of {name, deprecated_reason} dicts for any features that are deprecated.

    This is a pure in-memory lookup — no BigQuery round-trip needed.
    """
    result: list[dict[str, str | None]] = []
    for ref in feature_refs:
        col = ref.get("column", "")
        dataset = ref.get("dataset", "")
        if dataset == "curated" and col in _DEPRECATED_COLUMN_NAMES:
            result.append({
                "name": col,
                "deprecated_reason": DEPRECATED_COLUMN_REASON.get(col),
            })
    return result
