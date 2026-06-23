# ChatGPT Project Reconstructor

Reconstruct a structured, machine-readable history of your projects directly
from raw multi-GB ChatGPT `.zip` exports — no database, no cloud, local-first.

---

## Goal

From raw `conversations.json` exports, produce a per-project record containing:
name, slug, start/end date, number of versions, **every version `.zip` filename**,
goal, objectives, requirements, how those requirements evolved across chats,
quickstart, how-to-use (with a use case), and how to update to the next version.

Output is flat JSON ready for agentic/Cursor workflows.

## How it works

```
.zip ──▶ extract_cards ──▶ cluster_projects ──▶ build_bundles ──▶ [LLM] ──▶ reconstructed_projects.json
         Stage 1            Stage 2              Stage 3           Stage 4
         stream shards      union-find slugs     token-capped      Cursor or Ollama
         canonical path     from zip basenames   .md per project
```

| Stage | Script | LLM? | Output |
|-------|--------|------|--------|
| 1 | `extract_cards.py` | No | `store/transcripts/`, `cards.jsonl`, `index.json` |
| 2 | `cluster_projects.py` | No | `store/clusters.json` |
| 3 | `build_bundles.py` | No | `bundles/<slug>.md` |
| 4 | `summarize_ollama.py` or Cursor | Yes | `reconstructed_projects.json` |

Modern exports shard conversations across `conversations-000.json … -NNN.json`.
All shards are streamed; attachments are ignored. By default only clusters that
look like real **projects** (≥1 version `.zip`, or ≥2 conversations) are bundled
and summarized. Use `--min-versions 0` to include everything.

**Design principles:** zero-extraction streaming · token-optimized transcripts
(code bodies stripped) · canonical conversation path only · deterministic facts
computed in code · incremental store keyed by conversation id.

---

## Quick start

```bash
# One-time setup
cp .env.example .env                  # optional: edit VENV_DIR + data paths
cp config/reconstruct.config.example.json config/reconstruct.config.local.json  # optional
bash setup.sh

# Stages 1–3 (deterministic, no LLM tokens)
./run.sh --zip "<path-to-latest-export>.zip"

# Inspect before spending tokens
cat output/store/clusters.json        # or $RECONSTRUCTOR_DATA_ROOT/store/…
ls output/bundles/

# Stage 4 — pick one:
./ollama.sh --model qwen2.5-coder:14b --num-ctx 16384   # local Ollama
# OR Cursor: attach schema/project_history_schema.json + bundles/<slug>.md,
#            paste prompts/cursor_extraction_prompt.md (once per bundle)

# Publish safe copy to GitHub
python scripts/export_public.py --md --review
git diff published/
```

> Use `./run.sh`, `./ollama.sh`, `./diagnose.sh`, `./run_summary.sh` — they load
> `.env` and activate the external venv. Bare `python` may fail on Ubuntu 24.

A **run summary** (`output/RUN_SUMMARY_<timestamp>.md`) is written automatically
at the end of `./run.sh` and `./ollama.sh`. Regenerate anytime with `./run_summary.sh`.

---

## Setup and directory layout

The project separates **tooling** (this repo), **personal data** (never git),
**published summaries** (git, sanitized), and **venv** (never git).

```
┌─────────────────────────────────────────────────────────────────┐
│  THIS REPO (public GitHub)                                      │
│  scripts/  schema/  skills/  config/  published/                │
└─────────────────────────────────────────────────────────────────┘
         │                              ▲
         │ pipeline                     │ export_public.py --review
         ▼                              │
┌─────────────────────────┐    ┌────────────────────────┐
│  LOCAL DATA (gitignored) │    │  published/ (git OK)   │
│  $RECONSTRUCTOR_DATA_ROOT│    │  projects.json         │
│  or output/ (fallback)   │    │  projects/<slug>.md    │
│  ├─ store/               │    └────────────────────────┘
│  ├─ bundles/             │
│  └─ reconstructed_…json  │
└─────────────────────────┘

┌─────────────────────────┐
│  VENV (gitignored)      │
│  ~/.venvs/chatgpt-…     │
└─────────────────────────┘
```

### Configuration files

| File | Committed? | Purpose |
|------|------------|---------|
| `.env.example` | Yes | Template — copy to `.env` |
| `.env` | **No** | `VENV_DIR`, `RECONSTRUCTOR_DATA_ROOT` |
| `config/reconstruct.config.json` | Yes | Shared tuning knobs (no personal paths) |
| `config/reconstruct.config.example.json` | Yes | Template for local overrides |
| `config/reconstruct.config.local.json` | **No** | Your `data_root`, `default_zips` |

