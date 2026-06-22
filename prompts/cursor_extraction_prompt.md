# Cursor Composer — Project Reconstruction Extraction Prompt

Use this AFTER `python run.py --zip ...` has produced `output/bundles/*.md`.
Run it **once per bundle** (each bundle is one project and already fits context).

## Attach
1. `schema/project_history_schema.json`
2. One bundle file: `output/bundles/<slug>.md`

## Prompt (paste verbatim)

> **Task:** From the attached bundle, emit ONE JSON object for the single
> project it describes, conforming to `project_history_schema.json`.
>
> **Authority rule:** The bundle's `DETERMINISTIC FACTS` block is ground truth.
> Copy `slug`, `start_date`, `end_date`, `n_conversations`, `n_versions`,
> `version_zip_files`, and `file_artifacts` **verbatim**. Do NOT invent or alter
> file names, zip names, versions, or dates. Set `source_conversation_ids` from
> the conversation ids in the transcript headers.
>
> **Your job (prose fields only):** read the REDUCED TRANSCRIPTS in
> chronological order and write:
> - `project_name` (human-readable; fall back to slug)
> - `goal` (one sentence)
> - `objectives` (array)
> - `requirements` (array, current/latest understanding)
> - `requirements_evolution` (ordered array of `{date, change}` — capture how
>   the user's asks change across chats; this is the point of the exercise)
> - `quickstart`, `how_to_use`, `use_case`, `how_to_update`
>
> **Constraints:** Output only the JSON object. No markdown fences, no prose
> outside JSON. Code bodies were stripped from the transcripts on purpose —
> infer intent from user turns and assistant prose, not from code. If a field
> is unknown, use "" or [].

## Merge
Append each emitted object to the `projects` array of
`output/reconstructed_projects.json`. Re-running on a future export only
changes clusters whose conversations changed, so re-extract only those slugs.
