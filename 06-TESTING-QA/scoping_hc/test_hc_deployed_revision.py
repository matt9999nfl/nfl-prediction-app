"""
The DEPLOYED revision, read-only.

HC-S6 acceptance: "At least one test runs against the DEPLOYED revision, not
only a local backend." Revision nfl-backend-api-00024-kw7 went live on
2026-09-08 as a side effect of an unrelated deploy, so the scoping router is in
production ahead of this gate. The live service is the thing that can actually
hurt, so it is checked directly.

Every request here is a GET. The write endpoints are probed only for their
AUTH behaviour, using a session id that does not exist, so no row is created,
updated or deleted in the live project by this module.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from .conftest import DEPLOYED_BASE_URL

pytestmark = [pytest.mark.integration, pytest.mark.live]

NONEXISTENT_SESSION = "00000000-0000-0000-0000-000000000000"


def _request(path: str, method: str = "GET", body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{DEPLOYED_BASE_URL}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, {"raw": raw[:400].decode(errors="replace")}
    except Exception as exc:
        pytest.skip(f"deployed API unreachable: {exc}")


def test_the_deployed_revision_answers_at_all():
    status, payload = _request("/health")
    assert status == 200
    assert payload["status"] == "ok"


def test_the_deployed_revision_still_cannot_say_which_code_is_running():
    """
    Not a new finding — PHASE6_STATUS.md records it as a DEVOPS item from the
    same 2026-09-08 deploy. Asserted here so that fixing it turns this test red
    and someone deletes it deliberately, rather than the signal quietly
    returning and nobody noticing either way.
    """
    _, payload = _request("/health")
    assert payload.get("commit") == "unknown", (
        "commit SHA is being reported again — the observability regression "
        "recorded in PHASE6_STATUS.md looks fixed; remove this test."
    )


def test_the_scoping_read_path_works_against_the_real_platform_tables():
    """
    The first live evidence that scoping's BigQuery read path works against
    real platform.* tables, which the S5 in-memory stand-in could not give.
    """
    status, payload = _request("/api/v1/scoping/capability-gaps")
    assert status == 200
    assert isinstance(payload.get("data"), list)


def test_the_only_live_evidence_for_capability_gaps_is_an_empty_table(capsys):
    """
    The endpoint returns 200 because there is nothing in the table.

    This is the shape the brief warns about: healthy on the first (and only)
    case, untested on the case that will actually occur. It is recorded as an
    explicit gap rather than counted as coverage. The row shape that WILL
    appear is checked against the response model in
    test_hc_gap_row_shapes.py, which does not need the table to be populated.
    """
    _, payload = _request("/api/v1/scoping/capability-gaps")
    rows = payload["data"]
    if rows:
        pytest.skip(
            "capability_gaps now has rows — re-run and assert against them "
            "instead of relying on the shape test"
        )
    assert rows == []


def test_every_scoping_write_endpoint_refuses_an_anonymous_caller():
    """
    Why the live write path is not exercised by this suite: OWNER_API_KEY is
    configured on the deployed revision, so every write returns 401.

    That is the right answer and it is asserted rather than assumed — an
    unauthenticated production dispatch endpoint would be a serious finding,
    and this is the test that would surface it.
    """
    sixty_four = "a" * 64
    probes = [
        ("POST", "/api/v1/scoping/sessions", {"hypothesis_text": "auth probe"}),
        ("POST", f"/api/v1/scoping/sessions/{NONEXISTENT_SESSION}/answers",
         {"slot_id": "target", "value": "ats_cover"}),
        ("POST", f"/api/v1/scoping/sessions/{NONEXISTENT_SESSION}/approve",
         {"config_hash": sixty_four}),
        ("POST", f"/api/v1/scoping/sessions/{NONEXISTENT_SESSION}/dispatch", {}),
        ("POST", f"/api/v1/scoping/sessions/{NONEXISTENT_SESSION}/extract", {}),
    ]
    for method, path, body in probes:
        status, payload = _request(path, method=method, body=body)
        assert status == 401, (
            f"{method} {path} returned {status}, not 401. An anonymous caller "
            f"can reach a scoping write endpoint in production. Body: {payload}"
        )


def test_the_scoping_read_endpoints_are_open_to_anonymous_callers():
    """
    Recorded, not asserted as desirable.

    Reads carry no API key by project convention (the same convention the
    public predictions endpoint relies on), so anyone who learns a session id
    can read its hypothesis text, answers and config, and anyone at all can
    list the capability gaps. Single-user by ADR-012, public URL in practice.
    Raised for PROJECT-LEAD to rule on rather than treated as a defect here.
    """
    status, _ = _request("/api/v1/scoping/capability-gaps")
    assert status == 200, "reads now require a key — this observation is stale"

    status, _ = _request(f"/api/v1/scoping/sessions/{NONEXISTENT_SESSION}")
    assert status == 404, (
        f"expected 404 for an unknown session read, got {status}; if this is "
        "401 the read surface has been closed and this test should be removed"
    )


# ── regression guard on the archetype the brief describes ────────────────────


@pytest.mark.parametrize("season", list(range(2015, 2026)))
def test_every_historical_season_still_serves_its_games(season):
    """
    The worked example from the brief: GET /api/v1/games 500'd for every season
    with completed games because the SQL emitted 'complete' while Game.status
    is Literal["scheduled", "final"]. It looked healthy because the list sorts
    season DESC and the first page was unplayed 2026 fixtures.

    The fix is in this revision. This is the guard that would have caught it:
    every season, not the first page.
    """
    status, payload = _request(f"/api/v1/games?season={season}&limit=5")
    assert status == 200, f"season {season} returns {status}: {payload}"
    rows = payload["data"]
    assert rows, f"season {season} returned no games"
    assert any(row.get("home_score") is not None for row in rows), (
        f"season {season} returned no completed games — the case that used to 500"
    )
    assert {row["status"] for row in rows} <= {"scheduled", "final"}
