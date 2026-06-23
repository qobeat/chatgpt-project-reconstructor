#!/usr/bin/env bash
# runs.sh — browse, search, and manage labeled pipeline runs
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/.env"
    set +a
fi
VENV_DIR="${VENV_DIR:-$HOME/.venvs/chatgpt-project-reconstructor}"
if [[ -f "$VENV_DIR/bin/activate" ]]; then
    source "$VENV_DIR/bin/activate"
    PYTHON=python
else
    PYTHON=python3
fi
exec "$PYTHON" "$SCRIPT_DIR/scripts/runs.py" "$@"
