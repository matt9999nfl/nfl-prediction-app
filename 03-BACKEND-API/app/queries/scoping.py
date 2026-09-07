"""
BigQuery reads and writes for platform.scoping_sessions and platform.capability_gaps.

Tables created 2026-08-31 by 01-DATA-PIPELINE/scripts/migrate_phase6_scoping.py
(schema also in 00-PROJECT-LEAD/PHASE6_STAGE1_DDL.sql).

Writes use DML rather than streaming inserts: a scoping session is updated
repeatedly as answers arrive, and rows in the streaming buffer cannot be
UPDATEd.  Volume here is one row per conversation, so DML cost is irrelevant.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from google.cloud import bigquery

from app.config import settings

logger = logging.getLogger(__name__)

PROJECT = settings.bigquery_project
SESSIONS = f"{PROJECT}.platform.scoping_sessions"
GAPS = f"{PROJECT}.platform.capability_gaps"


def _run(client: bigquery.Client, query: str, params: list) -> list[dict[str, Any]]:
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    rows = list(client.query(query, job_config=job_config).result())
    return [dict(r) for r in rows]


def _parse_json(value: Any) -> Any:
    """BigQuery JSON columns come back as str on some client versions, dict on others."""
    if value is None or isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def _normalize(row: dict[str, Any]) -> dict[str, Any]:
    row["slot_answers"] = _parse_json(row.get("slot_answers")) or {}
    row["config"] = _parse_json(row.get("config"))
    for ts in ("created_at", "updated_at"):
        if row.get(ts) is not None:
            row[ts] = row[ts].isoformat()
    return row


# ── sessions ─────────────────────────────────────────────────────────────────


def create_session(client: bigquery.Client, session_id: str, hypothesis_text: str) -> None:
    _run(
        client,
        f"""
        INSERT INTO `{SESSIONS}`
          (session_id, hypothesis_text, slot_answers, config, config_hash,
           approved_hash, status, experiment_id, created_at, updated_at)
        VALUES
          (@session_id, @hypothesis_text, JSON '{{}}', NULL, NULL,
           NULL, 'scoping', NULL, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())
        """,
        [
            bigquery.ScalarQueryParameter("session_id", "STRING", session_id),
            bigquery.ScalarQueryParameter("hypothesis_text", "STRING", hypothesis_text),
        ],
    )


def get_session(client: bigquery.Client, session_id: str) -> Optional[dict[str, Any]]:
    rows = _run(
        client,
        f"""
        SELECT session_id, hypothesis_text, slot_answers, config, config_hash,
               approved_hash, status, experiment_id, created_at, updated_at
        FROM `{SESSIONS}` WHERE session_id = @session_id LIMIT 1
        """,
        [bigquery.ScalarQueryParameter("session_id", "STRING", session_id)],
    )
    return _normalize(rows[0]) if rows else None


def update_answers(
    client: bigquery.Client,
    session_id: str,
    slot_answers: dict[str, Any],
    config: Optional[dict[str, Any]],
    config_hash: Optional[str],
    status: str,
) -> None:
    """
    Persist answers and, once complete, the assembled config and its hash.

    Writing config and hash together is deliberate — a stored hash that does not
    match the stored config would break the approval guarantee silently.
    """
    _run(
        client,
        f"""
        UPDATE `{SESSIONS}`
        SET slot_answers = PARSE_JSON(@slot_answers),
            config       = CASE WHEN @config IS NULL THEN NULL ELSE PARSE_JSON(@config) END,
            config_hash  = @config_hash,
            status       = @status,
            updated_at   = CURRENT_TIMESTAMP()
        WHERE session_id = @session_id
        """,
        [
            bigquery.ScalarQueryParameter("session_id", "STRING", session_id),
            bigquery.ScalarQueryParameter("slot_answers", "STRING", json.dumps(slot_answers)),
            bigquery.ScalarQueryParameter(
                "config", "STRING", json.dumps(config) if config is not None else None
            ),
            bigquery.ScalarQueryParameter("config_hash", "STRING", config_hash),
            bigquery.ScalarQueryParameter("status", "STRING", status),
        ],
    )


def set_approved_hash(client: bigquery.Client, session_id: str, approved_hash: str) -> None:
    _run(
        client,
        f"""
        UPDATE `{SESSIONS}`
        SET approved_hash = @approved_hash, status = 'approved',
            updated_at = CURRENT_TIMESTAMP()
        WHERE session_id = @session_id
        """,
        [
            bigquery.ScalarQueryParameter("session_id", "STRING", session_id),
            bigquery.ScalarQueryParameter("approved_hash", "STRING", approved_hash),
        ],
    )


def mark_dispatched(client: bigquery.Client, session_id: str, experiment_id: str) -> None:
    _run(
        client,
        f"""
        UPDATE `{SESSIONS}`
        SET status = 'dispatched', experiment_id = @experiment_id,
            updated_at = CURRENT_TIMESTAMP()
        WHERE session_id = @session_id
        """,
        [
            bigquery.ScalarQueryParameter("session_id", "STRING", session_id),
            bigquery.ScalarQueryParameter("experiment_id", "STRING", experiment_id),
        ],
    )


# ── capability gaps ──────────────────────────────────────────────────────────


def insert_gap(
    client: bigquery.Client,
    gap_id: str,
    session_id: Optional[str],
    requested_concept: str,
    why_unavailable: str,
    nearest_expressible: Optional[str],
    suggested_definition: Optional[str],
) -> None:
    _run(
        client,
        f"""
        INSERT INTO `{GAPS}`
          (gap_id, session_id, requested_concept, why_unavailable,
           nearest_expressible, suggested_definition, status, created_at)
        VALUES
          (@gap_id, @session_id, @requested_concept, @why_unavailable,
           @nearest_expressible, @suggested_definition, 'open', CURRENT_TIMESTAMP())
        """,
        [
            bigquery.ScalarQueryParameter("gap_id", "STRING", gap_id),
            bigquery.ScalarQueryParameter("session_id", "STRING", session_id),
            bigquery.ScalarQueryParameter("requested_concept", "STRING", requested_concept),
            bigquery.ScalarQueryParameter("why_unavailable", "STRING", why_unavailable),
            bigquery.ScalarQueryParameter("nearest_expressible", "STRING", nearest_expressible),
            bigquery.ScalarQueryParameter("suggested_definition", "STRING", suggested_definition),
        ],
    )


def list_gaps(client: bigquery.Client, status: Optional[str] = None) -> list[dict[str, Any]]:
    where = "WHERE status = @status" if status else ""
    params = [bigquery.ScalarQueryParameter("status", "STRING", status)] if status else []
    rows = _run(
        client,
        f"""
        SELECT gap_id, session_id, requested_concept, why_unavailable,
               nearest_expressible, suggested_definition, status, created_at
        FROM `{GAPS}` {where} ORDER BY created_at DESC LIMIT 200
        """,
        params,
    )
    for r in rows:
        if r.get("created_at") is not None:
            r["created_at"] = r["created_at"].isoformat()
    return rows


# ── governor inputs ──────────────────────────────────────────────────────────


_ALLOWED_FILTER_OPS = {"eq": "=", "gte": ">=", "lte": "<=", "ne": "!="}


def slice_fraction(
    client: bigquery.Client,
    start_season: int,
    end_season: int,
    game_universe: Optional[dict[str, Any]],
) -> Optional[float]:
    """
    The REAL proportion of regular-season games surviving the game-universe
    filter, counted from curated.games.

    Not an estimate. The governor's sample-size warning is only worth reading if
    the number behind it is the actual one.  Returns None when there is no
    filter (nothing is removed) or when the count cannot be taken.

    The field name is validated against GameUniverseFilter's own allowed values
    and the operator against a fixed map, so nothing from the config reaches the
    SQL string uncontrolled.
    """
    if not game_universe:
        return None

    from app.schemas.experiments import GameUniverseFilter

    allowed_fields = set(GameUniverseFilter.model_fields["field"].annotation.__args__)
    field = game_universe.get("field")
    operator = game_universe.get("operator")
    if field not in allowed_fields or operator not in _ALLOWED_FILTER_OPS:
        logger.warning("Refusing to count slice for unrecognised filter %r", game_universe)
        return None

    sql_op = _ALLOWED_FILTER_OPS[operator]
    value = game_universe.get("value")
    param_type = "BOOL" if isinstance(value, bool) else "INT64"

    rows = _run(
        client,
        f"""
        SELECT
          COUNTIF({field} {sql_op} @value) AS matched,
          COUNT(*) AS total
        FROM `{PROJECT}.curated.games`
        WHERE season BETWEEN @start_season AND @end_season
        """,
        [
            bigquery.ScalarQueryParameter("value", param_type, value),
            bigquery.ScalarQueryParameter("start_season", "INT64", int(start_season)),
            bigquery.ScalarQueryParameter("end_season", "INT64", int(end_season)),
        ],
    )
    if not rows or not rows[0].get("total"):
        return None
    return float(rows[0]["matched"]) / float(rows[0]["total"])


def list_prior_configs(client: bigquery.Client, limit: int = 200) -> list[dict[str, Any]]:
    """
    Saved experiment configs, for the multiple-comparisons check.

    Shaped like an ExperimentCreateRequest so the governor compares like with
    like and does not need to know where they came from.
    """
    rows = _run(
        client,
        f"""
        SELECT target, features, methodology, model
        FROM `{PROJECT}.platform.experiment_configs`
        ORDER BY created_at DESC
        LIMIT {int(limit)}
        """,
        [],
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append({
            "target": row.get("target"),
            "features": _parse_json(row.get("features")) or [],
            "methodology": _parse_json(row.get("methodology")) or {},
            "model": _parse_json(row.get("model")) or {},
        })
    return out
