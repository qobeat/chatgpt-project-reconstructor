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
sys.path.insert(0, os.path.join(HERE, "scripts", "lib"))
import paths  # noqa: E402
import run_log  # noqa: E402


def _data_root_from_store(store: str) -> str:
    return os.path.abspath(os.path.dirname(store))


def _write_summary(store: str, label: str) -> None:
    try:
        sys.path.insert(0, os.path.join(HERE, "scripts"))
        from collect_run_stats import write_summary  # noqa: WPS433
        root = _data_root_from_store(store)
        out = write_summary(root=root, label=label)
        sys.stderr.write(f"[run] Summary: {out}\n")
    except Exception as e:
        sys.stderr.write(f"[run] Summary skipped: {e}\n")


def run(mod: str, *cli: str):
    cmd = [sys.executable, os.path.join(HERE, "scripts", mod), *cli]
    sys.stderr.write("[run] " + " ".join(cmd) + "\n")
    subprocess.run(cmd, check=True)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Orchestrate deterministic Stages 1-3 (extract -> cluster "
                    "-> bundle). Stage 4 (LLM) is run separately via Cursor or "
                    "scripts/summarize_ollama.py.")
    ap.add_argument("--zip", action="append", required=True, dest="zips",
                    metavar="PATH", help="Export .zip (repeatable).")
    ap.add_argument("--store", default=None,
                    help="Store directory (default: $RECONSTRUCTOR_DATA_ROOT/store "
                         "or output/store).")
    ap.add_argument("--bundles", default=None,
                    help="Bundle directory (default: $RECONSTRUCTOR_DATA_ROOT/bundles "
                         "or output/bundles).")
    ap.add_argument("--min-slug-votes", type=int, default=3,
                    help="Clustering slug-vote threshold (default: 3).")
    ap.add_argument("--char-budget", type=int, default=24000,
                    help="Max chars per LLM bundle (default: 24000).")
    ap.add_argument("--min-versions", type=int, default=1,
                    help="Bundle only clusters with >= N version zips "
                         "(default: 1 = projects; 0 = all).")
    ap.add_argument("--verbose", action="store_true",
                    help="Verbose per-file read/write logging.")
    ap.add_argument("--no-summary", action="store_true",
                    help="Do not write output/RUN_SUMMARY_<timestamp>.md.")
    args = ap.parse_args()

    store = paths.store_dir(args.store)
    bundles = paths.bundles_dir(args.bundles)
    root = _data_root_from_store(store)

    run_log.append_command(" ".join(["./run.sh"] + sys.argv[1:]), root)
    run_log.record_run_start(root)

    zip_args = []
    for z in args.zips:
        zip_args += ["--zip", z]

    extract_args = [*zip_args, "--out", store]
    if args.verbose:
        extract_args.append("--verbose")
    run_log.stage_start("extract", root)
    run("extract_cards.py", *extract_args)
    run_log.stage_end("extract", root)

    run_log.stage_start("cluster", root)
    run("cluster_projects.py", "--store", store,
        "--min-slug-votes", str(args.min_slug_votes))
    run_log.stage_end("cluster", root)

    run_log.stage_start("bundle", root)
    run("build_bundles.py", "--store", store, "--out", bundles,
        "--char-budget", str(args.char_budget),
        "--min-versions", str(args.min_versions))
    run_log.stage_end("bundle", root)

    if not args.no_summary:
        _write_summary(store, label="Stages 1–3")

    out_json = paths.reconstructed_json()
    sys.stderr.write(
        "\n[next] LLM summary step (pick one):\n"
        "  A) Cursor Composer: attach schema/project_history_schema.json + "
        f"{bundles}/*.md, paste prompts/cursor_extraction_prompt.md\n"
        "  B) Local Ollama:    ./ollama.sh --model gpt-oss:20b\n"
        f"\n  Full JSON lands at: {out_json}\n"
        "  Publish to GitHub:  python scripts/export_public.py --review\n"
        "  Run summary:        ./run_summary.sh\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