Default paths (when `.env` is unset):

| Setting | Default |
|---------|---------|
| Virtualenv | `~/.venvs/chatgpt-project-reconstructor/` |
| Data root | `output/` inside repo (gitignored) |
| With `.env` | `~/chatgpt-reconstructor-data/` |

Path resolution lives in `scripts/lib/paths.py` — all stages read
`RECONSTRUCTOR_DATA_ROOT` from the environment or local config.

### Clone and first-time setup

```bash
git clone git@github.com:<org>/chatgpt-project-reconstructor.git
cd chatgpt-project-reconstructor
cp .env.example .env
bash setup.sh
```

---

## Outputs

### Internal (local only)

| Path | Contents |
|------|----------|
| `store/transcripts/<id>.txt` | Reduced chat text (code stripped) |
| `store/cards.jsonl` | One compact card per conversation |
| `store/index.json` | Incremental store (id-keyed; newer export wins) |
| `store/clusters.json` | Deterministic project clusters |
| `bundles/<slug>.md` | Token-capped context for Stage 4 |
| `reconstructed_projects.json` | **Full** JSON incl. `source_conversation_ids` |

Schema: `schema/project_history_schema.json`

### Published (safe for GitHub)

| Path | Contents |
|------|----------|
| `published/projects.json` | Sanitized project catalog |
| `published/projects/<slug>.md` | Optional per-project markdown (`--md`) |

Schema: `schema/project_history_public_schema.json` — no conversation IDs,
zip filenames reduced to basenames only.

Produced by:

```bash
python scripts/export_public.py --md --review
```

---

## Privacy and GitHub

### Never commit

- ChatGPT export `.zip` files
- `output/` or `$RECONSTRUCTOR_DATA_ROOT/` (transcripts, bundles, full JSON)
- `reconstructed_projects.json` (contains `source_conversation_ids`)
- `.env`, `config/reconstruct.config.local.json`

### Safe to commit

- All source code, schema, skills, prompts
- `published/` after `export_public.py --review`

### Publish checklist

1. `python scripts/export_public.py --md --review` — fails on emails / home paths
2. Skim `goal`, `how_to_use`, `use_case` for accidental names or URLs
3. `git diff published/`
4. Optional: `bash scripts/check_no_secrets.sh` (or install as pre-commit hook)

### Initial git push

```bash
git init && git add -A && git status   # verify: no output/, .env, transcripts, *.zip
git remote add origin git@github.com:<org>/chatgpt-project-reconstructor.git
git push -u origin main
```

