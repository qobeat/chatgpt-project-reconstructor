#!/usr/bin/env python3
"""
extract_cards.py  (Stage 1 — deterministic, zero-LLM)

Stream a ChatGPT export .zip and, per conversation, emit:
  * a compact "card" (title, slug candidates, dates, zip filenames, file
    artifacts, version tokens) -> output/store/cards.jsonl
  * a reduced, code-stripped transcript -> output/store/transcripts/<id>.txt
  * an incremental index keyed by conversation id (handles future exports;
    newer update_time wins) -> output/store/index.json

This pass NEVER calls an LLM and NEVER loads the whole JSON into memory.

Usage:
  python scripts/extract_cards.py --zip /path/a.zip [--zip /path/b.zip ...] \
      --out output/store [--keywords-file config/reconstruct.config.json]
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import re
import sys
from typing import Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))
from chatgpt_parse import (  # noqa: E402
    iter_conversations,
    active_path_nodes,
    message_text,
    conversation_dates,
    reduce_assistant_text,
)

ZIP_RE = re.compile(r"[\w][\w.\-]*?\.zip", re.I)
FILE_RE = re.compile(
    r"\b[\w\-./]+\.(?:py|ps1|psm1|md|json|jsonl|sh|ts|js|tsx|jsx|"
    r"yaml|yml|toml|sql|txt|csv|ipynb|cfg|ini|rs|go|c|cpp|h)\b",
    re.I,
)
HEX_RE = re.compile(r"\b[0-9a-f]{8,}\b", re.I)
DATE_RE = re.compile(r"\b\d{4}[-_]\d{2}[-_]\d{2}\b")
VER_RE = re.compile(r"[-_ ]?v?(\d+(?:[._]\d+){0,3})\b", re.I)
SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def epoch_to_date(ts: Optional[float]) -> Optional[str]:
    if not ts:
        return None
    try:
        return dt.datetime.fromtimestamp(float(ts), dt.timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return None


def slug_from_zip(name: str) -> str:
    base = re.sub(r"\.zip$", "", name, flags=re.I)
    base = HEX_RE.sub("", base)
    base = DATE_RE.sub("", base)
    base = VER_RE.sub("", base)
    base = SLUG_STRIP.sub("-", base.lower()).strip("-")
    base = re.sub(r"-{2,}", "-", base)
    return base


def slug_from_title(title: str) -> str:
    s = SLUG_STRIP.sub("-", (title or "").lower()).strip("-")
    return re.sub(r"-{2,}", "-", s)


def version_of_zip(name: str) -> Optional[str]:
    m = VER_RE.search(re.sub(r"\.zip$", "", name, flags=re.I))
    return m.group(1).replace("_", ".") if m else None


def build_card(conv: dict) -> Optional[dict]:
    cid = conv.get("id") or conv.get("conversation_id")
    if not cid:
        return None
    title = conv.get("title") or "untitled"
    ct, ut = conversation_dates(conv)
    nodes = active_path_nodes(conv)

    transcript_lines: List[str] = []
    zips: Dict[str, dict] = {}
    files: set = set()
    full_text_buf: List[str] = []

    for node in nodes:
        role, text, ctype = message_text(node.get("message") or {})
        if role not in ("user", "assistant") or not text:
            continue
        full_text_buf.append(text)
        if role == "assistant":
            red = reduce_assistant_text(text)
            transcript_lines.append(f"[assistant] {red}")
        else:
            transcript_lines.append(f"[user] {text.strip()}")

    blob = "\n".join(full_text_buf)
    for m in ZIP_RE.finditer(blob):
        zname = m.group(0)
        if zname.lower() in zips:
            continue
        zips[zname.lower()] = {
            "filename": zname,
            "slug": slug_from_zip(zname),
            "version": version_of_zip(zname),
        }
    for m in FILE_RE.finditer(blob):
        files.add(m.group(0))

    # candidate slugs: from zip basenames (strong) + title (weak)
    slug_votes: Dict[str, int] = {}
    for z in zips.values():
        if z["slug"]:
            slug_votes[z["slug"]] = slug_votes.get(z["slug"], 0) + 3
    ts = slug_from_title(title)
    if ts:
        slug_votes[ts] = slug_votes.get(ts, 0) + 1

    return {
        "id": cid,
        "title": title,
        "create_date": epoch_to_date(ct),
        "update_date": epoch_to_date(ut),
        "create_time": ct,
        "update_time": ut,
        "zip_files": list(zips.values()),
        "file_artifacts": sorted(files),
        "slug_votes": slug_votes,
        "transcript": "\n\n".join(transcript_lines),
        "n_turns": len(transcript_lines),
    }


def load_index(path: str) -> dict:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", action="append", required=True, dest="zips")
    ap.add_argument("--out", default="output/store")
    args = ap.parse_args()

    tdir = os.path.join(args.out, "transcripts")
    os.makedirs(tdir, exist_ok=True)
    index_path = os.path.join(args.out, "index.json")
    cards_path = os.path.join(args.out, "cards.jsonl")
    index = load_index(index_path)

    added, updated, skipped = 0, 0, 0
    for zp in args.zips:
        if not os.path.exists(zp):
            sys.stderr.write(f"[skip] missing: {zp}\n")
            continue
        sys.stderr.write(f"[scan] {zp}\n")
        for conv in iter_conversations(zp):
            card = build_card(conv)
            if not card:
                continue
            cid = card["id"]
            prev = index.get(cid)
            if prev and (prev.get("update_time") or 0) >= (card["update_time"] or 0):
                skipped += 1
                continue
            # write transcript
            with open(os.path.join(tdir, f"{cid}.txt"), "w", encoding="utf-8") as f:
                f.write(card["transcript"])
            meta = {k: v for k, v in card.items() if k != "transcript"}
            meta["source_zip"] = os.path.basename(zp)
            if prev:
                updated += 1
            else:
                added += 1
            index[cid] = meta

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    with open(cards_path, "w", encoding="utf-8") as f:
        for cid, meta in index.items():
            f.write(json.dumps(meta, ensure_ascii=False) + "\n")

    sys.stderr.write(
        f"[done] added={added} updated={updated} skipped={skipped} "
        f"total={len(index)}\n  index: {index_path}\n  cards: {cards_path}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
