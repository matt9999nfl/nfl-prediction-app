"""Base adapter interface — every source adapter implements this contract."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List
import pandas as pd


@dataclass
class ValidationResult:
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def __str__(self):
        lines = [f"ValidationResult(passed={self.passed})"]
        for e in self.errors:
            lines.append(f"  ERROR: {e}")
        for w in self.warnings:
            lines.append(f"  WARN:  {w}")
        return "\n".join(lines)


class SourceAdapter(ABC):
    name: str                  # "nflfastR", "ftn", etc.
    license_tag: str           # "open", "personal_use_only", "licensed_commercial"

    @abstractmethod
    def fetch(self, season: int, week: int | None = None) -> pd.DataFrame: ...

    @abstractmethod
    def validate(self, df: pd.DataFrame) -> ValidationResult: ...

    @abstractmethod
    def normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map vendor column names to our canonical schema."""
        ...
