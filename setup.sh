#!/usr/bin/env bash
# setup.sh — bootstrap the venv for chatgpt-project-reconstructor
# Run once from the project root:  bash setup.sh
set -euo pipefail

VENV=".venv"
PYTHON=""

# ── find python 3.10+ ──────────────────────────────────────────────────────
for candidate in python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" &>/dev/null; then
        ver=$("$candidate" -c 'import sys; print(sys.version_info[:2])')
        if "$candidate" -c 'import sys; assert sys.version_info >= (3,10)' 2>/dev/null; then
            PYTHON="$candidate"
            break
        fi
    fi
done
if [[ -z "$PYTHON" ]]; then
    echo "[error] Python 3.10+ not found. Install: sudo apt install python3.12"
    exit 1
fi
echo "[setup] Using $PYTHON ($("$PYTHON" --version))"

# ── create venv if absent ─────────────────────────────────────────────────
if [[ ! -d "$VENV" ]]; then
    echo "[setup] Creating venv at $VENV ..."
    "$PYTHON" -m venv "$VENV"
fi

PIP="$VENV/bin/pip"
VPYTHON="$VENV/bin/python"

# ── upgrade pip quietly ───────────────────────────────────────────────────
"$PIP" install --quiet --upgrade pip

# ── install ijson (recommended; falls back gracefully if build fails) ──────
echo "[setup] Installing ijson ..."
if ! "$PIP" install "ijson>=3.2" 2>/dev/null; then
    echo "[warn]  ijson build failed (no C compiler?). Falling back to stdlib mode."
    echo "        Large zips (>200 MB) will load fully into RAM."
else
    echo "[setup] ijson installed OK."
fi

# ── write run.sh activation wrapper ───────────────────────────────────────
cat > run.sh << 'RUN'
#!/usr/bin/env bash
# run.sh — activate venv then delegate to run.py
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/.venv/bin/activate"
exec python "$SCRIPT_DIR/run.py" "$@"
RUN
chmod +x run.sh

# ── write ollama.sh wrapper ────────────────────────────────────────────────
cat > ollama.sh << 'OLL'
#!/usr/bin/env bash
# ollama.sh — activate venv then run Stage 4 (local Ollama summarizer)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/.venv/bin/activate"
exec python "$SCRIPT_DIR/scripts/summarize_ollama.py" "$@"
OLL
chmod +x ollama.sh

# ── write diagnose.sh wrapper ──────────────────────────────────────────────
cat > diagnose.sh << 'DIAG'
#!/usr/bin/env bash
# diagnose.sh — inspect an export's structure (read-only)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/.venv/bin/activate"
exec python "$SCRIPT_DIR/scripts/diagnose.py" "$@"
DIAG
chmod +x diagnose.sh

echo ""
echo "[setup] Done. Wrappers written: run.sh, ollama.sh, diagnose.sh"
echo ""
echo "  Run the pipeline (deterministic Stages 1-3):"
echo "    ./run.sh --zip \"/mnt/c/Users/kirae/Downloads/ChatGpt/<export>.zip\""
echo "    ./run.sh --zip \"<export>.zip\" --verbose      # per-file logging"
echo ""
echo "  Stage 4 — LLM summary (offline):"
echo "    ./ollama.sh --model gpt-oss:20b"
echo ""
echo "  Inspect an export if parsing yields 0 (read-only):"
echo "    ./diagnose.sh --zip \"<export>.zip\""
echo ""
echo "  Manual venv (alternative to wrappers):"
echo "    source .venv/bin/activate && python run.py --zip \"<export>.zip\""
