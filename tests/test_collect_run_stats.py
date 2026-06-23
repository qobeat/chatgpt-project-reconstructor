"""Tests for collect_run_stats.py and run_log.py."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
SCRIPTS = os.path.join(ROOT, "scripts")
LIB = os.path.join(SCRIPTS, "lib")


def _load_module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class CollectRunStatsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "store", "transcripts"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp, "bundles"), exist_ok=True)
        with open(os.path.join(self.tmp, "store", "transcripts", "a.txt"), "w") as f:
            f.write("line1\nline2\n")
        with open(os.path.join(self.tmp, "store", "cards.jsonl"), "w") as f:
            f.write('{"id":"a"}\n')
        with open(os.path.join(self.tmp, "store", "index.json"), "w") as f:
            json.dump({"a": {}}, f)
        with open(os.path.join(self.tmp, "store", "clusters.json"), "w") as f:
            json.dump([{"slug": "demo", "n_versions": 1, "n_conversations": 1}], f)

        sys.path.insert(0, LIB)
        self.run_log = _load_module("run_log_test", os.path.join(LIB, "run_log.py"))
        self.run_log.append_command("./run.sh --zip test.zip", self.tmp)
        self.run_log.stage_start("extract", self.tmp)
        self.run_log.stage_end("extract", self.tmp)

        self.crs = _load_module(
            "collect_run_stats_test",
            os.path.join(SCRIPTS, "collect_run_stats.py"),
        )

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_write_summary_creates_timestamped_file(self):
        out = self.crs.write_summary(root=self.tmp, label="test")
        self.assertTrue(os.path.basename(out).startswith("RUN_SUMMARY_"))
        self.assertTrue(out.endswith(".md"))
        with open(out, encoding="utf-8") as f:
            body = f.read()
        self.assertIn("Pipeline Run Summary", body)
        self.assertIn("./run.sh --zip test.zip", body)
        self.assertIn("Stage 1 extract", body)

    def test_append_command_logged(self):
        cmds = self.run_log.read_commands(self.tmp)
        self.assertIn("./run.sh --zip test.zip", cmds)


if __name__ == "__main__":
    unittest.main()
