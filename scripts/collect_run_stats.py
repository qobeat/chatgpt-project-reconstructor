#!/usr/bin/env python3
"""
collect_run_stats.py — write output/RUN_SUMMARY_<timestamp>.md after a pipeline run.

Reads artifact counts/sizes, optional .run_manifest.json stage timings, and
RUN_COMMANDS.log for the command block.

Usage:
  python scripts/collect_run_stats.py              # after any stage
  python scripts/collect_run_stats.py --append-command './run.sh --zip x.zip'
  ./run_summary.sh                                 # wrapper (same thing)

Auto-invoked at end of run.py (Stages 1–3) and summarize_ollama.py (Stage 4)
unless --no-summary is passed to those tools.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))
import paths  # noqa: E402
import run_log  # noqa: E402


DEFAULT_COMMANDS = """\
bash setup.sh
./run.sh --zip "<path-to-latest-export>.zip"
./ollama.sh --model qwen2.5-coder:14b --num-ctx 16384
python scripts/export_public.py --md --review
"""


def _mtime(path: str) -> dt.datetime | None:
    if not os.path.exists(path):
        return None
    return dt.datetime.fromtimestamp(os.path.getmtime(path), tz=dt.timezone.utc)


def _line_count(path: str) -> int:
    with open(path, encoding="utf-8", errors="replace") as f:
        return sum(1 for _ in f)


def _dir_size(path: str) -> int:
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for fn in filenames:
            fp = os.path.join(dirpath, fn)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total


def collect(root: str) -> dict:
    store = os.path.join(root, "store")
    bundles = os.path.join(root, "bundles")
    transcripts = glob.glob(os.path.join(store, "transcripts", "*.txt"))
    bundle_mds = [
        p for p in glob.glob(os.path.join(bundles, "*.md"))
        if os.path.basename(p) not in ("INDEX.json",)
    ]

    stats: dict = {
        "root": os.path.abspath(root),
        "total_files": sum(
            1 for p in glob.glob(os.path.join(root, "**", "*"), recursive=True)
            if os.path.isfile(p)
        ),
        "transcripts": len(transcripts),
        "transcript_lines": sum(_line_count(p) for p in transcripts),
        "bundles": len(bundle_mds),
        "bundle_lines": sum(_line_count(p) for p in bundle_mds),
        "disk_bytes": {
            "store": _dir_size(store) if os.path.isdir(store) else 0,
            "bundles": _dir_size(bundles) if os.path.isdir(bundles) else 0,
        },
    }

    for name in ("index.json", "cards.jsonl", "clusters.json"):
        p = os.path.join(store, name)
        if not os.path.exists(p):
            continue
        stats[f"{name}_bytes"] = os.path.getsize(p)
        if name == "cards.jsonl":
            stats["cards"] = _line_count(p)
        elif name == "index.json":
            with open(p, encoding="utf-8") as f:
                stats["index_records"] = len(json.load(f))
        elif name == "clusters.json":
            with open(p, encoding="utf-8") as f:
                clusters = json.load(f)
            stats["clusters"] = len(clusters)
            stats["clusters_with_version_zip"] = sum(
                1 for c in clusters if c.get("n_versions", 0) >= 1)
            stats["clusters_2plus_conversations"] = sum(
                1 for c in clusters if c.get("n_conversations", 0) >= 2)
            stats["total_version_zips"] = sum(
                c.get("n_versions", 0) for c in clusters)

    rec_path = os.path.join(root, "reconstructed_projects.json")
    if os.path.exists(rec_path):
        stats["reconstructed_bytes"] = os.path.getsize(rec_path)
        with open(rec_path, encoding="utf-8") as f:
            rec = json.load(f)
        stats["n_projects"] = rec.get("n_projects", len(rec.get("projects", [])))
        stats["generated_by"] = rec.get("generated_by", "unknown")

    manifest = run_log.load_manifest(root)
    stats["manifest"] = manifest

    # Prefer manifest wall times; fall back to file mtimes
    m = manifest.get("stages", {})
    stats["stage_seconds"] = {
        "extract": run_log.stage_seconds(manifest, "extract"),
        "cluster": run_log.stage_seconds(manifest, "cluster"),
        "bundle": run_log.stage_seconds(manifest, "bundle"),
        "summarize": run_log.stage_seconds(manifest, "summarize"),
    }
    s13 = [stats["stage_seconds"].get(k) for k in ("extract", "cluster", "bundle")]
    s13_vals = [x for x in s13 if x is not None]
    if s13_vals:
        stats["stage1_3_seconds"] = sum(s13_vals)
    stats["stage4_seconds"] = stats["stage_seconds"].get("summarize")

    t_first = min((_mtime(p) for p in transcripts if _mtime(p)), default=None)
    t_clusters = _mtime(os.path.join(store, "clusters.json"))
    t_bundles = _mtime(os.path.join(bundles, "INDEX.json"))
    t_rec = _mtime(rec_path)

    if stats.get("stage1_3_seconds") is None and t_first and t_clusters:
        stats["stage1_3_seconds"] = (t_clusters - t_first).total_seconds()
    if stats.get("stage4_seconds") is None and t_bundles and t_rec:
        stats["stage4_seconds"] = (t_rec - t_bundles).total_seconds()
    if t_first and t_rec:
        stats["total_wall_seconds"] = (t_rec - t_first).total_seconds()
    elif manifest.get("started_utc") and m.get("summarize", {}).get("ended_utc"):
        t0 = dt.datetime.fromisoformat(manifest["started_utc"])
        t1 = dt.datetime.fromisoformat(m["summarize"]["ended_utc"])
        stats["total_wall_seconds"] = (t1 - t0).total_seconds()

    stats["mtimes"] = {
        "first_transcript_utc": t_first.isoformat() if t_first else None,
        "clusters_utc": t_clusters.isoformat() if t_clusters else None,
        "bundles_index_utc": t_bundles.isoformat() if t_bundles else None,
        "reconstructed_utc": t_rec.isoformat() if t_rec else None,
    }
    if stats.get("n_projects") and stats.get("stage4_seconds"):
        stats["stage4_seconds_per_project"] = round(
            stats["stage4_seconds"] / max(stats["n_projects"], 1), 1)
    return stats


def format_summary(stats: dict, commands: str, label: str = "") -> str:
    def fmt_sec(s: float | None) -> str:
        if s is None:
            return "n/a"
        m, sec = divmod(int(s), 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h}h {m}m {sec}s ({s:.0f}s)"
        if m:
            return f"{m}m {sec}s ({s:.0f}s)"
        return f"{sec}s"

    title = "# Pipeline Run Summary"
    if label:
        title += f" ({label})"

    lines = [
        title,
        "",
        f"Generated: {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"Data root: `{stats['root']}`",
        "",
        "## Commands run",
        "",
        "```bash",
        commands.strip() or "(no RUN_COMMANDS.log — pass --append-command during runs)",
        "```",
        "",
        "## Output inventory",
        "",
        "| Artifact | Count / size |",
        "|----------|--------------|",
        f"| Total files under data root | {stats.get('total_files', 0):,} |",
        f"| Conversations (index / cards / transcripts) | "
        f"{stats.get('index_records', stats.get('cards', stats.get('transcripts', 0))):,} |",
        f"| Transcript lines | {stats.get('transcript_lines', 0):,} |",
        f"| Project clusters | {stats.get('clusters', 'n/a')} |",
        f"| Clusters with ≥1 version zip | {stats.get('clusters_with_version_zip', 'n/a')} |",
        f"| Clusters with ≥2 conversations | {stats.get('clusters_2plus_conversations', 'n/a')} |",
        f"| Version zip files (sum across clusters) | {stats.get('total_version_zips', 'n/a')} |",
        f"| LLM bundles (.md) | {stats.get('bundles', 0):,} |",
        f"| Bundle lines | {stats.get('bundle_lines', 0):,} |",
    ]
    if stats.get("n_projects") is not None:
        lines.append(
            f"| Reconstructed projects (Stage 4) | {stats['n_projects']:,} "
            f"(`{stats.get('generated_by', '?')}`) |"
        )
    for key, lbl in (
        ("index.json_bytes", "index.json"),
        ("cards.jsonl_bytes", "cards.jsonl"),
        ("clusters.json_bytes", "clusters.json"),
        ("reconstructed_bytes", "reconstructed_projects.json"),
    ):
        if key in stats:
            lines.append(f"| {lbl} size | {stats[key]:,} bytes |")
    disk = stats.get("disk_bytes", {})
    if disk:
        lines.append(f"| store/ on disk | {disk.get('store', 0):,} bytes |")
        lines.append(f"| bundles/ on disk | {disk.get('bundles', 0):,} bytes |")

    ss = stats.get("stage_seconds", {})
    lines += [
        "",
        "## Processing time",
        "",
        f"- Stage 1 extract: **{fmt_sec(ss.get('extract'))}**",
        f"- Stage 2 cluster: **{fmt_sec(ss.get('cluster'))}**",
        f"- Stage 3 bundle: **{fmt_sec(ss.get('bundle'))}**",
        f"- Stages 1–3 combined: **{fmt_sec(stats.get('stage1_3_seconds'))}**",
        f"- Stage 4 summarize: **{fmt_sec(stats.get('stage4_seconds'))}**",
    ]
    if stats.get("stage4_seconds_per_project") is not None:
        lines.append(
            f"- Stage 4 per project: **{stats['stage4_seconds_per_project']:.1f}s**"
        )
    lines.append(
        f"- Total wall time: **{fmt_sec(stats.get('total_wall_seconds'))}**"
    )
    lines += ["", "## Timestamps (UTC)", ""]
    for k, v in stats.get("mtimes", {}).items():
        lines.append(f"- `{k}`: {v or 'n/a'}")
    lines.append("")
    return "\n".join(lines)


def write_summary(
    root: str | None = None,
    commands: str | None = None,
    commands_file: str | None = None,
    out: str | None = None,
    label: str = "",
) -> str:
    if not root:
        dr = paths.data_root()
        root = dr if dr else os.path.join(paths.ROOT, "output")
    if not os.path.isdir(root):
        raise FileNotFoundError(f"Root not found: {root}")

    cmd = commands
    if commands_file:
        with open(commands_file, encoding="utf-8") as f:
            cmd = f.read()
    if not cmd:
        cmd = run_log.read_commands(root) or DEFAULT_COMMANDS

    stats = collect(root)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = out or os.path.join(root, f"RUN_SUMMARY_{stamp}.md")
    body = format_summary(stats, cmd, label=label)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(body)
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Write RUN_SUMMARY_<timestamp>.md for the latest pipeline run.")
    ap.add_argument("--root", default=None, help="Output/data root (default: from paths)")
    ap.add_argument("--commands-file", help="File with commands to embed")
    ap.add_argument("--commands", default=None, help="Inline commands text")
    ap.add_argument("--append-command", help="Append a command to RUN_COMMANDS.log")
    ap.add_argument("--out", default=None, help="Output path (default: root/RUN_SUMMARY_<now>.md)")
    ap.add_argument("--label", default="", help="Optional label in summary title")
    args = ap.parse_args()

    root = args.root
    if not root:
        dr = paths.data_root()
        root = dr if dr else os.path.join(paths.ROOT, "output")

    if args.append_command:
        run_log.append_command(args.append_command, root)

    try:
        out_path = write_summary(
            root=root,
            commands=args.commands,
            commands_file=args.commands_file,
            out=args.out,
            label=args.label,
        )
    except FileNotFoundError as e:
        sys.stderr.write(f"[error] {e}\n")
        return 1

    sys.stderr.write(f"[stats] Wrote {out_path}\n")
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