If you accidentally committed chat data, scrub history with
[`git filter-repo`](https://github.com/newren/git-filter-repo) before pushing.

---

## Run summaries

Each pipeline run can produce a timestamped report in the data root:

```
output/RUN_SUMMARY_20260622_062120.md     # example
```

Includes: commands run, conversation/cluster/bundle counts, file sizes, per-stage
timings, total wall time.

| Trigger | When |
|---------|------|
| Automatic | End of `./run.sh` (Stages 1–3) and `./ollama.sh` (Stage 4) |
| Manual | `./run_summary.sh` or `python scripts/collect_run_stats.py` |
| Skip | Pass `--no-summary` to `run.py` or `summarize_ollama.py` |

Supporting files (gitignored, in data root):

- `RUN_COMMANDS.log` — append-only command history
- `.run_manifest.json` — per-stage wall-clock seconds

---

## Updating (future exports)

Exports are cumulative full snapshots. Run only the **newest** `.zip` unless you
deleted chats between exports:

```bash
./run.sh --zip "<new-export>.zip"       # incremental: changed chats only
./ollama.sh --model qwen2.5-coder:14b   # re-summarize
python scripts/export_public.py --md --review
```

---

## Performance tips

From a typical run (~4k conversations, 180 projects):

| Phase | Typical time | Notes |
|-------|--------------|-------|
| Stages 1–3 | ~2–3 min | Already fast; ensure `ijson` is installed |
| Stage 4 (Ollama) | ~1 hr+ | **Bottleneck** — sequential LLM calls |

Stage 4 improvements:

- Use a smaller/faster model (`qwen2.5-coder:14b` beats `gpt-oss:20b` for prose)
- Lower `--num-ctx` and `--max-chars`
- Run Cursor Stage 4 in parallel across bundles
- On re-exports, only re-summarize changed slugs (manual today)

Stage 1 tip: read exports from the Linux filesystem, not `/mnt/c/…`, when possible.

---

## Troubleshooting

### `total=0` / `seen=0`

The archive parsed but no conversations matched. Inspect structure (read-only):

```bash
./diagnose.sh --zip "<path-to-export>.zip"
```

If the root JSON shape differs, extend `iter_conversations()` in
`scripts/lib/chatgpt_parse.py`.

### Ollama 500 / slow / OOM

The summarizer sends `think:false`, truncates bundles, and retries with halved
context. Tune `--num-ctx`, `--timeout`, `--max-chars`, or switch `--model`.
Keep `--num-ctx` ≤ 32768 for large models on limited GPU RAM.

---

## Extending

| Need | Where |
|------|-------|
| New OpenAI `content_type` | `message_text()` in `scripts/lib/chatgpt_parse.py` |
| Clustering too coarse/fine | `--min-slug-votes` or slug aliases |
| Bundle too large | `--char-budget` (stay under model context) |
| Different LLM | `summarize_ollama.py` or Cursor prompt |
| Schema change | `schema/project_history_schema.json` (+ public schema) |

---

## Project layout

```
run.py / run.sh              Stages 1–3 orchestrator + wrapper
ollama.sh / diagnose.sh      Stage 4 + export diagnostics
run_summary.sh               Write RUN_SUMMARY_<timestamp>.md
setup.sh                     Bootstrap external venv + ijson
.env.example                 VENV_DIR, RECONSTRUCTOR_DATA_ROOT

config/
  reconstruct.config.json           committed defaults
  reconstruct.config.example.json   local override template

schema/
  project_history_schema.json         full internal schema
  project_history_public_schema.json  GitHub-safe schema

published/                   sanitized summaries (committed)
scripts/
  extract_cards.py           Stage 1
  cluster_projects.py        Stage 2
  build_bundles.py           Stage 3
  summarize_ollama.py        Stage 4
  export_public.py           strip PII → published/
  collect_run_stats.py       run summary reports
  check_no_secrets.sh        pre-commit safety net
  lib/
    chatgpt_parse.py         streaming parser
    paths.py                 data-root resolution
    run_log.py               command log + stage timings

skills/                      Cursor agent skills
prompts/                     Cursor Stage 4 prompt
tests/                       unit tests (stdlib unittest)
output/                      fallback data dir (gitignored)
MANIFEST.md                  agent execution contract
```

---

## Tests

```bash
python3 -m unittest discover -s tests -v   # 29 tests, stdlib only
bash scripts/check_no_secrets.sh           # block accidental PII commits
```

Test coverage includes: path resolution, export sanitization, slug parsing,
schema roundtrip, repo hygiene (no personal paths in committed files), pre-commit
hook behavior, run summary generation.

---

## Recent project improvements

This section documents infrastructure added to make the repo safe for GitHub and
easier to operate day-to-day.

### Repository and privacy

- **Three-zone layout** — tooling in git, personal data outside repo, sanitized
  summaries in `published/`.
- **External venv** — `setup.sh` creates `~/.venvs/chatgpt-project-reconstructor/`
  instead of `.venv/` in the project tree.
- **External data root** — `RECONSTRUCTOR_DATA_ROOT` (via `.env` or local config)
  keeps transcripts and bundles out of git; falls back to `output/` for quick trials.
- **Config split** — committed `reconstruct.config.json` has no personal paths;
  use gitignored `reconstruct.config.local.json` for zip paths.
- **Expanded `.gitignore`** — blocks `.env`, transcripts, bundles, full JSON, zips.

### GitHub publishing

- **`scripts/export_public.py`** — strips `source_conversation_ids`, normalizes
  zip paths to basenames; `--review` scans for emails/home paths; `--md` writes
  per-project markdown.
- **`schema/project_history_public_schema.json`** — schema for sanitized output.
- **`scripts/check_no_secrets.sh`** — optional pre-commit hook; scans staged
  `*.json` for conversation IDs and user paths.

### Run observability

- **`scripts/collect_run_stats.py`** + **`run_summary.sh`** — generates
  `RUN_SUMMARY_<timestamp>.md` with counts, sizes, and timings.
- **`scripts/lib/run_log.py`** — logs commands to `RUN_COMMANDS.log` and stage
  timings to `.run_manifest.json`.
- **Auto-summary** — `./run.sh` and `./ollama.sh` write a summary at exit
  (disable with `--no-summary`).

### Quality

- **`tests/`** — 29 unit/integration tests (paths, export, hygiene, slug parsing,
  schema validation, run summaries).
- **Skills/docs** — removed hardcoded personal paths; aligned with new path model.

---

## Notes

- Exports are cumulative; deleted chats disappear from later snapshots.
- Everything runs locally. Ollama is fully offline; Cursor sends only the bundles
  you attach.
- Only `published/` is intended for GitHub — review before every push.
