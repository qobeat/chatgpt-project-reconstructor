#!/usr/bin/env python3
"""
build_bundles.py  (Stage 3 — deterministic, zero-LLM)

Turn each cluster into a single token-capped bundle file the LLM can ingest in
one shot. Each bundle = deterministic facts (JSON header) + reduced transcripts
of its member conversations, ordered chronologically, hard-capped by a
character budget (~4 chars/token heuristic).

Bundles land in output/bundles/<slug>.md  and a bundles/INDEX.json lists them.

Usage:
  python scripts/build_bundles.py --store output/store --out output/bundles \
      [--char-budget 48000]
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from typing import List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))
import ulog  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Stage 3: build one token-capped LLM bundle per cluster.")
    ap.add_argument("--store", default="output/store",
                    help="Store dir with clusters.json + transcripts/ (default: output/store).")
    ap.add_argument("--out", default="output/bundles",
                    help="Bundle output directory (default: output/bundles).")
    ap.add_argument("--char-budget", type=int, default=48000,
                    help="Max chars per bundle (~4 chars/token; default: 48000).")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    ulog.log("MKDIR", args.out, status="ready")
    tdir = os.path.join(args.store, "transcripts")
    clusters_path = os.path.join(args.store, "clusters.json")
    index_path = os.path.join(args.store, "index.json")
    try:
        with open(clusters_path, "r", encoding="utf-8") as f:
            clusters = json.load(f)
        ulog.log("READ", clusters_path, status=f"{len(clusters)} clusters")
    except OSError as e:
        ulog.err("READ", clusters_path, error=e)
        return 1
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)
        ulog.log("READ", index_path, status=f"{len(index)} records")
    except OSError as e:
        ulog.err("READ", index_path, error=e)
        index = {}

    bundle_index = []
    for c in clusters:
        slug = c["slug"]
        facts = {
            "slug": slug,
            "start_date": c["start_date"],
            "end_date": c["end_date"],
            "n_conversations": c["n_conversations"],
            "n_versions": c["n_versions"],
            "version_zip_files": c["version_zip_files"],
            "file_artifacts": c["file_artifacts"][:60],
            "titles": c["titles"],
        }
        parts: List[str] = []
        parts.append("# DETERMINISTIC FACTS (authoritative — copy verbatim)\n")
        parts.append("```json\n" + json.dumps(facts, ensure_ascii=False, indent=2) + "\n```\n")
        parts.append("\n# REDUCED TRANSCRIPTS (chronological; code bodies stripped)\n")

        members = sorted(
            c["member_ids"],
            key=lambda cid: (index.get(cid, {}).get("create_time") or 0),
        )
        budget = args.char_budget - len("".join(parts))
        for cid in members:
            meta = index.get(cid, {})
            tpath = os.path.join(tdir, f"{cid}.txt")
            if not os.path.exists(tpath):
                ulog.dbg("READ transcript", tpath, status="missing, skipped")
                continue
            try:
                with open(tpath, "r", encoding="utf-8") as tf:
                    body = tf.read()
            except OSError as e:
                ulog.err("READ transcript", tpath, error=e)
                continue
            header = f"\n\n--- conversation {cid} | {meta.get('create_date')} | {meta.get('title')} ---\n"
            chunk = header + body
            if len(chunk) > budget:
                chunk = chunk[: max(0, budget)] + "\n[...bundle budget reached...]"
                parts.append(chunk)
                break
            parts.append(chunk)
            budget -= len(chunk)

        out_path = os.path.join(args.out, f"{slug}.md")
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write("".join(parts))
            ulog.log("WRITE bundle", out_path,
                     status=f"{sum(len(p) for p in parts):,} chars")
        except OSError as e:
            ulog.err("WRITE bundle", out_path, error=e)
            continue
        bundle_index.append({
            "slug": slug,
            "bundle": os.path.relpath(out_path),
            "n_conversations": c["n_conversations"],
            "chars": sum(len(p) for p in parts),
        })

    idx_path = os.path.join(args.out, "INDEX.json")
    try:
        with open(idx_path, "w", encoding="utf-8") as f:
            json.dump(bundle_index, f, ensure_ascii=False, indent=2)
        ulog.log("WRITE", idx_path, status=f"{len(bundle_index)} bundles")
    except OSError as e:
        ulog.err("WRITE", idx_path, error=e)
    total = sum(b["chars"] for b in bundle_index)
    ulog.log("DONE", args.out,
             status=f"{len(bundle_index)} bundles, ~{total//4} tokens total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
