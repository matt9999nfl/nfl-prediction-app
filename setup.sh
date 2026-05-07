#!/usr/bin/env bash
# setup.sh — bootstrap the NFL prediction app folder structure
# Run from the parent directory where you want nfl-prediction-app/ to live
# Idempotent: re-running won't clobber existing files

set -euo pipefail

ROOT="${1:-$HOME/Desktop/nfl-prediction-app}"
echo "Setting up project at: $ROOT"

# Create folder structure
mkdir -p "$ROOT"/{00-PROJECT-LEAD,01-DATA-PIPELINE,02-MODELING,03-BACKEND-API,04-FRONTEND,05-DEVOPS,06-TESTING-QA,docs}

# Create empty stub files only if they don't exist (preserve any work)
touch_if_missing() {
  local f="$1"
  if [[ ! -f "$f" ]]; then
    touch "$f"
    echo "  created: $f"
  fi
}

# Per-agent README pointers (instructions.md files come from the bundle)
for agent in 00-PROJECT-LEAD 01-DATA-PIPELINE 02-MODELING 03-BACKEND-API 04-FRONTEND 05-DEVOPS 06-TESTING-QA; do
  touch_if_missing "$ROOT/$agent/.gitkeep"
done

# Initialize git if not already
if [[ ! -d "$ROOT/.git" ]]; then
  (cd "$ROOT" && git init -q)
  echo "  initialized git repo"
fi

# Sensible .gitignore if missing
if [[ ! -f "$ROOT/.gitignore" ]]; then
  cat > "$ROOT/.gitignore" <<'EOF'
# Python
__pycache__/
*.pyc
.venv/
venv/
.env
*.egg-info/

# Node
node_modules/
dist/
.next/
.vite/

# IDE
.vscode/
.idea/
.DS_Store

# Local data and credentials
*.parquet
*.csv
local_data/
credentials/
service-account*.json

# Experiment artifacts (large)
02-MODELING/backtests/reports/*/artifacts/

# Logs
*.log
EOF
  echo "  created: .gitignore"
fi

echo ""
echo "Done. Structure:"
ls -la "$ROOT"
echo ""
echo "Next: copy the instructions.md files and docs from the bundle into place,"
echo "then open Cowork on $ROOT/00-PROJECT-LEAD to start."
