#!/usr/bin/env bash
# runs.sh — browse, search, and manage labeled pipeline runs
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/activate_env.sh
source "$REPO_DIR/scripts/lib/activate_env.sh"
exec "$PYTHON" "$REPO_DIR/scripts/runs.py" "$@"
