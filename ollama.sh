#!/usr/bin/env bash
# ollama.sh — activate venv then run Stage 4 (local Ollama summarizer)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/.env"
    set +a
fi
VENV_DIR="${VENV_DIR:-$HOME/.venvs/chatgpt-project-reconstructor}"
source "$VENV_DIR/bin/activate"
exec python "$SCRIPT_DIR/scripts/summarize_ollama.py" "$@"
