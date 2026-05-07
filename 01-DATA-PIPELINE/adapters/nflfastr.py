"""
nflfastR source adapter.
Wraps nfl_data_py for play-by-play, schedules, and weekly rosters.
"""
import logging
from typing import Optional

import nfl_data_py as nfl
import pandas as pd

from adapters.base import SourceAdapter, ValidationResult

logger = logging.getLogger(__name__)


class NflfastrAdapter(SourceAdapter):
    name = "nflfastR"
    license_tag = "open"

    # ------------------------------------------------------------------ #
    # fetch                                                                #
    # ------------------------------------------------------------------ #

    def fetch_pbp(self, season: int) -> pd.DataFrame:
        logger.info(f"Fetching PBP for season {season}")
        df = nfl.import_pbp_data(years=[season], downcast=False)
        df["source"] = self.name
        df["license_tag"] = self.license_tag
        return df

    def fetch_schedules(self, season: int) -> pd.DataFrame:
        logger.info(f"Fetching schedules for season {season}")
        df = nfl.import_schedules(years=[season])
        df["source"] = self.name
        df["license_tag"] = self.license_tag
        return df

    def fetch_rosters(self, season: int) -> pd.DataFrame:
        logger.info(f"Fetching weekly rosters for season {season}")
        df = nfl.import_weekly_rosters(years=[season])
        df["source"] = self.name
        df["license_tag"] = self.license_tag
        return df

    # Required by abstract base — season-level fetch dispatches to above.
    def fetch(self, season: int, week: Optional[int] = None) -> pd.DataFrame:
        raise NotImplementedError("Use fetch_pbp / fetch_schedules / fetch_rosters directly.")

    # ------------------------------------------------------------------ #
    # validate                                                             #
    # ------------------------------------------------------------------ #

    def validate_pbp(self, df: pd.DataFrame, season: int) -> ValidationResult:
        errors, warnings = [], []
        row_count = len(df)
        expected_min = 40_000
        expected_max = 65_000
        if row_count < expected_min:
            errors.append(f"PBP {season}: only {row_count} rows (expected ≥{expected_min})")
        elif row_count > expected_max:
            warnings.append(f"PBP {season}: {row_count} rows exceeds expected max {expected_max}")
        else:
            logger.info(f"PBP {season}: {row_count} rows — OK")

        for col in ("game_id", "play_id", "posteam", "defteam"):
            if col not in df.columns:
                errors.append(f"PBP {season}: missing required column '{col}'")

        return ValidationResult(passed=len(errors) == 0, errors=errors, warnings=warnings)

    def validate_schedules(self, df: pd.DataFrame, season: int) -> ValidationResult:
        errors, warnings = [], []
        row_count = len(df)
        expected_min = 256
        expected_max = 290
        if row_count < expected_min:
            errors.append(f"Schedules {season}: only {row_count} rows (expected ≥{expected_min})")
        elif row_count > expected_max:
            warnings.append(f"Schedules {season}: {row_count} rows — check for duplicates or preseason")

        for col in ("game_id", "season", "week", "home_team", "away_team"):
            if col not in df.columns:
                errors.append(f"Schedules {season}: missing required column '{col}'")

        return ValidationResult(passed=len(errors) == 0, errors=errors, warnings=warnings)

    def validate_rosters(self, df: pd.DataFrame, season: int) -> ValidationResult:
        errors, warnings = [], []
        for col in ("player_id", "player_name", "team", "season", "week"):
            if col not in df.columns:
                errors.append(f"Rosters {season}: missing required column '{col}'")
        return ValidationResult(passed=len(errors) == 0, errors=errors, warnings=warnings)

    def validate(self, df: pd.DataFrame) -> ValidationResult:
        raise NotImplementedError("Use validate_pbp / validate_schedules / validate_rosters directly.")

    # ------------------------------------------------------------------ #
    # normalize — raw landing keeps all columns; no renaming at raw layer #
    # ------------------------------------------------------------------ #

    def normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        return df
