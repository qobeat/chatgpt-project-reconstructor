#!/usr/bin/env bash
# ollama.sh — activate venv then run Stage 4 (local Ollama summarizer)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/.venv/bin/activate"
exec python "$SCRIPT_DIR/scripts/summarize_ollama.py" "$@"
