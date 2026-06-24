#!/usr/bin/env bash
# ollama.sh — activate venv then run Stage 4 (local Ollama summarizer)
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/activate_env.sh
source "$REPO_DIR/scripts/lib/activate_env.sh"
exec "$PYTHON" "$REPO_DIR/scripts/summarize_ollama.py" "$@"
