#!/usr/bin/env python3
"""
cluster_projects.py  (Stage 2 — deterministic, zero-LLM)

Group conversation cards into project clusters using a union-find over shared
slugs (zip-basename slugs are strong; title slugs are weak tie-breakers).
Emits output/store/clusters.json: a list of clusters, each with the
deterministic facts an LLM should NOT have to infer (dates, version zips,
file artifacts, member conversation ids).

Usage:
  python scripts/cluster_projects.py --store output/store \
      [--min-slug-votes 3]
"""
from __future__ import annotations
import argparse
import json
import os
from collections import defaultdict
from typing import Dict, List


class UnionFind:
    def __init__(self):
        self.parent: Dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def primary_slug(card: dict, min_votes: int) -> str:
    votes = card.get("slug_votes") or {}
    if not votes:
        return slug_fallback(card)
    # prefer strongest vote; require min_votes else fall back to title slug
    best = max(votes.items(), key=lambda kv: kv[1])
    if best[1] >= min_votes:
        return best[0]
    return slug_fallback(card)


def slug_fallback(card: dict) -> str:
    votes = card.get("slug_votes") or {}
    if votes:
        return max(votes.items(), key=lambda kv: kv[1])[0]
    return "unclustered-" + card["id"][:8]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", default="output/store")
    ap.add_argument("--min-slug-votes", type=int, default=3)
    args = ap.parse_args()

    cards_path = os.path.join(args.store, "cards.jsonl")
    cards: List[dict] = []
    with open(cards_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cards.append(json.loads(line))

    uf = UnionFind()
    # link any two cards that share any strong (zip) slug
    slug_to_cards: Dict[str, List[str]] = defaultdict(list)
    card_primary: Dict[str, str] = {}
    for c in cards:
        cid = c["id"]
        card_primary[cid] = primary_slug(c, args.min_slug_votes)
        strong = {z["slug"] for z in (c.get("zip_files") or []) if z.get("slug")}
        if not strong:
            strong = {card_primary[cid]}
        for s in strong:
            slug_to_cards[s].append(cid)
    for s, ids in slug_to_cards.items():
        for other in ids[1:]:
            uf.union(ids[0], other)
    # also union cards that share the same primary slug
    by_primary: Dict[str, List[str]] = defaultdict(list)
    for cid, s in card_primary.items():
        by_primary[s].append(cid)
    for s, ids in by_primary.items():
        for other in ids[1:]:
            uf.union(ids[0], other)

    groups: Dict[str, List[dict]] = defaultdict(list)
    by_id = {c["id"]: c for c in cards}
    for c in cards:
        groups[uf.find(c["id"])].append(c)

    clusters = []
    for root, members in groups.items():
        members.sort(key=lambda c: c.get("create_time") or 0)
        # choose canonical slug = most common primary among members
        slug_counts: Dict[str, int] = defaultdict(int)
        for m in members:
            slug_counts[card_primary[m["id"]]] += 1
        slug = max(slug_counts.items(), key=lambda kv: kv[1])[0]

        zips: Dict[str, dict] = {}
        files: set = set()
        for m in members:
            for z in m.get("zip_files") or []:
                zips.setdefault(z["filename"].lower(), z)
            files.update(m.get("file_artifacts") or [])
        zip_list = sorted(zips.values(), key=lambda z: (z.get("version") or "", z["filename"]))

        dates = [m.get("create_date") for m in members if m.get("create_date")]
        clusters.append({
            "slug": slug,
            "member_ids": [m["id"] for m in members],
            "titles": [m["title"] for m in members],
            "start_date": min(dates) if dates else None,
            "end_date": max(dates) if dates else None,
            "n_conversations": len(members),
            "version_zip_files": zip_list,
            "n_versions": len(zip_list),
            "file_artifacts": sorted(files),
        })

    clusters.sort(key=lambda c: (-c["n_conversations"], c["slug"]))
    out = os.path.join(args.store, "clusters.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(clusters, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(clusters)} clusters -> {out}")
    for c in clusters[:15]:
        print(f"  {c['slug']:<28} convs={c['n_conversations']:<3} "
              f"versions={c['n_versions']:<3} {c['start_date']}..{c['end_date']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
