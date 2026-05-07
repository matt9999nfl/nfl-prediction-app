"""
Cloud Run Job entrypoint for the data pipeline.

Environment variables:
  PIPELINE_MODE=full    → full season refresh (all steps)
  PIPELINE_MODE=gameday → gameday refresh (schedules + curated.games only)
"""
import os
import sys
from pathlib import Path

# Add parent directory to path so we can import run_pipeline
sys.path.insert(0, str(Path(__file__).parent.parent))

mode = os.environ.get("PIPELINE_MODE", "full")

if mode == "full":
    # Full pipeline: ingest raw data + rebuild curated layer
    from scripts.run_pipeline import main
    main()
elif mode == "gameday":
    # Gameday refresh: schedules + curated.games only (skip PBP/rosters for speed)
    # Note: Confirm with DATA-PIPELINE that --start-at 1 is the correct invocation
    from scripts.run_pipeline import main
    sys.argv = ["run_pipeline.py", "--start-at", "1"]
    main()
else:
    print(f"Unknown PIPELINE_MODE: {mode}", file=sys.stderr)
    sys.exit(1)
