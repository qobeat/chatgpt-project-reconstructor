"""Unit tests for zip slug parsing in extract_cards.py."""
from __future__ import annotations

import importlib.util
import os
import sys
import unittest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")


def _load_extract_cards():
    spec = importlib.util.spec_from_file_location(
        "extract_cards",
        os.path.join(SCRIPTS, "extract_cards.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


ec = _load_extract_cards()


class SlugParsingTest(unittest.TestCase):
    def test_date_cut(self):
        self.assertEqual(
            ec.slug_from_zip("ados-arena-2026-06-20-final.zip"),
            "ados-arena",
        )

    def test_timestamp_and_version(self):
        self.assertEqual(
            ec.slug_from_zip("ollama-test-20260622-045835-test-v1_9_0.zip"),
            "ollama-test",
        )

    def test_simple_version_suffix(self):
        self.assertEqual(
            ec.slug_from_zip("ollama-test-v1_9.zip"),
            "ollama-test",
        )

    def test_version_of_zip(self):
        self.assertEqual(ec.version_of_zip("proj-v1_9_0.zip"), "1.9.0")
        self.assertIsNone(ec.version_of_zip("no-version-here.zip"))


if __name__ == "__main__":
    unittest.main()
