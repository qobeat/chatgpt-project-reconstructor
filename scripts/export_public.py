#!/usr/bin/env python3
"""
export_public.py — sanitize full reconstructed_projects.json for GitHub.

Strips conversation provenance, normalizes zip paths to basenames, and optionally
writes per-project markdown under published/projects/.

Usage:
  python scripts/export_public.py
  python scripts/export_public.py --in ~/chatgpt-reconstructor-data/reconstructed_projects.json \\
      --out published/projects.json --md --review
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))
import paths  # noqa: E402

STRIP_FIELDS = frozenset({
    "source_conversation_ids",
    "member_ids",
})

PII_PATTERNS = [
    (re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"), "email"),
    (re.compile(r"/Users/[^\s\"']+"), "macOS home path"),
    (re.compile(r"/mnt/c/Users/[^\s\"']+"), "Windows user path"),
    (re.compile(r"\\Users\\[^\s\"']+"), "Windows backslash path"),
    (re.compile(r"source_conversation_ids"), "conversation id field"),
]


def basename_only(name: str) -> str:
    return os.path.basename(name.replace("\\", "/"))


def sanitize_project(project: dict) -> dict:
    out = {k: v for k, v in project.items() if k not in STRIP_FIELDS}
    zips = out.get("version_zip_files") or []
    cleaned = []
    for z in zips:
        if isinstance(z, dict):
            entry = dict(z)
            if "filename" in entry:
                entry["filename"] = basename_only(str(entry["filename"]))
            cleaned.append(entry)
        elif isinstance(z, str):
            cleaned.append({"filename": basename_only(z)})
    out["version_zip_files"] = cleaned
    return out


def sanitize_document(doc: dict) -> dict:
    projects = [sanitize_project(p) for p in doc.get("projects", [])]
    return {
        "generated_by": doc.get("generated_by", "export_public.py"),
        "n_projects": len(projects),
        "projects": projects,
    }


def review_text(label: str, text: str) -> list[str]:
    findings = []
    for pattern, kind in PII_PATTERNS:
        for match in pattern.finditer(text):
            findings.append(f"{label}: possible {kind}: {match.group()[:80]}")
    return findings


def review_document(doc: dict) -> list[str]:
    findings: list[str] = []
    raw = json.dumps(doc, ensure_ascii=False)
    findings.extend(review_text("document", raw))
    for p in doc.get("projects", []):
        slug = p.get("slug", "?")
        for field in ("goal", "how_to_use", "use_case", "quickstart", "how_to_update"):
            val = p.get(field)
            if isinstance(val, str) and val.strip():
                findings.extend(review_text(f"{slug}.{field}", val))
        for obj in p.get("objectives") or []:
            if isinstance(obj, str):
                findings.extend(review_text(f"{slug}.objectives", obj))
        for req in p.get("requirements") or []:
            if isinstance(req, str):
                findings.extend(review_text(f"{slug}.requirements", req))
    return findings


def project_to_markdown(project: dict) -> str:
    slug = project.get("slug", "unknown")
    lines = [
        f"# {project.get('project_name', slug)}",
        "",
        f"**Slug:** `{slug}`",
    ]
    if project.get("start_date") or project.get("end_date"):
        lines.append(
            f"**Dates:** {project.get('start_date') or '?'} → "
            f"{project.get('end_date') or '?'}"
        )
    lines += [
        f"**Versions:** {project.get('n_versions', 0)} "
        f"({project.get('n_conversations', 0)} conversations)",
        "",
        "## Goal",
        "",
        project.get("goal") or "_Not set._",
        "",
    ]
    if project.get("objectives"):
        lines += ["## Objectives", ""]
        lines += [f"- {o}" for o in project["objectives"]]
        lines.append("")
    if project.get("requirements"):
        lines += ["## Requirements", ""]
        lines += [f"- {r}" for r in project["requirements"]]
        lines.append("")
    if project.get("requirements_evolution"):
        lines += ["## Requirements evolution", ""]
        for ev in project["requirements_evolution"]:
            date = ev.get("date") or "?"
            change = ev.get("change", "")
            lines.append(f"- **{date}:** {change}")
        lines.append("")
    for title, key in (
        ("Quickstart", "quickstart"),
        ("How to use", "how_to_use"),
        ("Use case", "use_case"),
        ("How to update", "how_to_update"),
    ):
        val = project.get(key)
        if val:
            lines += [f"## {title}", "", val, ""]
    zips = project.get("version_zip_files") or []
    if zips:
        lines += ["## Version archives", ""]
        for z in zips:
            fn = z.get("filename") if isinstance(z, dict) else str(z)
            ver = z.get("version") if isinstance(z, dict) else None
            suffix = f" (v{ver})" if ver else ""
            lines.append(f"- `{fn}`{suffix}")
        lines.append("")
    arts = project.get("file_artifacts") or []
    if arts:
        lines += ["## File artifacts", ""]
        lines += [f"- `{a}`" for a in arts]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Export sanitized project summaries for GitHub.")
    ap.add_argument("--in", dest="in_path", default=None,
                    help="Full reconstructed_projects.json (default: from paths).")
    ap.add_argument("--out", dest="out_path", default=None,
                    help="Output JSON (default: published/projects.json).")
    ap.add_argument("--md", action="store_true",
                    help="Also write published/projects/<slug>.md per project.")
    ap.add_argument("--review", action="store_true",
                    help="Print PII/path warnings; exit 1 if any found.")
    args = ap.parse_args()

    in_path = paths.reconstructed_json(args.in_path)
    out_path = paths.published_json(args.out_path)

    if not os.path.exists(in_path):
        sys.stderr.write(f"[error] Input not found: {in_path}\n")
        return 1

    with open(in_path, "r", encoding="utf-8") as f:
        doc = json.load(f)

    public = sanitize_document(doc)
    public["generated_by"] = f"export_public.py (from {os.path.basename(in_path)})"

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(public, f, ensure_ascii=False, indent=2)
    sys.stderr.write(f"[export] Wrote {out_path} ({public['n_projects']} projects)\n")

    if args.md:
        md_dir = os.path.join(os.path.dirname(out_path), "projects")
        os.makedirs(md_dir, exist_ok=True)
        for p in public["projects"]:
            slug = p.get("slug", "unknown")
            md_path = os.path.join(md_dir, f"{slug}.md")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(project_to_markdown(p))
            sys.stderr.write(f"[export] Wrote {md_path}\n")

    if args.review:
        findings = review_document(public)
        if findings:
            sys.stderr.write("[review] Possible personal data — fix before git push:\n")
            for line in findings:
                sys.stderr.write(f"  - {line}\n")
            return 1
        sys.stderr.write("[review] No obvious PII patterns detected.\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
