"""Run A2 experiment."""
import os
import sys
from pathlib import Path

os.environ["EXPERIMENT_CONFIG_ID"] = "6ec7deac-3c62-4954-a8d4-a7bfb21b410f"
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from backtests.run_experiment import main
main()
