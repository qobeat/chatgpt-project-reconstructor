#!/usr/bin/env python3
"""
runs.py — browse, search, and manage labeled pipeline runs.

Usage:
  ./runs.sh list
  ./runs.sh show [LABEL]
  ./runs.sh search ados [--run LABEL] [--full]
  ./runs.sh cards [--run LABEL] [--search Q] [--limit N]
  ./runs.sh migrate [--label legacy-20260622]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
import paths  # noqa: E402
import run_catalog  # noqa: E402


def _resolve(label: str | None) -> str:
    resolved = paths.resolve_run_label(label)
    if resolved:
        return resolved
    if label:
        return label
    runs = run_catalog.list_runs()
    if runs:
        return runs[0]["label"]
    raise SystemExit(
        "[error] No runs found. Create: ./run.sh --run-label NAME  "
        "or migrate: ./runs.sh migrate"
    )


def cmd_list(args: argparse.Namespace) -> int:
    catalog = run_catalog.load_catalog()
    runs = run_catalog.list_runs()
    if args.json:
        print(json.dumps({"latest": catalog.get("latest"), "runs": runs},
                         ensure_ascii=False, indent=2))
    else:
        print(run_catalog.format_run_list(runs, latest=catalog.get("latest")))
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    label = _resolve(args.run)
    manifest = run_catalog.get_run(label)
    if args.json:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    else:
        print(run_catalog.format_run_show(manifest))
    return 0


def cmd_latest(args: argparse.Namespace) -> int:
    label = _resolve(None)
    if args.json:
        print(json.dumps({"label": label}))
    else:
        print(label)
    return 0


def cmd_paths(args: argparse.Namespace) -> int:
    label = _resolve(args.run)
    rp = run_catalog.run_paths(label)
    if args.json:
        print(json.dumps(rp, indent=2))
    elif args.export:
        print(f"export RUN_LABEL={label}")
        print(f"export RUN_ROOT={rp['root']}")
        print(f"export STORE={rp['store']}")
        print(f"export BUNDLES={rp['bundles']}")
        print(f"export RECONSTRUCTED={rp['reconstructed']}")
    else:
        for k, v in rp.items():
            print(f"{k}: {v}")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    label = _resolve(args.run)
    results = run_catalog.search_run(
        label,
        args.query,
        scope=args.scope,
        regex=args.regex,
        full=args.full,
        min_versions=args.min_versions,
        limit=args.limit,
    )
    if args.json:
        print(json.dumps({"run": label, "query": args.query, "results": results},
                         ensure_ascii=False, indent=2))
    else:
        print(run_catalog.format_search_results(label, args.query, results))
    return 0


def cmd_cards(args: argparse.Namespace) -> int:
    label = _resolve(args.run)
    run = run_catalog.get_run(label)
    store = run["paths"]["store"]
    if args.search:
        items = run_catalog.search_cards(
            store, args.search, regex=args.regex, limit=args.limit)
    else:
        items = []
        for card in run_catalog._load_cards(store):  # noqa: SLF001
            items.append({
                "id": card.get("id"),
                "title": card.get("title"),
                "create_date": card.get("create_date"),
                "update_date": card.get("update_date"),
                "n_turns": card.get("n_turns"),
                "slug_votes": card.get("slug_votes"),
            })
            if len(items) >= args.limit:
                break
    if args.json:
        print(json.dumps(items, ensure_ascii=False, indent=2))
    else:
        print(f"# Cards — run `{label}` ({len(items)} shown)\n")
        for c in items:
            slug = max((c.get("slug_votes") or {"": 0}).items(),
                       key=lambda kv: kv[1], default=("", 0))[0]
            print(
                f"- {c.get('create_date', '?'):<12} "
                f"{c.get('title', '?')[:50]:<50} "
                f"turns={c.get('n_turns', 0):<4} slug={slug}"
            )
    return 0


def cmd_clusters(args: argparse.Namespace) -> int:
    label = _resolve(args.run)
    run = run_catalog.get_run(label)
    store = run["paths"]["store"]
    if args.search:
        items = run_catalog.search_clusters(
            store, args.search, regex=args.regex,
            min_versions=args.min_versions, limit=args.limit)
    else:
        items = []
        for c in run_catalog._load_clusters(store):  # noqa: SLF001
            if c.get("n_versions", 0) < args.min_versions:
                continue
            items.append({
                "slug": c.get("slug"),
                "titles": c.get("titles"),
                "n_conversations": c.get("n_conversations"),
                "n_versions": c.get("n_versions"),
                "start_date": c.get("start_date"),
                "end_date": c.get("end_date"),
            })
            if len(items) >= args.limit:
                break
    if args.json:
        print(json.dumps(items, ensure_ascii=False, indent=2))
    else:
        print(f"# Clusters — run `{label}` ({len(items)} shown)\n")
        for c in items:
            title = (c.get("titles") or ["?"])[0][:40]
            print(
                f"- {c.get('slug', '?'):<30} "
                f"convs={c.get('n_conversations', 0):<4} "
                f"ver={c.get('n_versions', 0):<3} "
                f"{c.get('start_date', '?')}..{c.get('end_date', '?')}  {title}"
            )
    return 0


def cmd_bundles(args: argparse.Namespace) -> int:
    label = _resolve(args.run)
    run = run_catalog.get_run(label)
    bundles = run["paths"]["bundles"]
    if args.search:
        items = run_catalog.search_bundles(
            bundles, args.search, regex=args.regex, limit=args.limit)
    else:
        items = run_catalog.search_bundles(bundles, "", regex=False,
                                           limit=99999)
        items = items[: args.limit] if items else []
        if not items:
            import glob
            items = []
            for path in sorted(glob.glob(os.path.join(bundles, "*.md")))[: args.limit]:
                slug = os.path.splitext(os.path.basename(path))[0]
                items.append({"slug": slug, "chars": os.path.getsize(path),
                              "path": path})
    if args.json:
        print(json.dumps(items, ensure_ascii=False, indent=2))
    else:
        print(f"# Bundles — run `{label}` ({len(items)} shown)\n")
        for b in items:
            print(f"- {b.get('slug', '?'):<40} {b.get('chars', 0):>8,} chars")
    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    if not paths.legacy_output_detected():
        sys.stderr.write("[runs] No legacy output to migrate.\n")
        return 1
    try:
        plan = run_catalog.migrate_legacy_output(
            args.label, dry_run=args.dry_run, copy=args.copy)
    except (FileNotFoundError, FileExistsError) as e:
        sys.stderr.write(f"[error] {e}\n")
        return 1
    if args.dry_run:
        print(json.dumps(plan, indent=2))
    else:
        sys.stderr.write(
            f"[runs] Migrated to runs/{plan['label']}/\n"
            f"[runs] Latest pointer updated.\n"
        )
        print(run_catalog.format_run_show(plan["manifest"]))
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    label = _resolve(args.run)
    run = run_catalog.get_run(label)
    root = run["paths"]["root"]
    sys.path.insert(0, HERE)
    from collect_run_stats import write_summary  # noqa: WPS433
    out = write_summary(root=root, label=f"run {label}")
    sys.stderr.write(f"[runs] Summary: {out}\n")
    run_catalog.register_run(label, source=run.get("source", "pipeline"))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Browse, search, and manage labeled pipeline runs.")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("list", help="List all runs")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("show", help="Show run details")
    p.add_argument("run", nargs="?", default=None, help="Run label (default: latest)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("latest", help="Print latest run label")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_latest)

    p = sub.add_parser("paths", help="Print artifact paths for a run")
    p.add_argument("run", nargs="?", default=None)
    p.add_argument("--json", action="store_true")
    p.add_argument("--export", action="store_true",
                     help="Print shell export statements")
    p.set_defaults(func=cmd_paths)

    p = sub.add_parser("search", help="Search cards, clusters, bundles (and transcripts with --full)")
    p.add_argument("query", help="Search text (substring or --regex)")
    p.add_argument("--run", default=None, help="Run label (default: latest)")
    p.add_argument("--scope", choices=("all", "cards", "clusters", "bundles", "transcripts"),
                   default="all")
    p.add_argument("--full", action="store_true",
                   help="Also grep transcript bodies (slower)")
    p.add_argument("--regex", action="store_true")
    p.add_argument("--min-versions", type=int, default=0)
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("cards", help="List or search conversation cards")
    p.add_argument("--run", default=None)
    p.add_argument("--search", default=None, metavar="QUERY")
    p.add_argument("--regex", action="store_true")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_cards)

    p = sub.add_parser("clusters", help="List or search project clusters")
    p.add_argument("--run", default=None)
    p.add_argument("--search", default=None, metavar="QUERY")
    p.add_argument("--regex", action="store_true")
    p.add_argument("--min-versions", type=int, default=0)
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_clusters)

    p = sub.add_parser("bundles", help="List or search LLM bundles")
    p.add_argument("--run", default=None)
    p.add_argument("--search", default=None, metavar="QUERY")
    p.add_argument("--regex", action="store_true")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_bundles)

    p = sub.add_parser("migrate", help="Move legacy output/ into runs/<label>/")
    p.add_argument("--label", default=None,
                   help="Run label (default: legacy-YYYYMMDD from mtime)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--copy", action="store_true",
                   help="Copy instead of move (keep legacy layout)")
    p.set_defaults(func=cmd_migrate)

    p = sub.add_parser("summary", help="Regenerate RUN_SUMMARY for a run")
    p.add_argument("run", nargs="?", default=None)
    p.set_defaults(func=cmd_summary)

    args = ap.parse_args()
    if not hasattr(args, "func"):
        ap.print_help()
        return 0
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
