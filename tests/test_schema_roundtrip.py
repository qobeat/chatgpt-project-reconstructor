"""Validate export_public output matches public schema shape."""
from __future__ import annotations

import importlib.util
import json
import os
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

PUBLIC_REQUIRED_PROJECT = frozenset({"project_name", "slug", "goal"})
PUBLIC_FORBIDDEN = frozenset({"source_conversation_ids", "member_ids"})


def validate_public_project(p: dict) -> list[str]:
    errors = []
    for key in PUBLIC_REQUIRED_PROJECT:
        if key not in p:
            errors.append(f"missing required field: {key}")
    for key in PUBLIC_FORBIDDEN:
        if key in p:
            errors.append(f"forbidden field present: {key}")
    for z in p.get("version_zip_files") or []:
        fn = z.get("filename", "") if isinstance(z, dict) else str(z)
        if "/" in fn or "\\" in fn:
            errors.append(f"zip filename not basename-only: {fn}")
    return errors


class SchemaRoundtripTest(unittest.TestCase):
    def test_sanitize_matches_public_schema_shape(self):
        sample = {
            "projects": [{
                "project_name": "Demo",
                "slug": "demo",
                "goal": "g",
                "source_conversation_ids": ["x"],
                "version_zip_files": [{"filename": "/a/b.zip"}],
                "file_artifacts": [],
                "objectives": [],
                "requirements": [],
                "requirements_evolution": [],
                "quickstart": "",
                "how_to_use": "",
                "use_case": "",
                "how_to_update": "",
            }]
        }
        public = ep.sanitize_document(sample)
        for p in public["projects"]:
            self.assertEqual(validate_public_project(p), [])

    def test_real_output_if_present(self):
        path = os.path.join(ROOT, "output", "reconstructed_projects.json")
        if not os.path.exists(path):
            self.skipTest("no local run output")
        with open(path, encoding="utf-8") as f:
            full = json.load(f)
        public = ep.sanitize_document(full)
        all_errors = []
        for p in public["projects"]:
            all_errors.extend(validate_public_project(p))
        self.assertEqual(all_errors, [])


if __name__ == "__main__":
    unittest.main()
