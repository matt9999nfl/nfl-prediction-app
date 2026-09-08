"""
Fixtures for the Hypothesis Chat tests that touch NO storage.

WHY THIS DIRECTORY EXISTS
-------------------------
06-TESTING-QA/conftest.py declares an autouse `cleanup_test_rows` fixture that
depends on `bq_client`, so every test under this tree constructs a BigQuery
client at setup.  The tests in this directory deliberately touch no storage at
all — they are static analysis of the implementation, pure-function checks, and
read-only HTTPS reads of the deployed API — so requiring a BigQuery credential
to run them would make them unrunnable for no reason.

The two overrides below are ADDITIVE and scoped to this directory only.  They
do not weaken the root fixtures for any other test:

  * `bq_client` here FAILS LOUDLY if a test requests it.  It is not a stand-in.
    Nothing in this directory may reach storage, and this makes that structural
    rather than promised.
  * `cleanup_test_rows` here is a no-op, which is correct by construction: with
    no client there is nothing to clean up.

The live-storage suite is `integration/test_hypothesis_chat.py` and it uses the
ROOT fixtures unchanged.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

import pytest

DEPLOYED_BASE_URL = os.getenv(
    "DEPLOYED_API_BASE_URL", "https://nfl-backend-api-rmaehdhzhq-uc.a.run.app"
)

def _find_backend_root() -> Path:
    """
    Locate 03-BACKEND-API without hardcoding a repo layout.

    NFL_BACKEND_ROOT wins if set; otherwise walk up from this file looking for
    a sibling 03-BACKEND-API. Explicit override matters because this suite is
    sometimes run from a workspace where 06-TESTING-QA is mounted on its own.
    """
    override = os.getenv("NFL_BACKEND_ROOT")
    if override:
        return Path(override).resolve()
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "03-BACKEND-API"
        if (candidate / "app" / "scoping").is_dir():
            return candidate
    return here.parents[2] / "03-BACKEND-API"


BACKEND_ROOT = _find_backend_root()
SCOPING_PKG = BACKEND_ROOT / "app" / "scoping"


@pytest.fixture(scope="session")
def bq_client():
    """Override: no test in this directory may touch BigQuery."""
    pytest.fail(
        "A test under scoping_hc/ requested bq_client. This directory is for "
        "tests that touch no storage; live-storage coverage belongs in "
        "integration/test_hypothesis_chat.py against the root fixtures."
    )


@pytest.fixture(autouse=True)
def cleanup_test_rows():
    """Override: nothing here writes, so there is nothing to clean up."""
    yield


@pytest.fixture(scope="session")
def backend_root() -> Path:
    if not SCOPING_PKG.is_dir():
        pytest.skip(f"backend source not found at {SCOPING_PKG}")
    return BACKEND_ROOT


@pytest.fixture(scope="session")
def scoping_src(backend_root: Path) -> dict[str, str]:
    """{filename: source text} for every module under app/scoping/."""
    return {
        p.name: p.read_text(encoding="utf-8")
        for p in sorted((backend_root / "app" / "scoping").glob("*.py"))
    }


@pytest.fixture(scope="session")
def scoping_api(backend_root: Path):
    """
    The pure layer, imported directly.

    app/scoping/* imports only stdlib + pydantic + its own siblings, so this
    works without fastapi, google-cloud-bigquery, or any credential. If that
    ever stops being true, this fixture fails and that IS the finding.
    """
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))
    try:
        from app.scoping import assemble, governor, hashing, render, schema
        from app.scoping import session as session_mod
    except Exception as exc:  # pragma: no cover - the failure is the point
        pytest.fail(
            "app/scoping/ could not be imported without fastapi/bigquery "
            f"installed, which means the pure layer is no longer pure: {exc!r}"
        )
    return {
        "assemble": assemble,
        "governor": governor,
        "hashing": hashing,
        "render": render,
        "schema": schema,
        "session": session_mod,
    }


def _get_json(url: str, timeout: int = 40):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.load(resp)


@pytest.fixture(scope="session")
def live_catalog() -> list[dict]:
    """
    The REAL feature catalog from the deployed revision. Read-only.

    Requirement C says render purity must be proven against configs built from
    the live catalog, not fixture configs. This is that catalog.
    """
    try:
        payload = _get_json(f"{DEPLOYED_BASE_URL}/api/v1/features")
    except Exception as exc:
        pytest.skip(f"deployed API unreachable ({exc}); cannot use the live catalog")
    data = payload["data"] if isinstance(payload, dict) else payload
    if not data:
        pytest.fail("live feature catalog came back empty — that is itself a finding")
    return data


@pytest.fixture(scope="session")
def live_season_game_counts() -> dict[int, int]:
    """
    Games per season counted from curated.games via the deployed /api/v1/games
    endpoint, paged to exhaustion.

    This is the INDEPENDENT count requirement D demands. It does not use
    governor.evaluated_games, GAMES_PER_SEASON, or any other number the
    implementation produces.
    """
    counts: dict[int, int] = {}
    for season in range(2015, 2026):
        total = 0
        cursor = None
        while True:
            url = f"{DEPLOYED_BASE_URL}/api/v1/games?season={season}&limit=200"
            if cursor:
                url += f"&cursor={cursor}"
            try:
                page = _get_json(url)
            except Exception as exc:
                pytest.skip(f"deployed /api/v1/games unreachable ({exc})")
            total += len(page["data"])
            pagination = page.get("pagination") or {}
            if not pagination.get("has_more"):
                break
            cursor = pagination.get("next_cursor")
        if total == 0:
            pytest.skip(f"no games returned for season {season}")
        counts[season] = total
    return counts
