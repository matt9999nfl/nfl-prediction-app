"""
Environment fingerprint — recorded on every run (PROMPT-STAGE1-FINISH-
EXPLANATIONS.md §5) so a future reproduction or mismatch investigation (like
the 2026-09-17 Windows-vs-Linux week-1/week-2 gap, QUESTIONS.md) knows exactly
what platform, package versions, and code produced a result, instead of
relying on memory.

One place, reused by predict_upcoming.py, run_experiment.py (via bq_writer.py)
and explain_picks.py — previously each rolled its own copy of this dict.
"""
from __future__ import annotations

import json
import os
import platform

import numpy as np
import pandas as pd
import sklearn
import xgboost


def environment_fingerprint() -> dict:
    """
    Full fingerprint: platform, Python, the four numerically-relevant package
    versions, the git commit baked into the image at build time (GIT_SHA, a
    Dockerfile ARG — see cloudbuild.yaml), and the Cloud Run execution name
    (CLOUD_RUN_EXECUTION, set automatically by Cloud Run Jobs; None outside
    Cloud Run, e.g. a local run or a one-off Cloud Build step).
    """
    return {
        "platform_system": platform.system(),
        "platform_release": platform.release(),
        "platform_machine": platform.machine(),
        "python_version": platform.python_version(),
        "pandas_version": pd.__version__,
        "numpy_version": np.__version__,
        "scikit_learn_version": sklearn.__version__,
        "xgboost_version": xgboost.__version__,
        "git_sha": os.environ.get("GIT_SHA"),
        "cloud_run_execution": os.environ.get("CLOUD_RUN_EXECUTION"),
    }


def backtest_runs_env_columns() -> dict:
    """
    The fingerprint reshaped onto experiments.backtest_runs' own env_* column
    names: env_platform, env_python, env_packages (JSON: pandas/numpy/
    scikit-learn/xgboost), git_sha, cloud_run_execution.
    """
    fp = environment_fingerprint()
    return {
        "env_platform": fp["platform_system"],
        "env_python": fp["python_version"],
        "env_packages": json.dumps({
            "pandas": fp["pandas_version"],
            "numpy": fp["numpy_version"],
            "scikit-learn": fp["scikit_learn_version"],
            "xgboost": fp["xgboost_version"],
        }),
        "git_sha": fp["git_sha"],
        "cloud_run_execution": fp["cloud_run_execution"],
    }
