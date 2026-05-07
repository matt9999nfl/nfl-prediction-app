"""
Seam 1: DATA-PIPELINE → curated.*
Verifies that curated tables exist, have the expected schema, and pass basic
data quality checks. Does not verify correctness of values — only shape.
"""
import pytest
from google.cloud import bigquery

PROJECT = "nfl-model-471509"

EXPECTED_GAMES_COLUMNS = {
    "game_id": "STRING",
    "season": "INTEGER",
    "week": "INTEGER",
    "home_team": "STRING",
    "away_team": "STRING",
    "home_score": "INTEGER",
    "away_score": "INTEGER",
    "spread_line": "FLOAT",
    "home_covered": "BOOLEAN",
    "div_game": "BOOLEAN",
}


@pytest.mark.integration
def test_curated_games_schema(bq_client):
    """curated.games has all required columns with correct types."""
    table = bq_client.get_table(f"{PROJECT}.curated.games")
    schema = {f.name: f.field_type for f in table.schema}
    for col, expected_type in EXPECTED_GAMES_COLUMNS.items():
        assert col in schema, f"Missing column: {col}"
        assert schema[col] == expected_type, (
            f"Column {col}: expected type {expected_type}, got {schema[col]}"
        )


@pytest.mark.integration
def test_curated_games_season_coverage(bq_client):
    """curated.games has data from 2015 through at least 2023."""
    rows = list(bq_client.query(
        f"SELECT MIN(season) as min_s, MAX(season) as max_s "
        f"FROM `{PROJECT}.curated.games`"
    ).result())
    assert rows[0]["min_s"] <= 2015, "curated.games missing seasons before 2015"
    assert rows[0]["max_s"] >= 2023, "curated.games missing recent seasons"


@pytest.mark.integration
def test_curated_games_no_null_game_ids(bq_client):
    """game_id is never null in curated.games."""
    rows = list(bq_client.query(
        f"SELECT COUNT(*) as n FROM `{PROJECT}.curated.games` WHERE game_id IS NULL"
    ).result())
    assert rows[0]["n"] == 0, f"curated.games has {rows[0]['n']} null game_ids"


@pytest.mark.integration
def test_curated_games_spread_null_rate(bq_client):
    """spread_line null rate is under 5% for regular season games."""
    rows = list(bq_client.query(f"""
        SELECT
          COUNTIF(spread_line IS NULL) / COUNT(*) as null_rate
        FROM `{PROJECT}.curated.games`
        WHERE season >= 2015
    """).result())
    null_rate = rows[0]["null_rate"]
    assert null_rate < 0.05, (
        f"spread_line null rate is {null_rate:.1%} — "
        f"expected < 5% (validates closing-line data quality)"
    )


@pytest.mark.integration
def test_no_look_ahead_in_curated_games(bq_client):
    """
    For completed games, actual score cannot be null if home_covered is set.
    This is a proxy for checking that result fields are not being populated
    for future games.
    """
    rows = list(bq_client.query(f"""
        SELECT COUNT(*) as n
        FROM `{PROJECT}.curated.games`
        WHERE home_covered IS NOT NULL
          AND (home_score IS NULL OR away_score IS NULL)
    """).result())
    assert rows[0]["n"] == 0, (
        f"{rows[0]['n']} rows have home_covered set but no actual score — "
        "possible look-ahead contamination"
    )
