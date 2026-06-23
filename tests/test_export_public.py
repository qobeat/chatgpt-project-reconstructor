"""Unit tests for scripts/export_public.py sanitization."""
from __future__ import annotations

import importlib.util
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
SCRIPTS = os.path.join(ROOT, "scripts")


def _load_export_public():
    spec = importlib.util.spec_from_file_location(
        "export_public",
        os.path.join(SCRIPTS, "export_public.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


ep = _load_export_public()

SAMPLE = {
    "generated_by": "test",
    "n_projects": 1,
    "projects": [
        {
            "project_name": "Demo",
            "slug": "demo",
            "start_date": "2026-01-01",
            "end_date": "2026-06-01",
            "n_conversations": 2,
            "n_versions": 1,
            "version_zip_files": [
                {
                    "filename": "/mnt/c/Users/alice/Downloads/demo-v1.zip",
                    "slug": "demo",
                    "version": "1",
                }
            ],
            "file_artifacts": ["app.py"],
            "source_conversation_ids": ["conv-secret-abc"],
            "member_ids": ["also-stripped"],
            "goal": "Build a demo app",
            "objectives": ["Ship MVP"],
            "requirements": [],
            "requirements_evolution": [],
            "quickstart": "",
            "how_to_use": "",
            "use_case": "",
            "how_to_update": "",
        }
    ],
}


class ExportPublicTest(unittest.TestCase):
    def test_strips_provenance_fields(self):
        out = ep.sanitize_project(SAMPLE["projects"][0])
        self.assertNotIn("source_conversation_ids", out)
        self.assertNotIn("member_ids", out)

    def test_normalizes_zip_to_basename(self):
        out = ep.sanitize_project(SAMPLE["projects"][0])
        self.assertEqual(out["version_zip_files"][0]["filename"], "demo-v1.zip")

    def test_windows_backslash_basename(self):
        self.assertEqual(
            ep.basename_only(r"C:\Users\alice\Downloads\proj-v2.zip"),
            "proj-v2.zip",
        )

    def test_sanitize_document_count(self):
        doc = ep.sanitize_document(SAMPLE)
        self.assertEqual(doc["n_projects"], 1)
        self.assertEqual(len(doc["projects"]), 1)

    def test_review_clean_document(self):
        doc = ep.sanitize_document(SAMPLE)
        self.assertEqual(ep.review_document(doc), [])

    def test_review_detects_email(self):
        dirty = ep.sanitize_document(SAMPLE)
        dirty["projects"][0]["goal"] = "Contact me at alice@example.com"
        findings = ep.review_document(dirty)
        self.assertTrue(any("email" in f for f in findings))

    def test_review_detects_user_path(self):
        dirty = ep.sanitize_document(SAMPLE)
        dirty["projects"][0]["how_to_use"] = "Open /mnt/c/Users/alice/Downloads/foo"
        findings = ep.review_document(dirty)
        self.assertTrue(any("Windows user path" in f for f in findings))

    def test_markdown_includes_slug_and_goal(self):
        proj = ep.sanitize_project(SAMPLE["projects"][0])
        md = ep.project_to_markdown(proj)
        self.assertIn("# Demo", md)
        self.assertIn("**Slug:** `demo`", md)
        self.assertIn("Build a demo app", md)
        self.assertNotIn("conv-secret", md)


if __name__ == "__main__":
    unittest.main()
