"""Run A3 shuffled-label leakage test."""
import os
import sys
from pathlib import Path

os.environ["EXPERIMENT_CONFIG_ID"] = "decaa551-b991-43af-9a71-ab70b9580af7"
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from backtests.run_experiment import main
main()
