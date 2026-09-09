"""
Production-experiment selection for GET /api/v1/predictions.

These tests exercise `get_production_experiment` directly with a stub BigQuery
client, so they need no credentials and no network — unlike the router-level
tests in test_predictions.py, which construct a real client via the dependency
and fail with DefaultCredentialsError outside a GCP context.

What is being protected here is the DEC-C bargain: the endpoint MAY serve an
experiment that never cleared a success gate, and in exchange it must always
report which kind it served.  A regression that silently drops `gate_passed`,
or that lets an arbitrary experiment be served by query string, breaks that
bargain quietly — the failure mode is a confident-looking pick with no banner.
"""
from unittest.mock import patch

import pytest

from app.queries import predictions as pq


PRODUCTION_ID = "00000000-0000-4000-8000-00000000f0re"


class _StubResult:
    def __init__(self, rows):
        self._rows = rows

    def result(self):
        return iter(self._rows)


class StubClient:
    """Returns a queued response per query and records what it was asked."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.queries: list[str] = []
        self.params: list[list] = []

    def query(self, query, job_config=None):
        self.queries.append(query)
        self.params.append(list(job_config.query_parameters) if job_config else [])
        rows = self._responses.pop(0) if self._responses else []
        return _StubResult(rows)


def _row(experiment_id, gate_passed, name="exp"):
    return {
        "experiment_id": experiment_id,
        "run_id": "run-1",
        "completed_at": "2026-09-09T00:00:00Z",
        "experiment_name": name,
        "gate_passed": gate_passed,
    }


def _param_values(params):
    return {p.name: p.value for p in params}


# ── Auto-selection ────────────────────────────────────────────────────────────


def test_gate_passed_experiment_wins_when_one_exists():
    """A validated model must always outrank the ungated production fallback."""
    client = StubClient([[_row("gated-1", True, "validated")]])

    with patch.object(pq.settings, "production_experiment_id", PRODUCTION_ID):
        result = pq.get_production_experiment(client)

    assert result["experiment_id"] == "gated-1"
    assert result["gate_passed"] is True
    # Only the gated query ran — the fallback was never reached.
    assert len(client.queries) == 1


def test_falls_back_to_production_experiment_when_nothing_gate_passed():
    """The case that actually matters: no experiment has ever passed its gate."""
    client = StubClient([[], [_row(PRODUCTION_ID, False, "production-forward-v2")]])

    with patch.object(pq.settings, "production_experiment_id", PRODUCTION_ID):
        result = pq.get_production_experiment(client)

    assert result["experiment_id"] == PRODUCTION_ID
    assert result["gate_passed"] is False
    assert len(client.queries) == 2
    assert _param_values(client.params[1])["production_id"] == PRODUCTION_ID


def test_returns_none_when_ungated_serving_is_disabled():
    """Setting PRODUCTION_EXPERIMENT_ID='' restores strict Phase 3 behaviour."""
    client = StubClient([[]])

    with patch.object(pq.settings, "production_experiment_id", ""):
        result = pq.get_production_experiment(client)

    assert result is None
    assert len(client.queries) == 1, "must not run the fallback query when disabled"


def test_returns_none_when_production_experiment_has_no_run():
    """Configured but never run — nothing to serve, and no invented row."""
    client = StubClient([[], []])

    with patch.object(pq.settings, "production_experiment_id", PRODUCTION_ID):
        assert pq.get_production_experiment(client) is None


# ── Override ──────────────────────────────────────────────────────────────────


def test_override_is_constrained_to_gated_or_production():
    """
    The override must not be a way to serve any experiment at all.

    Without this the shuffled-label leakage test (a deliberately meaningless
    model, kept for the INC-001 record) could be served to the dashboard by
    editing a query string.
    """
    client = StubClient([[_row("some-id", False)]])

    with patch.object(pq.settings, "production_experiment_id", PRODUCTION_ID):
        pq.get_production_experiment(client, experiment_id_override="some-id")

    sql = client.queries[0]
    assert "r.gate_passed = true" in sql
    assert "@production_id" in sql
    values = _param_values(client.params[0])
    assert values["experiment_id"] == "some-id"
    assert values["production_id"] == PRODUCTION_ID


def test_override_returns_none_when_query_matches_nothing():
    client = StubClient([[]])

    with patch.object(pq.settings, "production_experiment_id", PRODUCTION_ID):
        assert pq.get_production_experiment(client, experiment_id_override="nope") is None


# ── The response contract ─────────────────────────────────────────────────────


def test_every_selection_path_reports_gate_passed():
    """
    `gate_passed` is what the UI keys the evaluation banner off.  If any path can
    return a row without it, the banner can be dropped silently — so assert it is
    present on all of them rather than only on the one under test.
    """
    with patch.object(pq.settings, "production_experiment_id", PRODUCTION_ID):
        gated = pq.get_production_experiment(StubClient([[_row("g", True)]]))
        fallback = pq.get_production_experiment(
            StubClient([[], [_row(PRODUCTION_ID, False)]])
        )
        override = pq.get_production_experiment(
            StubClient([[_row(PRODUCTION_ID, False)]]),
            experiment_id_override=PRODUCTION_ID,
        )

    for result in (gated, fallback, override):
        assert "gate_passed" in result


def test_response_model_requires_gate_passed():
    """
    A missing gate_passed must be a loud error, not a default.

    ProductionPredictionsResponse deliberately gives the field no default: a
    default of False would be safe today and forgotten tomorrow.
    """
    from pydantic import ValidationError

    from app.schemas.experiments import ProductionPredictionsResponse

    fields = dict(
        experiment_id="e", experiment_name="n", season=2026, week=1,
        generated_at="2026-09-09T00:00:00Z", data=[],
    )
    with pytest.raises(ValidationError):
        ProductionPredictionsResponse(**fields)

    ok = ProductionPredictionsResponse(**fields, gate_passed=False)
    assert ok.gate_passed is False
