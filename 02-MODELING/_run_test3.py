"""Run test3 rush-feature experiment."""
import os
import sys
from pathlib import Path

os.environ["EXPERIMENT_CONFIG_ID"] = "19a50bf1-e812-4745-b153-042c6db46a00"
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from backtests.run_experiment import main
main()
