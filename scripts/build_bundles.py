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
from typing import List


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", default="output/store")
    ap.add_argument("--out", default="output/bundles")
    ap.add_argument("--char-budget", type=int, default=48000)  # ~12k tokens
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    tdir = os.path.join(args.store, "transcripts")
    with open(os.path.join(args.store, "clusters.json"), "r", encoding="utf-8") as f:
        clusters = json.load(f)
    index = {}
    with open(os.path.join(args.store, "index.json"), "r", encoding="utf-8") as f:
        index = json.load(f)

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
                continue
            with open(tpath, "r", encoding="utf-8") as tf:
                body = tf.read()
            header = f"\n\n--- conversation {cid} | {meta.get('create_date')} | {meta.get('title')} ---\n"
            chunk = header + body
            if len(chunk) > budget:
                chunk = chunk[: max(0, budget)] + "\n[...bundle budget reached...]"
                parts.append(chunk)
                break
            parts.append(chunk)
            budget -= len(chunk)

        out_path = os.path.join(args.out, f"{slug}.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("".join(parts))
        bundle_index.append({
            "slug": slug,
            "bundle": os.path.relpath(out_path),
            "n_conversations": c["n_conversations"],
            "chars": sum(len(p) for p in parts),
        })

    with open(os.path.join(args.out, "INDEX.json"), "w", encoding="utf-8") as f:
        json.dump(bundle_index, f, ensure_ascii=False, indent=2)
    total = sum(b["chars"] for b in bundle_index)
    print(f"[done] {len(bundle_index)} bundles -> {args.out}  (~{total//4} tokens total)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
