"""
run_catalog.py — run registry, legacy migration, and search over pipeline extracts.
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import re
import shutil
from typing import Any, Iterator

import paths

SCHEMA_VERSION = 1


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _read_json(path: str, default: Any = None) -> Any:
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _dir_mtime(path: str) -> dt.datetime | None:
    if not os.path.exists(path):
        return None
    return dt.datetime.fromtimestamp(os.path.getmtime(path), tz=dt.timezone.utc)


def _default_legacy_label() -> str:
    legacy = paths.legacy_layout_paths()
    for key in ("reconstructed", "store"):
        p = legacy[key] if key != "store" else os.path.join(legacy["store"], "clusters.json")
        m = _dir_mtime(p)
        if m:
            return f"legacy-{m.strftime('%Y%m%d')}"
    return f"legacy-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d')}"


def run_paths(label: str) -> dict[str, str]:
    """Resolved artifact paths for a labeled run."""
    root = paths.run_root(label)
    return {
        "root": root,
        "store": paths.store_dir(run_label=label),
        "bundles": paths.bundles_dir(run_label=label),
        "reconstructed": paths.reconstructed_json(run_label=label),
        "manifest": paths.run_manifest_path(label),
    }


def load_catalog() -> dict[str, Any]:
    data = _read_json(paths.catalog_path(), default=None)
    if not data:
        return {"schema_version": SCHEMA_VERSION, "runs": [], "latest": None}
    return data


def save_catalog(catalog: dict[str, Any]) -> None:
    catalog["schema_version"] = SCHEMA_VERSION
    _write_json(paths.catalog_path(), catalog)


def load_run_manifest(label: str) -> dict[str, Any] | None:
    return _read_json(paths.run_manifest_path(label), default=None)


def save_run_manifest(label: str, manifest: dict[str, Any]) -> None:
    manifest.setdefault("schema_version", SCHEMA_VERSION)
    manifest.setdefault("label", label)
    manifest["updated_utc"] = _now_iso()
    _write_json(paths.run_manifest_path(label), manifest)


def _collect_run_stats(root: str) -> dict[str, Any]:
    sys_path = os.path.join(os.path.dirname(__file__), "..")
    if sys_path not in __import__("sys").path:
        __import__("sys").path.insert(0, sys_path)
    from collect_run_stats import collect  # noqa: WPS433
    return collect(root)


def build_run_manifest(label: str, *, source: str = "pipeline",
                       notes: str = "") -> dict[str, Any]:
    rp = run_paths(label)
    root = rp["root"]
    stats = _collect_run_stats(root) if os.path.isdir(root) else {}
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "label": label,
        "created_utc": _now_iso(),
        "updated_utc": _now_iso(),
        "source": source,
        "notes": notes,
        "paths": rp,
        "stats": {
            k: stats[k]
            for k in (
                "index_records", "cards", "transcripts", "clusters",
                "clusters_with_version_zip", "bundles", "n_projects",
                "generated_by", "disk_bytes", "stage1_3_seconds",
                "stage4_seconds", "total_wall_seconds", "mtimes",
            )
            if k in stats
        },
    }
    rec = rp["reconstructed"]
    if os.path.exists(rec):
        manifest["has_reconstructed"] = True
    return manifest


def register_run(label: str, *, source: str = "pipeline", notes: str = "",
                 set_latest: bool = True) -> dict[str, Any]:
    catalog = load_catalog()
    manifest = build_run_manifest(label, source=source, notes=notes)
    save_run_manifest(label, manifest)

    entry = {
        "label": label,
        "source": source,
        "updated_utc": manifest["updated_utc"],
        "stats": manifest.get("stats", {}),
        "has_reconstructed": manifest.get("has_reconstructed", False),
    }
    runs = [r for r in catalog.get("runs", []) if r.get("label") != label]
    runs.append(entry)
    runs.sort(key=lambda r: r.get("updated_utc") or "", reverse=True)
    catalog["runs"] = runs
    if set_latest:
        catalog["latest"] = label
        paths.update_latest_pointer(label)
    save_catalog(catalog)
    return manifest


def list_runs() -> list[dict[str, Any]]:
    catalog = load_catalog()
    runs = catalog.get("runs") or []
    if runs:
        return runs
    # Fall back to scanning runs/ directory
    discovered = []
    runs_root = paths.runs_dir()
    if not os.path.isdir(runs_root):
        return []
    for name in sorted(os.listdir(runs_root)):
        if name in ("catalog.json", "latest"):
            continue
        rp = run_paths(name)
        if os.path.isdir(rp["store"]) or os.path.isdir(rp["root"]):
            manifest = load_run_manifest(name)
            discovered.append({
                "label": name,
                "source": (manifest or {}).get("source", "unknown"),
                "updated_utc": (manifest or {}).get("updated_utc"),
                "stats": (manifest or {}).get("stats", {}),
                "has_reconstructed": (manifest or {}).get("has_reconstructed", False),
            })
    discovered.sort(key=lambda r: r.get("updated_utc") or "", reverse=True)
    return discovered


def get_run(label: str | None = None) -> dict[str, Any]:
    resolved = paths.resolve_run_label(label) or label
    if not resolved:
        raise FileNotFoundError("No runs found. Run ./run.sh --run-label NAME or migrate legacy output.")
    rp = run_paths(resolved)
    if not os.path.isdir(rp["root"]):
        raise FileNotFoundError(f"Run not found: {resolved}")
    manifest = load_run_manifest(resolved) or build_run_manifest(resolved)
    manifest["paths"] = rp
    manifest["label"] = resolved
    return manifest


def _load_cards(store: str) -> list[dict]:
    cards_path = os.path.join(store, "cards.jsonl")
    if not os.path.isfile(cards_path):
        index_path = os.path.join(store, "index.json")
        index = _read_json(index_path, default={})
        return list(index.values()) if isinstance(index, dict) else []
    cards = []
    with open(cards_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cards.append(json.loads(line))
    return cards


def _load_clusters(store: str) -> list[dict]:
    return _read_json(os.path.join(store, "clusters.json"), default=[]) or []


def _match_query(text: str, query: str, regex: bool) -> bool:
    if not text:
        return False
    if regex:
        try:
            return bool(re.search(query, text, re.I))
        except re.error:
            return query.lower() in text.lower()
    return query.lower() in text.lower()


def search_cards(store: str, query: str, *, regex: bool = False,
                 limit: int = 50) -> list[dict]:
    results = []
    for card in _load_cards(store):
        hay = " ".join(filter(None, [
            card.get("title", ""),
            card.get("id", ""),
            " ".join(card.get("slug_votes") or {}),
            " ".join(z.get("filename", "") for z in card.get("zip_files") or []),
        ]))
        if _match_query(hay, query, regex):
            results.append({
                "kind": "card",
                "id": card.get("id"),
                "title": card.get("title"),
                "create_date": card.get("create_date"),
                "update_date": card.get("update_date"),
                "n_turns": card.get("n_turns"),
                "slug_votes": card.get("slug_votes"),
            })
            if len(results) >= limit:
                break
    return results


def search_clusters(store: str, query: str, *, regex: bool = False,
                    min_versions: int = 0, limit: int = 50) -> list[dict]:
    results = []
    for c in _load_clusters(store):
        if c.get("n_versions", 0) < min_versions:
            continue
        hay = " ".join(filter(None, [
            c.get("slug", ""),
            " ".join(c.get("titles") or []),
        ]))
        if _match_query(hay, query, regex):
            results.append({
                "kind": "cluster",
                "slug": c.get("slug"),
                "titles": c.get("titles"),
                "n_conversations": c.get("n_conversations"),
                "n_versions": c.get("n_versions"),
                "start_date": c.get("start_date"),
                "end_date": c.get("end_date"),
            })
            if len(results) >= limit:
                break
    return results


def search_bundles(bundles_dir: str, query: str, *, regex: bool = False,
                   limit: int = 50) -> list[dict]:
    results = []
    if not os.path.isdir(bundles_dir):
        return results
    for path in sorted(glob.glob(os.path.join(bundles_dir, "*.md"))):
        slug = os.path.splitext(os.path.basename(path))[0]
        if _match_query(slug, query, regex):
            try:
                size = os.path.getsize(path)
            except OSError:
                size = 0
            results.append({
                "kind": "bundle",
                "slug": slug,
                "path": path,
                "chars": size,
            })
            if len(results) >= limit:
                break
    return results


def search_transcripts(store: str, query: str, *, regex: bool = False,
                       limit: int = 20) -> list[dict]:
    """Full-text search in transcript bodies (slower)."""
    tdir = os.path.join(store, "transcripts")
    index = _read_json(os.path.join(store, "index.json"), default={}) or {}
    results = []
    if not os.path.isdir(tdir):
        return results
    pattern = re.compile(query, re.I) if regex else None
    q_lower = query.lower()
    for fname in sorted(os.listdir(tdir)):
        if not fname.endswith(".txt"):
            continue
        cid = fname[:-4]
        path = os.path.join(tdir, fname)
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                body = f.read()
        except OSError:
            continue
        if pattern:
            if not pattern.search(body):
                continue
        elif q_lower not in body.lower():
            continue
        meta = index.get(cid, {})
        snippet = body[:200].replace("\n", " ")
        results.append({
            "kind": "transcript",
            "id": cid,
            "title": meta.get("title"),
            "path": path,
            "snippet": snippet + ("…" if len(body) > 200 else ""),
        })
        if len(results) >= limit:
            break
    return results


def search_run(label: str, query: str, *, scope: str = "all",
               regex: bool = False, full: bool = False,
               min_versions: int = 0, limit: int = 50) -> dict[str, list]:
    run = get_run(label)
    store = run["paths"]["store"]
    bundles = run["paths"]["bundles"]
    out: dict[str, list] = {}
    if scope in ("all", "cards"):
        out["cards"] = search_cards(store, query, regex=regex, limit=limit)
    if scope in ("all", "clusters"):
        out["clusters"] = search_clusters(
            store, query, regex=regex, min_versions=min_versions, limit=limit)
    if scope in ("all", "bundles"):
        out["bundles"] = search_bundles(bundles, query, regex=regex, limit=limit)
    if full and scope in ("all", "transcripts"):
        out["transcripts"] = search_transcripts(
            store, query, regex=regex, limit=min(limit, 20))
    return out


def migrate_legacy_output(label: str | None = None, *, dry_run: bool = False,
                          copy: bool = False) -> dict[str, Any]:
    """
    Move legacy output/{store,bundles,reconstructed_projects.json,...}
    into output/runs/<label>/ and register in catalog.
    """
    if not paths.legacy_output_detected():
        raise FileNotFoundError(
            "No legacy output detected (expected output/store/index.json with data)."
        )

    label = label or _default_legacy_label()
    dest_root = paths.run_root(label)
    if os.path.exists(dest_root) and os.listdir(dest_root):
        raise FileExistsError(
            f"Run directory already exists and is non-empty: {dest_root}. "
            f"Choose another --label."
        )

    legacy = paths.legacy_layout_paths()
    base = legacy["base"]
    moves: list[tuple[str, str]] = []

    for name in ("store", "bundles"):
        src = legacy[name]
        if os.path.isdir(src):
            moves.append((src, os.path.join(dest_root, name)))

    for src_name, dest_name in (
        ("reconstructed", "reconstructed_projects.json"),
    ):
        src = legacy[src_name]
        if os.path.isfile(src):
            moves.append((src, os.path.join(dest_root, dest_name)))

    for pattern in ("RUN_SUMMARY_*.md", "RUN_COMMANDS.log", "RUN_COMMANDS.txt",
                    ".run_manifest.json"):
        for src in glob.glob(os.path.join(base, pattern)):
            moves.append((src, os.path.join(dest_root, os.path.basename(src))))

    plan = {
        "label": label,
        "dest_root": dest_root,
        "moves": [{"from": s, "to": d} for s, d in moves],
        "dry_run": dry_run,
        "copy": copy,
    }

    if dry_run:
        return plan

    os.makedirs(dest_root, exist_ok=True)
    op = shutil.copytree if copy else shutil.move

    for src, dest in moves:
        if os.path.isdir(src):
            if copy:
                shutil.copytree(src, dest, dirs_exist_ok=False)
            else:
                shutil.move(src, dest)
        elif os.path.isfile(src):
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            if copy:
                shutil.copy2(src, dest)
            else:
                shutil.move(src, dest)

    # Leave pointer at legacy root
    readme = os.path.join(base, "LEGACY_MIGRATED.txt")
    with open(readme, "w", encoding="utf-8") as f:
        f.write(
            f"Legacy pipeline output was migrated to runs/{label}/\n"
            f"Migrated at: {_now_iso()}\n"
            f"Browse runs: ./runs.sh list\n"
            f"Use run:       ./runs.sh paths {label}\n"
        )

    manifest = register_run(
        label,
        source="migrated_legacy",
        notes=f"Migrated from {base}",
        set_latest=True,
    )
    plan["manifest"] = manifest
    return plan


def format_run_list(runs: list[dict], *, latest: str | None = None) -> str:
    if not runs:
        return "No runs found.\n  Create one: ./run.sh --zip export.zip --run-label myrun\n  Or migrate: ./runs.sh migrate"
    lines = [
        f"{'LABEL':<28} {'CARDS':>6} {'CLUST':>6} {'BNDL':>6} {'PROJ':>6}  SOURCE",
        "-" * 72,
    ]
    for r in runs:
        st = r.get("stats") or {}
        tag = " *" if r.get("label") == latest else ""
        lines.append(
            f"{r.get('label', '?') + tag:<28} "
            f"{st.get('index_records', st.get('cards', 0)) or 0:>6} "
            f"{st.get('clusters', 0) or 0:>6} "
            f"{st.get('bundles', 0) or 0:>6} "
            f"{st.get('n_projects', 0) or 0:>6}  "
            f"{r.get('source', '')}"
        )
    lines.append("")
    lines.append("* = latest")
    return "\n".join(lines)


def format_run_show(manifest: dict) -> str:
    label = manifest.get("label", "?")
    rp = manifest.get("paths") or run_paths(label)
    st = manifest.get("stats") or {}
    lines = [
        f"# Run: {label}",
        "",
        f"- Source: {manifest.get('source', 'unknown')}",
        f"- Updated: {manifest.get('updated_utc', 'n/a')}",
        f"- Root: `{rp.get('root')}`",
        "",
        "## Stats",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
    ]
    for key, lbl in (
        ("index_records", "Conversations"),
        ("clusters", "Clusters"),
        ("clusters_with_version_zip", "Clusters w/ version zip"),
        ("bundles", "Bundles"),
        ("n_projects", "Reconstructed projects"),
        ("generated_by", "Stage 4 model"),
    ):
        if key in st:
            lines.append(f"| {lbl} | {st[key]} |")
    lines += [
        "",
        "## Commands",
        "",
        "```bash",
        f"./runs.sh search --run {label} ados",
        f"./runs.sh cards --run {label} --limit 20",
        f"./ollama.sh --run-label {label}",
        f"python scripts/export_public.py --review  # after Stage 4",
        "```",
        "",
        "## Paths",
        "",
    ]
    for k, v in rp.items():
        lines.append(f"- `{k}`: `{v}`")
    return "\n".join(lines)


def format_search_results(label: str, query: str, results: dict[str, list]) -> str:
    lines = [f"# Search `{query}` in run `{label}`", ""]
    total = sum(len(v) for v in results.values())
    if total == 0:
        lines.append("_No matches._")
        return "\n".join(lines)
    for section, items in results.items():
        if not items:
            continue
        lines.append(f"## {section} ({len(items)})")
        lines.append("")
        for item in items:
            if section == "cards":
                lines.append(
                    f"- **{item.get('title', '?')}** `{item.get('id', '')[:8]}…` "
                    f"({item.get('create_date')}) turns={item.get('n_turns')}"
                )
            elif section == "clusters":
                titles = (item.get("titles") or [""])[0]
                lines.append(
                    f"- **{item.get('slug')}** — {titles} "
                    f"(convs={item.get('n_conversations')}, "
                    f"versions={item.get('n_versions')})"
                )
            elif section == "bundles":
                lines.append(
                    f"- **{item.get('slug')}** ({item.get('chars', 0):,} chars)"
                )
            elif section == "transcripts":
                lines.append(
                    f"- **{item.get('title', '?')}** `{item.get('id', '')[:8]}…`"
                )
                lines.append(f"  > {item.get('snippet', '')}")
        lines.append("")
    return "\n".join(lines)
