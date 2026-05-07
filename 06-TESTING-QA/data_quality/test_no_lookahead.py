"""
Data quality: verify no look-ahead leakage in feature construction.
Features must be computed only from data available before the game starts.
"""
import pytest
from google.cloud import bigquery

PROJECT = "nfl-model-471509"


@pytest.mark.integration
def test_no_same_week_features_in_curated_plays(bq_client):
    """
    curated.plays should not contain same-week stat totals for a game
    that appear as season-to-date features for that same game.
    This is a schema-level check — actual leakage is caught in MODELING unit tests.
    """
    # Verify that curated.plays has a game_date or week column we can reason about
    table = bq_client.get_table(f"{PROJECT}.curated.plays")
    col_names = {f.name for f in table.schema}
    assert "season" in col_names, "curated.plays missing 'season' column"
    assert "week" in col_names, "curated.plays missing 'week' column"
    # If play-level data includes game_id, we can verify it links to curated.games
    if "game_id" in col_names:
        rows = list(bq_client.query(f"""
            SELECT COUNT(*) as orphans
            FROM `{PROJECT}.curated.plays` p
            LEFT JOIN `{PROJECT}.curated.games` g USING (game_id)
            WHERE g.game_id IS NULL AND p.season >= 2020
        """).result())
        assert rows[0]["orphans"] == 0, (
            f"{rows[0]['orphans']} plays reference game_ids not in curated.games"
        )


@pytest.mark.integration
def test_predictions_cover_prob_in_range(bq_client):
    """All predicted_home_cover_prob values are in [0, 1]."""
    rows = list(bq_client.query(f"""
        SELECT COUNT(*) as n
        FROM `{PROJECT}.experiments.backtest_predictions`
        WHERE predicted_home_cover_prob < 0 OR predicted_home_cover_prob > 1
    """).result())
    assert rows[0]["n"] == 0, (
        f"{rows[0]['n']} predictions have cover_prob outside [0, 1]"
    )


@pytest.mark.integration
def test_backtest_predictions_have_required_columns(bq_client):
    """Verify core prediction columns exist and have correct types."""
    table = bq_client.get_table(f"{PROJECT}.experiments.backtest_predictions")
    col_names = {f.name: f.field_type for f in table.schema}
    
    required_columns = {
        "experiment_id": "STRING",
        "game_id": "STRING",
        "season": "INTEGER",
        "week": "INTEGER",
        "predicted_home_cover_prob": "FLOAT64",
        "fold": "INTEGER",
    }
    
    for col, expected_type in required_columns.items():
        assert col in col_names, f"Missing column: {col}"
        assert col_names[col] == expected_type, (
            f"Column {col}: expected {expected_type}, got {col_names[col]}"
        )
