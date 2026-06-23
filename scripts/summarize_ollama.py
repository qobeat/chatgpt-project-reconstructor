#!/usr/bin/env python3
"""
summarize_ollama.py  (Stage 4 — OPTIONAL, fully local LLM)

Fill the *fuzzy* schema fields (goal, objectives, requirements_evolution,
quickstart, how_to_use, how_to_update) for each cluster bundle using a local
Ollama model. Deterministic facts (dates, version zips, file artifacts,
member ids) are copied from clusters.json and NOT trusted to the model.

Usage:
  python scripts/summarize_ollama.py --model gpt-oss:20b
  python scripts/summarize_ollama.py --run-label modeltest --limit 5 --dry-run
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))
import ulog  # noqa: E402
import paths  # noqa: E402
import run_log  # noqa: E402
import ollama_probe  # noqa: E402

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

FUZZY_KEYS = (
    "project_name", "goal", "objectives", "requirements",
    "requirements_evolution", "quickstart", "how_to_use", "use_case",
    "how_to_update",
)


def bundle_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def call_ollama(host: str, model: str, prompt: str, num_ctx: int,
                timeout: int, keep_alive: str = "24h") -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYS_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "format": "json",
        "think": False,
        "keep_alive": keep_alive,
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


def load_cached_projects(out_path: str) -> dict[str, dict]:
    if not os.path.exists(out_path):
        return {}
    try:
        with open(out_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    cache: dict[str, dict] = {}
    for p in data.get("projects") or []:
        slug = p.get("slug")
        if slug:
            cache[slug] = p
    return cache


def build_project_entry(c: dict, fuzzy: dict, bundle_hash: str) -> dict:
    return {
        "project_name": fuzzy.get("project_name") or c["slug"],
        "slug": c["slug"],
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
        "bundle_sha": bundle_hash,
    }


def fuzzy_from_cached(cached: dict) -> dict:
    return {k: cached.get(k, "" if k != "objectives" and k != "requirements"
                           and k != "requirements_evolution" else [])
            for k in FUZZY_KEYS}


def main() -> int:
    import time

    cfg = paths.load_config()
    ollama_cfg = cfg.get("ollama") or {}
    default_host = ollama_cfg.get("host", "http://localhost:11434")
    default_model = ollama_cfg.get("model", "gpt-oss:20b")
    default_num_ctx = int(ollama_cfg.get("num_ctx", 32768))
    default_max_chars = int(cfg.get("char_budget_per_bundle", 24000))

    ap = argparse.ArgumentParser(
        description="Stage 4 (optional): fill fuzzy schema fields per project "
                    "using a local Ollama model. Deterministic facts are merged "
                    "over model output.")
    ap.add_argument("--run-label", default=None,
                    help="Read/write under output/runs/<label>/ (isolated run).")
    ap.add_argument("--store", default=None,
                    help="Store dir with clusters.json (default: from paths).")
    ap.add_argument("--bundles", default=None,
                    help="Bundle dir with <slug>.md files (default: from paths).")
    ap.add_argument("--model", default=None,
                    help=f"Ollama model tag (default: {default_model} from config).")
    ap.add_argument("--host", default=None,
                    help=f"Ollama host (default: {default_host} from config).")
    ap.add_argument("--out", default=None,
                    help="Final JSON path (default: from paths).")
    ap.add_argument("--num-ctx", type=int, default=None,
                    help=f"Model context window (default: {default_num_ctx} from config).")
    ap.add_argument("--timeout", type=int, default=300,
                    help="Per-call timeout seconds (default: 300).")
    ap.add_argument("--max-chars", type=int, default=None,
                    help=f"Truncate each bundle (default: {default_max_chars} from config).")
    ap.add_argument("--keep-alive", default="24h",
                    help="Ollama keep_alive between cluster calls (default: 24h).")
    ap.add_argument("--min-versions", type=int, default=1,
                    help="Only summarize clusters with >= this many version zips "
                         "(default: 1; use 0 for all).")
    ap.add_argument("--limit", type=int, default=0,
                    help="Summarize only the first N clusters after filtering (0 = all).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print per-cluster prompt sizes; make zero LLM calls.")
    ap.add_argument("--incremental", action="store_true",
                    help="Reuse cached project entries when bundle content unchanged.")
    ap.add_argument("--no-preflight", action="store_true",
                    help="Skip Ollama host/model preflight check.")
    ap.add_argument("--no-summary", action="store_true",
                    help="Do not write output/RUN_SUMMARY_<timestamp>.md.")
    args = ap.parse_args()

    run_label = args.run_label
    host = args.host or default_host
    model = args.model or default_model
    num_ctx = args.num_ctx if args.num_ctx is not None else default_num_ctx
    max_chars = args.max_chars if args.max_chars is not None else default_max_chars

    store = paths.store_dir(args.store, run_label=run_label)
    bundles = paths.bundles_dir(args.bundles, run_label=run_label)
    out_path = paths.reconstructed_json(args.out, run_label=run_label)
    root = paths.run_data_root(store=store, run_label=run_label)

    if not args.no_preflight and not args.dry_run:
        ok, msg = ollama_probe.preflight(model, host, num_ctx=num_ctx)
        if not ok:
            ulog.err("PREFLIGHT", host, error=msg)
            return 1
        ulog.log("PREFLIGHT", host, status=f"model={model} ctx={num_ctx}")

    cmd = " ".join(["./ollama.sh"] + sys.argv[1:])
    run_log.append_command(cmd, root)
    run_log.stage_start("summarize", root)

    cpath = os.path.join(store, "clusters.json")
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
    if args.limit > 0:
        clusters = clusters[: args.limit]
    ulog.log("FILTER", cpath, status=f"{len(clusters)} projects to summarize")

    cache = load_cached_projects(out_path) if args.incremental else {}

    projects = []
    for c in clusters:
        slug = c["slug"]
        bpath = os.path.join(bundles, f"{slug}.md")
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

        truncated = bundle
        if len(truncated) > max_chars:
            truncated = truncated[:max_chars] + "\n[...truncated...]"
        bhash = bundle_sha256(truncated)

        if args.incremental:
            prev = cache.get(slug)
            if prev and prev.get("bundle_sha") == bhash:
                ulog.log("CACHE hit", slug, status="bundle unchanged")
                projects.append(build_project_entry(c, fuzzy_from_cached(prev), bhash))
                continue

        prompt = (
            f"Fields to emit (JSON keys): {FIELDS}\n\n"
            f"Transcripts and facts for project slug '{slug}':\n\n{truncated}"
        )

        if args.dry_run:
            ulog.log("DRY-RUN", slug,
                     status=f"prompt={len(prompt):,} chars ctx={num_ctx}")
            projects.append(build_project_entry(c, {}, bhash))
            continue

        ulog.log("LLM call", slug, status=f"model={model} ctx={num_ctx}")
        t0 = time.time()
        fuzzy = {}
        for attempt, ctx in enumerate((num_ctx, num_ctx // 2), start=1):
            try:
                raw = call_ollama(host, model, prompt, ctx, args.timeout,
                                  keep_alive=args.keep_alive)
                fuzzy = json.loads(raw)
                ulog.log("LLM done", slug,
                         status=f"{time.time()-t0:.0f}s (ctx={ctx})")
                break
            except Exception as e:
                ulog.err("LLM call", slug,
                         error=f"attempt {attempt} ctx={ctx}: {e}")
                if attempt == 1:
                    ulog.log("LLM retry", slug, status=f"halving ctx -> {ctx//2}")

        projects.append(build_project_entry(c, fuzzy, bhash))

    result = {
        "generated_by": f"ollama:{model}",
        "n_projects": len(projects),
        "projects": projects,
    }
    if args.dry_run:
        ulog.log("DRY-RUN", out_path, status=f"would write {len(projects)} projects")
        run_log.stage_end("summarize", root, n_projects=len(projects),
                          model=model, dry_run=True)
        return 0

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        ulog.log("WRITE", out_path, status=f"{len(projects)} projects")
    except OSError as e:
        ulog.err("WRITE", out_path, error=e)
        run_log.stage_end("summarize", root, error=str(e))
        return 1
    run_log.stage_end("summarize", root, n_projects=len(projects), model=model)
    ulog.log("DONE", out_path, status=f"{len(projects)} projects")

    if run_label:
        try:
            from run_catalog import register_run  # noqa: WPS433
            register_run(run_label, source="pipeline", set_latest=True)
        except Exception as e:
            sys.stderr.write(f"[summarize] Run catalog update skipped: {e}\n")

    if not args.no_summary:
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
            from collect_run_stats import write_summary  # noqa: WPS433
            summary_path = write_summary(root=root, label="Full pipeline")
            sys.stderr.write(f"[summarize] Summary: {summary_path}\n")
        except Exception as e:
            sys.stderr.write(f"[summarize] Summary skipped: {e}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
