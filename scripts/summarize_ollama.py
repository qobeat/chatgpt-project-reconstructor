#!/usr/bin/env python3
"""
summarize_ollama.py  (Stage 4 — OPTIONAL, fully local LLM)

Fill the *fuzzy* schema fields (goal, objectives, requirements_evolution,
quickstart, how_to_use, how_to_update) for each cluster bundle using a local
Ollama model. Deterministic facts (dates, version zips, file artifacts,
member ids) are copied from clusters.json and NOT trusted to the model.

This is optional: if you prefer Cursor Composer, skip this and use
prompts/cursor_extraction_prompt.md instead. Either path writes the same
output/reconstructed_projects.json.

Requires Ollama running locally (default http://localhost:11434) with a model
that meets the bundle context size (e.g. gpt-oss:20b @ 64k).

Usage:
  python scripts/summarize_ollama.py --store output/store \
      --bundles output/bundles --model gpt-oss:20b \
      --out output/reconstructed_projects.json
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))
import ulog  # noqa: E402

SYS_PROMPT = (
    "You reconstruct software project history from reduced chat transcripts. "
    "Output ONLY a single JSON object for ONE project, matching the provided "
    "field list. Be terse and factual. If a field is unknown, use an empty "
    "string or empty array. Do NOT invent file names, versions, or dates — "
    "those are supplied separately and will be merged over your output. "
    "requirements_evolution must be an ordered array of {date, change} drawn "
    "from how the user's asks change across the chronological transcripts."
)

FIELDS = (
    "project_name, goal, objectives (array), requirements (array), "
    "requirements_evolution (array of {date, change}), quickstart, "
    "how_to_use, use_case, how_to_update"
)


def call_ollama(host: str, model: str, prompt: str, num_ctx: int,
                timeout: int) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYS_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "format": "json",
        "think": False,  # disable reasoning channel: faster, avoids 500s on gpt-oss
        "options": {
            "temperature": 0.1,
            "num_ctx": num_ctx,
            "num_predict": 1024,
        },
    }
    req = urllib.request.Request(
        host.rstrip("/") + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("message", {}).get("content", "{}")


def main() -> int:
    import time
    ap = argparse.ArgumentParser(
        description="Stage 4 (optional): fill fuzzy schema fields per project "
                    "using a local Ollama model. Deterministic facts are merged "
                    "over model output.")
    ap.add_argument("--store", default="output/store",
                    help="Store dir with clusters.json (default: output/store).")
    ap.add_argument("--bundles", default="output/bundles",
                    help="Bundle dir with <slug>.md files (default: output/bundles).")
    ap.add_argument("--model", default="gpt-oss:20b",
                    help="Ollama model tag (default: gpt-oss:20b).")
    ap.add_argument("--host", default="http://localhost:11434",
                    help="Ollama host (default: http://localhost:11434).")
    ap.add_argument("--out", default="output/reconstructed_projects.json",
                    help="Final JSON path.")
    ap.add_argument("--num-ctx", type=int, default=32768,
                    help="Model context window (default: 32768; lower if OOM/500).")
    ap.add_argument("--timeout", type=int, default=300,
                    help="Per-call timeout seconds (default: 300).")
    ap.add_argument("--max-chars", type=int, default=24000,
                    help="Truncate each bundle to this many chars before sending.")
    ap.add_argument("--min-versions", type=int, default=1,
                    help="Only summarize clusters with >= this many version zips "
                         "(default: 1; use 0 for all).")
    args = ap.parse_args()

    cpath = os.path.join(args.store, "clusters.json")
    try:
        with open(cpath, "r", encoding="utf-8") as f:
            clusters = json.load(f)
        ulog.log("READ", cpath, status=f"{len(clusters)} clusters")
    except OSError as e:
        ulog.err("READ", cpath, error=e)
        return 1

    clusters = [c for c in clusters
                if c.get("n_versions", 0) >= args.min_versions
                or c.get("n_conversations", 0) >= 2]
    ulog.log("FILTER", cpath, status=f"{len(clusters)} projects to summarize")

    projects = []
    for c in clusters:
        slug = c["slug"]
        bpath = os.path.join(args.bundles, f"{slug}.md")
        if not os.path.exists(bpath):
            ulog.dbg("READ bundle", bpath, status="missing, skipped")
            continue
        try:
            with open(bpath, "r", encoding="utf-8") as f:
                bundle = f.read()
            ulog.log("READ bundle", bpath, status=f"{len(bundle):,} chars")
        except OSError as e:
            ulog.err("READ bundle", bpath, error=e)
            continue
        if len(bundle) > args.max_chars:
            bundle = bundle[:args.max_chars] + "\n[...truncated...]"
        prompt = (
            f"Fields to emit (JSON keys): {FIELDS}\n\n"
            f"Transcripts and facts for project slug '{slug}':\n\n{bundle}"
        )
        ulog.log("LLM call", slug, status=f"model={args.model} ctx={args.num_ctx}")
        t0 = time.time()
        fuzzy = {}
        for attempt, ctx in enumerate((args.num_ctx, args.num_ctx // 2), start=1):
            try:
                raw = call_ollama(args.host, args.model, prompt, ctx, args.timeout)
                fuzzy = json.loads(raw)
                ulog.log("LLM done", slug,
                         status=f"{time.time()-t0:.0f}s (ctx={ctx})")
                break
            except Exception as e:
                ulog.err("LLM call", slug,
                         error=f"attempt {attempt} ctx={ctx}: {e}")
                if attempt == 1:
                    ulog.log("LLM retry", slug, status=f"halving ctx -> {ctx//2}")

        projects.append({
            "project_name": fuzzy.get("project_name") or slug,
            "slug": slug,
            "start_date": c["start_date"],
            "end_date": c["end_date"],
            "n_conversations": c["n_conversations"],
            "n_versions": c["n_versions"],
            "version_zip_files": c["version_zip_files"],
            "file_artifacts": c["file_artifacts"],
            "source_conversation_ids": c["member_ids"],
            "goal": fuzzy.get("goal", ""),
            "objectives": fuzzy.get("objectives", []),
            "requirements": fuzzy.get("requirements", []),
            "requirements_evolution": fuzzy.get("requirements_evolution", []),
            "quickstart": fuzzy.get("quickstart", ""),
            "how_to_use": fuzzy.get("how_to_use", ""),
            "use_case": fuzzy.get("use_case", ""),
            "how_to_update": fuzzy.get("how_to_update", ""),
        })

    result = {
        "generated_by": f"ollama:{args.model}",
        "n_projects": len(projects),
        "projects": projects,
    }
    try:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        ulog.log("WRITE", args.out, status=f"{len(projects)} projects")
    except OSError as e:
        ulog.err("WRITE", args.out, error=e)
        return 1
    ulog.log("DONE", args.out, status=f"{len(projects)} projects")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
