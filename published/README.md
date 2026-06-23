# Published project summaries

This directory contains **sanitized, AI-generated project summaries** intended
for GitHub. They are derived from your local pipeline output but stripped of
personal data before commit.

## What is included

- `projects.json` — redacted project catalog (schema: `schema/project_history_public_schema.json`)
- `projects/<slug>.md` — optional per-project markdown (generate with `--md`)

## What is never published here

- Raw ChatGPT export `.zip` files
- Conversation transcripts (`store/transcripts/`)
- LLM context bundles (`bundles/*.md`)
- `source_conversation_ids` or other chat provenance

## How to update

From the project root, after Stage 4 completes:

```bash
python scripts/export_public.py --md --review
git diff published/
git add published/
git commit -m "Update sanitized project summaries"
```

The `--review` flag scans for emails and user home paths. Skim `goal` and
`how_to_use` manually — the LLM may mention names or internal URLs.

## Redaction policy

| Field | Published? |
|-------|------------|
| `slug`, `project_name`, dates, counts | Yes |
| `goal`, objectives, requirements, how-to fields | Yes (review manually) |
| `version_zip_files` | Basename only |
| `file_artifacts` | Yes |
| `source_conversation_ids` | **No** |
