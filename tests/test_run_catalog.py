"""Tests for run catalog and legacy migration."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "lib"))
import paths  # noqa: E402
import run_catalog  # noqa: E402


class RunCatalogTest(unittest.TestCase):
    def _legacy_tree(self, base: str) -> None:
        store = os.path.join(base, "store")
        os.makedirs(os.path.join(store, "transcripts"), exist_ok=True)
        index = {
            "id1": {
                "id": "id1",
                "title": "ADOS Arena project",
                "update_time": 100.0,
                "slug_votes": {"ados-arena": 3},
            },
            "id2": {
                "id": "id2",
                "title": "Chess skill notes",
                "update_time": 200.0,
                "slug_votes": {"chess-skill": 1},
            },
        }
        with open(os.path.join(store, "index.json"), "w", encoding="utf-8") as f:
            json.dump(index, f)
        with open(os.path.join(store, "cards.jsonl"), "w", encoding="utf-8") as f:
            for v in index.values():
                f.write(json.dumps(v) + "\n")
        clusters = [
            {"slug": "ados-arena", "titles": ["ADOS Arena project"],
             "n_conversations": 2, "n_versions": 1, "member_ids": ["id1"],
             "start_date": "2026-01-01", "end_date": "2026-02-01",
             "version_zip_files": [], "file_artifacts": []},
        ]
        with open(os.path.join(store, "clusters.json"), "w", encoding="utf-8") as f:
            json.dump(clusters, f)
        bundles = os.path.join(base, "bundles")
        os.makedirs(bundles, exist_ok=True)
        with open(os.path.join(bundles, "ados-arena.md"), "w", encoding="utf-8") as f:
            f.write("# bundle\n")
        with open(os.path.join(base, "reconstructed_projects.json"), "w", encoding="utf-8") as f:
            json.dump({"n_projects": 1, "projects": []}, f)

    def test_migrate_legacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._legacy_tree(tmp)
            with patch.dict(os.environ, {"RECONSTRUCTOR_DATA_ROOT": tmp}):
                plan = run_catalog.migrate_legacy_output("test-legacy", dry_run=False)
                self.assertEqual(plan["label"], "test-legacy")
                dest = paths.run_root("test-legacy")
                self.assertTrue(os.path.isdir(os.path.join(dest, "store")))
                self.assertTrue(os.path.isfile(
                    os.path.join(dest, "reconstructed_projects.json")))
                self.assertFalse(os.path.isdir(os.path.join(tmp, "store")))
                catalog = run_catalog.load_catalog()
                self.assertEqual(catalog.get("latest"), "test-legacy")

    def test_search_cards(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._legacy_tree(tmp)
            store = os.path.join(tmp, "store")
            hits = run_catalog.search_cards(store, "ados")
            self.assertEqual(len(hits), 1)
            self.assertIn("ADOS", hits[0]["title"])

    def test_search_clusters(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._legacy_tree(tmp)
            store = os.path.join(tmp, "store")
            hits = run_catalog.search_clusters(store, "ados")
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0]["slug"], "ados-arena")

    def test_list_runs_from_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"RECONSTRUCTOR_DATA_ROOT": tmp}):
                os.makedirs(paths.run_root("r1"), exist_ok=True)
                run_catalog.register_run("r1", source="test")
                runs = run_catalog.list_runs()
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0]["label"], "r1")


if __name__ == "__main__":
    unittest.main()
