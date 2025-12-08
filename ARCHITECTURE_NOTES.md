# Document Intake – Workflow & Router Architecture

## 1. User chooses what to run

1. **User selects document(s)** to process.

2. **User selects schema (template)**:
   - **Built-in template**  
     - Ships with a predefined `document_type` (e.g. `"invoice"`, `"resume"`, `"claim"`).  
     - May also ship with a default `preferred_workflow` (e.g. `"basic"` or `"balanced"`).
   - **Cloned / user-created template**  
     - On first use, the system may call an LLM once to infer a suitable `document_type` from the document content, then store it on the template.  
     - After that, the template has a stable `document_type` just like a built-in template.  
     - A `preferred_workflow` can also be stored or adjusted by advanced users.

3. **User starts processing.**

---

## 2. What we store on every run

For each processed document we store (in some persistent store / log):

- `content_hash` (hash of the normalized text snippet / file stats).
- `document_type` used for extraction.
- `schema_id` or `schema_path`.
- `workflow` used (`"basic"` or `"balanced"`).

This lets us:

- Avoid re-routing the *same* document content. 
- Analyze or debug past decisions if needed.

---

## 3. Router behavior

Over time, every template ends up with a stable `document_type` (either predefined or inferred once). The router’s ongoing role is primarily to decide the **workflow per document** (basic vs balanced), using document content.

1. **Check content cache (by content hash/snippet)**
   - If an entry exists:
     - No LLM call is made.  
     - Reuse the stored `workflow` (and `document_type` if needed).
   - If no entry exists:
     - Call the LLM router to infer the best `workflow` (`"basic"` or `"balanced"`) for this particular document, based on layout/complexity.  
     - Optionally also (for brand-new templates) infer an initial `document_type` the very first time, then store it on the template.
     - Save `{content_hash, document_type, schema_id, workflow}`.

2. **Interaction with schemas/templates**

   - **Built-in templates**:
     - Already have `document_type` (and usually a sensible default `preferred_workflow`).
     - Router can still be used per document when you want flexibility (e.g. some resumes may be fine with basic, others need balanced).

   - **New / cloned templates**:
     - First time they are used, the system may consult the router (or a dedicated detector) once to pick a `document_type`, then store it on the template.  
     - After that, the template behaves like a built-in one: `document_type` is stable, while `workflow` can still be chosen per document.

---

## 4. Balanced workflow (registry)

In `WORKFLOW_REGISTRY`, the **balanced** entry conceptually contains three steps:

1. `vision_generate_markdown`
2. `prompt_generator` (explicit step)
3. `extract_fields_balanced`

### `vision_generate_markdown`

- Inputs: `document`, `metadata`.
- Outputs: `markdown_content`, `structure_hints`.

### `prompt_generator`

- Inputs: `document_type`, loaded `schema`.
- Behavior:
  - Computes a cache key for `(document_type, schema)`.
  - If present in `.cache`:
    - No LLM call.
    - Returns cached `system_prompt`.
  - If missing:
    - Calls LLM once to create `system_prompt`.
    - Saves `{document_type, schema, system_prompt}` via `cache_manager`.
- Output: `system_prompt`.

> **Note:** `vision_generate_markdown` and `prompt_generator` are independent and can be run in parallel by the orchestrator.

### `extract_fields_balanced`

- Inputs:
  - `document`, `metadata`, `schema_path`.
  - `markdown_content`, `structure_hints` (from vision).
  - `document_type`.
  - `system_prompt` (from `prompt_generator`; if missing, it can generate internally as a fallback).
- Uses all of the above to perform structured extraction.

---

## 5. Basic extraction workflow

- Workflow contains only `extract_fields_basic`.
- Inputs: `document`, `metadata`, `schema_path`, `document_type`.
- No vision step; simpler text-only path.
- Internally, `extract_fields_basic` also calls the shared `generate_system_prompt(document_type, schema)` helper (via `utils.prompt_generator`), so basic and balanced workflows both rely on the same prompt-generation and caching mechanism.

---

## 6. Prompt caching

- `generate_system_prompt(document_type, schema)`:
  - First call for a `(document_type, schema)` pair:
    - Calls LLM.  
    - Saves the resulting `system_prompt` in `.cache/`.
  - Subsequent calls for the same pair:
    - No LLM call.  
    - System prompt is reused from `.cache`.

- We can warm this cache ahead of time for standard templates via `utils/warm_prompt_cache.py` so first-time users don’t pay the LLM cost for prompt generation on those schemas.
