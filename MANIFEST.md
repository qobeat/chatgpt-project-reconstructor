# MANIFEST.md — Agent Execution Contract

> For the Cursor agent (or any coding agent) running this package locally.
> Follow GOAL/OBJECTIVES exactly. Do not change them without an explicit ask.

## GOAL
Produce a full internal `reconstructed_projects.json` under
`$RECONSTRUCTOR_DATA_ROOT` (or `output/` if unset): a structured, auditable
history of the user's projects reconstructed from ChatGPT export `.zip` file(s),
conforming to `schema/project_history_schema.json`.

For GitHub, run `scripts/export_public.py` to write sanitized summaries to
`published/projects.json` (no conversation IDs).

## OBJECTIVES
1. Process each provided `.zip` without full extraction or whole-file JSON load.
2. Keep only the canonical conversation branch; drop discarded regenerations.
3. Cluster conversations into projects deterministically (zip-basename slugs).
4. Capture every version `.zip` filename and the project's requirement evolution.
5. Use the LLM ONLY for prose fields; copy deterministic facts verbatim.

## PRECONDITIONS
- Python 3.10+ available. Run `bash setup.sh` or `pip install -r requirements.txt`.
- Load paths from `.env` (`VENV_DIR`, `RECONSTRUCTOR_DATA_ROOT`) or
  `config/reconstruct.config.local.json` (`data_root`, `default_zips`).
- Zip path(s) provided by the user via `--zip`. If none on CLI, read
  `config/reconstruct.config.local.json` → `default_zips`. If still none, STOP
  and ask. Do not guess paths.
- If a `.zip` is missing on disk, STOP and report it. Do not fabricate data.

## PLAN (actions → success condition)
1. `./run.sh --zip "<zip1>" [--zip "<zip2>" ...]`
   - SUCCESS: `$DATA_ROOT/store/index.json`, `cards.jsonl`, `clusters.json`, and
     `$DATA_ROOT/bundles/*.md` + `bundles/INDEX.json` exist; stderr shows
     `added/updated/skipped` and a non-zero cluster count.
2. Present `$DATA_ROOT/store/clusters.json` summary to the user BEFORE Stage 4
   (slugs, n_conversations, n_versions, date span). This is the cheap checkpoint.
3. Stage 4 — LLM summary via local Ollama:
   - `./ollama.sh --model gpt-oss:20b`
   - SUCCESS: full JSON validates against the schema; every project has non-empty
     `slug`, `goal`, and `source_conversation_ids`; deterministic fields match
     `clusters.json` exactly.
4. (Optional GitHub publish) `python scripts/export_public.py --md --review`
   - SUCCESS: `published/projects.json` has no `source_conversation_ids`; review
     passes with no PII warnings.

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
- Never commit transcripts, bundles, export zips, or full internal JSON to git.

## REUSE
Future exports: re-run step 1 with the new `.zip`; only changed conversations are
reprocessed. Re-cluster and re-summarize affected slugs only.

## OUTPUT INVENTORY
```
$DATA_ROOT/store/index.json                  incremental store (id-keyed)
$DATA_ROOT/store/cards.jsonl                 per-conversation facts
$DATA_ROOT/store/transcripts/<id>.txt        reduced transcripts (LOCAL ONLY)
$DATA_ROOT/store/clusters.json               deterministic project clusters
$DATA_ROOT/bundles/<slug>.md                  token-capped LLM bundles (LOCAL ONLY)
$DATA_ROOT/reconstructed_projects.json        full internal deliverable
published/projects.json                       sanitized GitHub deliverable
published/projects/<slug>.md                  optional sanitized markdown
```
