"""Resolve data paths from RECONSTRUCTOR_DATA_ROOT env or local config."""
from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_local_config() -> dict:
    path = os.path.join(ROOT, "config", "reconstruct.config.local.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def data_root() -> str | None:
    env = os.environ.get("RECONSTRUCTOR_DATA_ROOT")
    if env:
        return os.path.expanduser(env)
    cfg = _load_local_config()
    root = cfg.get("data_root")
    if root:
        return os.path.expanduser(str(root))
    return None


def store_dir(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    root = data_root()
    if root:
        return os.path.join(root, "store")
    return os.path.join(ROOT, "output", "store")


def bundles_dir(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    root = data_root()
    if root:
        return os.path.join(root, "bundles")
    return os.path.join(ROOT, "output", "bundles")


def reconstructed_json(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    root = data_root()
    if root:
        return os.path.join(root, "reconstructed_projects.json")
    return os.path.join(ROOT, "output", "reconstructed_projects.json")


def published_json(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    return os.path.join(ROOT, "published", "projects.json")
