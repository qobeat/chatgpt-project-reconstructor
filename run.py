#!/usr/bin/env python3
"""
run.py — orchestrate the deterministic pipeline (Stages 1-3).

Stage 4 (LLM summary) is intentionally separate: run it via Cursor Composer
(prompts/cursor_extraction_prompt.md) or locally:
    python scripts/summarize_ollama.py ...

Usage:
  python run.py --zip /path/a.zip --zip /path/b.zip
  # then either Cursor Composer, or:
  python scripts/summarize_ollama.py --model gpt-oss:20b
"""
from __future__ import annotations
import argparse
import subprocess
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def run(mod: str, *cli: str):
    cmd = [sys.executable, os.path.join(HERE, "scripts", mod), *cli]
    sys.stderr.write("[run] " + " ".join(cmd) + "\n")
    subprocess.run(cmd, check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", action="append", required=True, dest="zips")
    ap.add_argument("--store", default="output/store")
    ap.add_argument("--bundles", default="output/bundles")
    ap.add_argument("--min-slug-votes", type=int, default=3)
    ap.add_argument("--char-budget", type=int, default=48000)
    args = ap.parse_args()

    zip_args = []
    for z in args.zips:
        zip_args += ["--zip", z]

    run("extract_cards.py", *zip_args, "--out", args.store)
    run("cluster_projects.py", "--store", args.store,
        "--min-slug-votes", str(args.min_slug_votes))
    run("build_bundles.py", "--store", args.store, "--out", args.bundles,
        "--char-budget", str(args.char_budget))

    sys.stderr.write(
        "\n[next] LLM summary step (pick one):\n"
        "  A) Cursor Composer: attach schema/project_history_schema.json + "
        "output/bundles/*.md, paste prompts/cursor_extraction_prompt.md\n"
        "  B) Local Ollama:    python scripts/summarize_ollama.py "
        "--model gpt-oss:20b\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
