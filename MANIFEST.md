# MANIFEST.md — Agent Execution Contract

> For the Cursor agent (or any coding agent) running this package locally.
> Follow GOAL/OBJECTIVES exactly. Do not change them without an explicit ask.

## GOAL
Produce `output/reconstructed_projects.json`: a structured, auditable history of
the user's projects reconstructed from ChatGPT export `.zip` file(s), conforming
to `schema/project_history_schema.json`.

## OBJECTIVES
1. Process each provided `.zip` without full extraction or whole-file JSON load.
2. Keep only the canonical conversation branch; drop discarded regenerations.
3. Cluster conversations into projects deterministically (zip-basename slugs).
4. Capture every version `.zip` filename and the project's requirement evolution.
5. Use the LLM ONLY for prose fields; copy deterministic facts verbatim.

## PRECONDITIONS
- Python 3.10+ available. `pip install -r requirements.txt` (ijson).
- Zip path(s) provided by the user. If none, read `config/reconstruct.config.json`
  → `default_zips`. If still none, STOP and ask. Do not guess paths.
- If a `.zip` is missing on disk, STOP and report it. Do not fabricate data.

## PLAN (actions → success condition)
1. `python run.py --zip "<zip1>" [--zip "<zip2>" ...]`
   - SUCCESS: `output/store/index.json`, `cards.jsonl`, `clusters.json`, and
     `output/bundles/*.md` + `bundles/INDEX.json` exist; stderr shows
     `added/updated/skipped` and a non-zero cluster count.
2. Present `output/store/clusters.json` summary to the user BEFORE Stage 4
   (slugs, n_conversations, n_versions, date span). This is the cheap checkpoint.
3. Stage 4 — LLM summary (default to Ollama if `--model` reachable, else emit the
   Cursor instructions):
   - Ollama: `python scripts/summarize_ollama.py --model gpt-oss:20b`
   - Cursor: for each `output/bundles/<slug>.md`, attach it +
     `schema/project_history_schema.json`, run `prompts/cursor_extraction_prompt.md`,
     append the emitted object to `output/reconstructed_projects.json`.
   - SUCCESS: `output/reconstructed_projects.json` validates against the schema;
     every project has non-empty `slug`, `goal`, and `source_conversation_ids`;
     `version_zip_files`/`file_artifacts`/dates match `clusters.json` exactly.

## AUTHORITY RULES (anti-hallucination)
- `version_zip_files`, `file_artifacts`, `start_date`, `end_date`,
  `n_conversations`, `n_versions`, `source_conversation_ids`, `slug` come from
  `clusters.json` and are COPIED, never generated.
- The LLM may only write: `project_name`, `goal`, `objectives`, `requirements`,
  `requirements_evolution`, `quickstart`, `how_to_use`, `use_case`,
  `how_to_update`.
- If the LLM output conflicts with deterministic facts, deterministic wins.

## DRIFT / STOP CONDITIONS
- Empty transcripts for a whole content-type → likely a new OpenAI `content_type`.
  STOP, report which `content_type` is unhandled, propose extending
  `message_text()` in `scripts/lib/chatgpt_parse.py`. Do not silently proceed.
- ijson unavailable AND zip > 200 MB → warn; prefer installing ijson before
  proceeding to avoid high RAM use.
- Do not modify files outside this package. Do not alter GOAL/OBJECTIVES.

## REUSE
Future exports: re-run step 1 with the new `.zip`; only changed conversations are
reprocessed. Re-cluster and re-summarize affected slugs only.

## OUTPUT INVENTORY
```
output/store/index.json                  incremental store (id-keyed)
output/store/cards.jsonl                  per-conversation facts
output/store/transcripts/<id>.txt         reduced transcripts
output/store/clusters.json                deterministic project clusters
output/bundles/<slug>.md                  token-capped LLM bundles
output/reconstructed_projects.json        FINAL deliverable
```
