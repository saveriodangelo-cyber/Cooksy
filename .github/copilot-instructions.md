# Copilot Project Instructions

## Overview
- Desktop app with PyWebView UI (`app/launcher.py` -> `ui/index.html`, `ui/app.js`), backend orchestrator in `backend/bridge.py`, and extraction/AI pipeline in `backend/pipeline.py`.
- Batch/interactive flows call `analyze_files` (OCR + parse + AI enrichment) then export PDF/DOCX via `backend/pdf_export.py` templates in `templates/`.
- Archive stored in SQLite at `data/recipes/recipes.db` via `backend/archive_db.py`.

## Running & env
- Use Windows entry `run.cmd` (creates venv, installs `requirements.txt`, runs `python -m app.launcher`).
- Default output folder forced to `Desktop/Elaborate` (or chosen folder with nested `Elaborate`). Batch creates category subfolders and `da_analizzare` for deferred files.
- Key env: `RICETTEPDF_OLLAMA_URL/MODEL/TIMEOUT_S` (local LLM), `DISABLE_MODEL_SOURCE_CHECK=True` set by default. Cloud AI settings in `data/config/cloud_ai.json`.

## Backend patterns
- `bridge.py` is the API surface for UI: methods `analyze_start/result`, `batch_start/status`, `export_pdf`, `choose_input/output_folder`, archive helpers. Threading guarded by `_analysis_lock` and `_batch_lock`; batch timeout watcher handles retries and may move files to `da_analizzare`.
- Batch uses `_list_files` with fixed extensions; per-file processing: `analyze_files` -> export PDF/DOCX -> optional `ArchiveDB.save_recipe`. Errors/events reported via `_batch_state['last_event']`.
- `pipeline.py` does OCR (`extract_text_from_paths`), parsing (`parse_recipe_text`), AI enrichment (`standard_recipe_extraction`, `_complete_missing_with_ai` cloud/Ollama), normalization (`_apply_saverio_rules`), enrichment (`_enrich_data`), and export helpers.
- Missing-template fields no longer block: they are recorded in `recipe['missing_fields']` and `analyze_files` returns `ok=True`.
- `run_pipeline` (legacy batch) writes outputs to `Output_Elaborati/` and archives recipes; newer batch uses `bridge.py` with chosen output.

## UI specifics
- `ui/app.js` polls `batch_status`, shows `last_event` messages, and handles timeout prompts. Output directory label mirrors backend `_output_dir`.
- Templates selectable via UI; `bridge.get_templates` lists available IDs; HTML templates in `templates/` with assets in `templates/assets/`.

## Coding conventions
- Keep ASCII; brief comments only where logic is non-obvious.
- Prefer updating existing functions instead of new entry points; follow existing thread/lock usage in `bridge.py`.
- For new exports, reuse `build_template_context` from `pipeline.py`.

## Testing/diagnostics
- No formal test suite; ad-hoc scripts `_test_pdf_export.py`, `_test_allergens.py`, `_test_pdf_export.py` under `backend/`.
- Log/print paths: batch status via `last_event`; DB issues printed in console.

## When adding features
- Wire UI buttons to `bridge` methods; ensure `state` updates in `ui/app.js` and `batch_status` polling shows progress.
- Preserve timeout/defer behavior in batch: keep 180s timeout, 3 retries, autoskip to `da_analizzare`.
- Maintain forced AI options for batch (`use_ai`, `ai_complete_missing`, `force_ai_full`).
