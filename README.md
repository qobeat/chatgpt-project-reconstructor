# ChatGPT Project Reconstructor

Reconstruct a structured, machine-readable history of your projects directly
from raw multi-GB ChatGPT `.zip` exports — no database, no cloud, local-first.

## 🎯 Goal
Programmatically reconstruct, from raw `conversations.json` exports, a per-project
record containing: name, slug, start/end date, number of versions, **every
version `.zip` filename**, goal, objectives, requirements, how those requirements
evolved across chats, quickstart, how-to-use (with a use case), and how to update
to the next version. Output is flat JSON ready for agentic/Cursor workflows.

## 📋 Objectives
- **Zero-extraction triage** — stream straight from the `.zip`; never unpack the
  multi-GB payload or load the whole JSON into RAM.
- **Token-optimized context** — drop UI/mapping noise *and* assistant code bodies
  (the real token sink) before any LLM sees the data.
- **Canonical, not noisy** — follow `current_node → root` so discarded
  regenerations and forked drafts are excluded.
- **Deterministic-first** — versions, dates, file artifacts and clustering are
  computed in code; the LLM only writes prose, schema-constrained → no
  hallucinated filenames or versions.
- **Reusable** — an incremental JSON store keyed by conversation id absorbs
  future exports cheaply.

## ⚙️ Pipeline
```
.zip ──▶ extract_cards ──▶ cluster_projects ──▶ build_bundles ──▶ [LLM] ──▶ reconstructed_projects.json
        (stream, canonical   (union-find on       (token-capped     (Cursor or
         path, reduce)        zip-basename slugs)   per-project)      Ollama)
```

## 🚀 Fast start
```bash
cd chatgpt-project-reconstructor
pip install -r requirements.txt          # ijson (recommended for GB zips)

# Deterministic stages (no LLM): point at your NEWEST export (snapshots are cumulative)
python run.py --zip "/mnt/c/Users/kirae/Downloads/ChatGpt/<latest>.zip"

# Inspect deterministic results before spending any tokens:
cat output/store/clusters.json | less
ls output/bundles/

# Stage 4 — choose ONE:
#  A) Cursor: attach schema/project_history_schema.json + output/bundles/<slug>.md,
#     paste prompts/cursor_extraction_prompt.md (run once per bundle).
#  B) Local Ollama (offline):
python scripts/summarize_ollama.py --model gpt-oss:20b
```
Result: `output/reconstructed_projects.json`.

## 🧭 How to use the output
Each `projects[]` entry is self-contained context for an agent: feed a single
project object to Cursor/Claude to resume work, generate a README, or seed your
ADOS catalog. `source_conversation_ids` lets you jump back to raw transcripts in
`output/store/transcripts/`.

## 🔁 How to update (future exports)
Run `python run.py --zip "<new-export>.zip"` again. The store keyed by
conversation id updates only new/changed chats (newer `update_time` wins), then
re-cluster/re-summarize. No need to reprocess history.

## 🛠️ How to change / extend
- **New `content_type`** (OpenAI adds these over time): extend `message_text()`
  in `scripts/lib/chatgpt_parse.py`.
- **Clustering too coarse/fine**: tune `--min-slug-votes` (cluster) or add slug
  aliases after Stage 2.
- **Bundle truncation**: raise `--char-budget` (keep under your model context).
- **Different LLM**: edit `scripts/summarize_ollama.py` (any Ollama model) or use
  the Cursor prompt with any assistant.
- **Schema**: edit `schema/project_history_schema.json`; keep deterministic
  fields authoritative.

## 📁 Layout
```
run.py                         orchestrator (Stages 1-3)
schema/                        project_history_schema.json
config/                        reconstruct.config.json
scripts/
  lib/chatgpt_parse.py         streaming + canonical path + robust extraction
  extract_cards.py             Stage 1
  cluster_projects.py          Stage 2
  build_bundles.py             Stage 3
  summarize_ollama.py          Stage 4 (optional, local LLM)
skills/
  chatgpt-export-triage/       SKILL.md
  project-reconstruction/      SKILL.md
prompts/cursor_extraction_prompt.md
output/                        store/, bundles/, reconstructed_projects.json
MANIFEST.md                    agent execution contract
```

## Notes
- Exports are cumulative full snapshots; deleted chats are absent from later
  exports. You can ignore older archives unless you deleted chats between them.
- Everything runs locally. No data leaves the machine (Ollama path is fully
  offline; Cursor path sends only the reduced bundles you choose).
