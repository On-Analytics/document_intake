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

The router is implemented as `route_document(document, schema_id=None)` in `router.py`.

- **Inputs**:
  - `document`: a LangChain `Document` with `page_content` and `metadata` (especially `metadata["source"]`).
  - `schema_id` (optional): Supabase schema ID used to read/update `document_type` and for routing cache keys.

- **Outputs**:
  - A `dict` with:
    - `workflow`: `"basic"` or `"balanced"`.
    - `document_type`: final document type string used downstream (may come from schema or LLM).

### 3.1 High-level decision flow

1. **Schema-provided document_type (if schema_id is present)**
   - If `schema_id` is provided, `get_schema_document_type(schema_id)` is called against Supabase.
   - If Supabase returns a non-empty `document_type`, that value is treated as the **authoritative** type for this run and overrides any `document_type` proposed by the LLM.
   - If Supabase does **not** have a `document_type` yet, the LLM’s inferred `document_type` is used for the run; if it is not `"generic"`, it is also written back to Supabase via `update_schema_document_type` so future runs use that stored type.

2. **File-extension heuristic (fast path for .txt)**
   - If the source filename (from `document.metadata["source"]`) ends with `.txt` **and** no `document_type` was found on the schema:
     - Immediately returns:
       - `workflow = "basic"`
       - `document_type = "generic"`
     - Skips caching and LLM calls for simple plain-text inputs.

3. **Normalize content and build snippet**
   - Uses `_normalize_garbage_characters(document.page_content or "")` to clean up text.
   - **Current behavior:** takes the first ~4000 characters as `snippet` for routing (a single-prefix sample).
   - **Planned improvement for multi-page documents:** instead of a single long prefix, sample up to ~2000 characters **per page** across the first few pages (e.g., first 3 pages), then concatenate these page snippets. This spreads the context over multiple pages so the router can see both early boilerplate and later structured content.

4. **Router cache lookup (content + schema_id)**
   - Computes a cache key via `generate_cache_key` using:
     - `content = snippet`
     - `extra_params = {"schema_id": schema_id}`
   - Looks up this key in `ROUTER_CACHE_DIR` using `get_cached_result`.
   - If found, returns the cached result **immediately**:
     - `{"workflow": ..., "document_type": ...}`
   - This avoids repeated LLM calls for the same (snippet, schema_id) pair.

5. **Short-content optimization**
   - If the cleaned `snippet` has fewer than 50 non-whitespace characters:
     - Returns `workflow = "basic"`, `document_type = "generic"`.
     - No LLM call or cache write.

6. **LLM router decision**
   - Calls `_make_llm_decision(snippet)` which:
     - Uses `ChatOpenAI` with a structured `RouterOutput` schema.
     - Returns a `workflow` and an LLM-inferred `document_type` (fallbacks to `workflow="balanced"`, `document_type="generic"` on errors).
   - The **final** `document_type` used for the run is:
     - The schema `document_type` if it exists, otherwise
     - The LLM-inferred `document_type`.

7. **Schema backfill (optional update)**
   - If `schema_id` is provided, the schema has no `document_type` yet, and the LLM returns a non-`"generic"` type:
     - Calls `update_schema_document_type(schema_id, decision["document_type"])` to persist the inferred type back into Supabase.

8. **Write to router cache**
   - Stores the final decision in `ROUTER_CACHE_DIR` via `save_to_cache` using the same cache key computed earlier:
     - `{"workflow": decision["workflow"], "document_type": final_doc_type}`
   - Subsequent calls with the same (snippet, schema_id) will reuse this cached routing result.

---

## 4. Balanced workflow (registry)

In `WORKFLOW_REGISTRY`, the **balanced** entry conceptually contains three steps:

1. `vision_generate_markdown`
2. `prompt_generator` (explicit step)
3. `extract_fields_balanced`

### `vision_generate_markdown`

Implemented in `extractors/vision_generate_markdown.py` as:

`vision_generate_markdown(document, metadata, schema_content) -> Dict[str, Any]`

- **Inputs**:
  - `document`: LangChain `Document`.
    - Not heavily used in the current implementation; primary source is `metadata.file_path`.
  - `metadata: DocumentMetadata` (from `core_pipeline`), including at least:
    - `file_path`: path to the original file (PDF or image).
    - `filename`: used in prompt instructions for context.
  - `schema_content: Dict[str, Any]`:
    - Currently accepted for future schema-aware behavior but not read inside this function yet.

- **Outputs** (`Dict[str, Any]`):
  - `markdown_content: str`:
    - Human-readable markdown representation of the document generated by the vision model.
  - `structure_hints: Dict[str, Any]`:
    - Lightweight, derived metadata computed by `_analyze_markdown_structure`, e.g.:
      - `has_tables: bool`
      - `table_count: int`
      - `table_columns: List[str]`
      - `multi_row_entries: bool`
      - `has_multi_column_layout: bool`
      - `section_count: int`

- **Caching behavior**:
  - Builds a cache key using `generate_cache_key` with:
    - `file_path = str(metadata.file_path)`
    - `extra_params = {"step": "vision_generate_markdown", "model": VISION_MODEL}`
      - `VISION_MODEL` defaults to `"gpt-4o-mini"` (via env var `VISION_MODEL`).
  - Looks up this key in `VISION_CACHE_DIR` via `get_cached_result`.
  - If present, **returns the cached `{markdown_content, structure_hints}` immediately** and skips any model calls.

- **Vision vs non-vision path**:
  - If `metadata.file_path` ends with `.pdf`:
    - Uses `convert_pdf_to_images(file_path)` to produce a list of base64-encoded page images.
  - If `metadata.file_path` ends with `.png`, `.jpg`, `.jpeg`:
    - Reads the file bytes, encodes as base64, and wraps into a single image list.
  - If no images can be produced (not a supported extension or failure):
    - Returns `{"markdown_content": "", "structure_hints": {}}` without calling the LLM.

- **LLM call (vision)**:
  - Constructs a **system prompt** describing the task: convert the document into well-structured markdown while preserving layout and key information.
  - Builds a **base instruction** including the filename and formatting guidelines:
    - Use headers, lists, and tables.
    - Keep each logical item in a single table row.
    - Handle multi-column layouts carefully.
    - Preserve values exactly.
  - Assembles `HumanMessage` content:
    - First a text block with the base instruction.
    - Then one or more `image_url` entries with `data:image/jpeg;base64,...` URLs for each page image.
  - Uses `ChatOpenAI` with:
    - `model = os.getenv("VISION_MODEL", "gpt-4o-mini")`.
    - `temperature = 0`.
    - `.with_structured_output(MarkdownOutput, method="function_calling")` to parse into the `MarkdownOutput` pydantic model.

- **Post-processing and cache write**:
  - Extracts `markdown_content` from the model output.
  - Runs `_analyze_markdown_structure(markdown_content)` to compute `structure_hints` (tables, sections, simple layout cues).
  - Packs both into a result dict and saves it to `VISION_CACHE_DIR` via `save_to_cache(cache_key, result, cache_dir=VISION_CACHE_DIR)`.
  - Returns the same result to the caller.

### `prompt_generator`

Implemented in `utils/prompt_generator.py` as:

`generate_system_prompt(document_type, schema) -> str`

- **Inputs**:
  - `document_type: str`:
    - High-level type label (e.g., `"resume"`, `"invoice"`, `"claim"`).
    - Included in the meta prompt so the generated system prompt is specialized.
  - `schema: Dict[str, Any]`:
    - Full JSON schema definition used for extraction (same structure as `schema_content`).

- **Output**:
  - `system_prompt: str`:
    - A single string used as the **system message** for downstream extraction LLMs (basic and balanced workflows).

- **Caching behavior (Supabase `prompt_cache` table)**:
  - Computes a **canonical JSON** string for the schema (`sort_keys=True`) and hashes it:
    - `schema_hash = sha256(canonical_schema).hexdigest()`.
  - Builds a `cache_key = sha256(f"{document_type}:{schema_hash}")`.
  - Looks up this key in Supabase `prompt_cache` via `_get_cached_prompt_from_supabase(cache_key)` using `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY`.
  - If a cached row exists:
    - Returns `system_prompt` from Supabase.
    - No OpenAI call is made.
  - If no cache entry exists:
    - Calls the LLM once to generate a new `system_prompt`.
    - Saves `{cache_key, document_type, schema_hash, system_prompt}` back into Supabase via `_save_prompt_to_supabase` for reuse across deployments.

- **LLM behavior**:
  - Uses `ChatOpenAI` with:
    - `model="gpt-4o"`.
    - `temperature=0`.
    - Structured output model `SystemPromptOutput` with a single `system_prompt: str` field.
  - System (`meta_system_prompt`) describes the meta-task: design an optimal **system prompt** for extraction given a document type and schema.
  - User prompt includes:
    - The `document_type`.
    - The JSON schema (pretty-printed).
    - Explicit instructions about:
      - Handling nested fields and lists.
      - Handling table-like document types (invoices, bank statements, forms).
      - Enforcing strict schema alignment.
  - On success:
    - Returns `result.system_prompt`.
  - On failure (exceptions, network issues):
    - Logs a warning and falls back to a **generic** system prompt string that still enforces schema-aligned extraction.

> **Note:** `vision_generate_markdown` and `prompt_generator` are independent and can be run in parallel by the orchestrator.

### `extract_fields_balanced`

Implemented in `extractors/extract_fields_balanced.py` as:

`extract_fields_balanced(document, metadata, schema_content, markdown_content=None, document_type="generic", structure_hints=None) -> Dict[str, Any]`

- **Inputs**:
  - `document: Document`:
    - Full text version of the document (used if `markdown_content` is not provided).
  - `metadata: DocumentMetadata`:
    - Includes `filename` and other context used in the user prompt.
  - `schema_content: Dict[str, Any]`:
    - JSON schema describing fields to extract (same structure used by `generate_system_prompt`).
  - `markdown_content: Optional[str]`:
    - Preferred content for extraction when available (output of `vision_generate_markdown`).
    - If `None` or empty, falls back to `document.page_content`.
  - `document_type: str`:
    - Document type label used to specialize the system prompt via `generate_system_prompt(document_type, schema_content)`.
  - `structure_hints: Optional[Dict[str, Any]]`:
    - Structural metadata from the vision stage (tables, multi-column, section counts, etc.).
    - Used to enrich the user prompt but **not** part of the Pydantic model.

- **Outputs**:
  - A `Dict[str, Any]`:
    - Keys correspond exactly to field names from the schema.
    - Values are typed according to the dynamically built Pydantic model.

- **Dynamic schema/model construction**:
  - Reads `fields = schema_content.get("fields", [])`.
  - If `fields` is empty:
    - Immediately returns `{}` (no extraction attempted).
  - Uses `_get_python_type` to map field `type` strings (e.g. `"string"`, `"integer"`, `"list[object]"`) to Python types.
  - Builds a dynamic `BaseModel` subclass via `_create_dynamic_model(schema)` where:
    - Each schema field becomes a Pydantic field with description.
    - Required fields stay required; non-required fields become `Optional[...]` with default `None`.

- **Content selection and caching**:
  - Chooses `content_to_use`:
    - `markdown_content` if provided, else `document.page_content or ""`.
  - Builds a cache key using `generate_cache_key` with:
    - `content = content_to_use`.
    - `extra_params = {"step": "extract_fields_balanced", "schema": schema_content, "doc_type": document_type, "hints": structure_hints}`.
  - Checks `EXTRACTION_CACHE_DIR` via `get_cached_result`.
  - If cached result exists and has at least one non-`None` value:
    - Returns it immediately (skips LLM).
  - If cached result exists but all values are `None`:
    - Treats it as a failed/empty extraction and continues to recompute.

- **Prompt construction**:
  - Builds a human-readable **fields block** summarizing each schema field: `- name (type): description`.
  - Calls `generate_system_prompt(document_type, schema_content)` to obtain the LLM **system prompt**.
  - Converts `structure_hints` (if any) into a short bullet list, e.g. table counts, column names, multi-column layout, etc., appended as "Structural hints".
  - Constructs a `user_prompt` that includes:
    - Extraction instructions (do not invent data, null/empty list for missing fields).
    - The filename.
    - The fields block.
    - The structural hints section (if present).
    - The full `content_to_use` (markdown or raw text) delimited by separators.

- **LLM call and model**:
  - Uses `ChatOpenAI` with:
    - `model = os.getenv("EXTRACTION_MODEL", "gpt-4o-mini")` (overrideable via env var).
    - `temperature = 0`.
    - `.with_structured_output(DynamicModel, method="function_calling")` where `DynamicModel` is the dynamic Pydantic model.
  - Sends the system prompt from `generate_system_prompt` and the constructed user prompt.
  - Receives a typed Pydantic instance and converts it to a `dict` via `model.model_dump()`.

- **Post-processing and cache write**:
  - If the result dict is non-empty and any value is not `None`:
    - Saves it to `EXTRACTION_CACHE_DIR` with the same cache key.
  - Returns the result dict to the caller.

---

## 5. Basic extraction workflow

- Workflow contains only `extract_fields_basic`.
- No vision step; simpler text-only path.

Implemented in `extractors/extract_fields_basic.py` as:

`extract_fields_basic(document, metadata, schema_content, document_type="generic") -> Dict[str, Any]`

- **Inputs**:
  - `document: Document`:
    - Text content (`page_content`) is normalized and used directly (no markdown).
  - `metadata: DocumentMetadata`:
    - Provides `filename` for prompt context.
  - `schema_content: Dict[str, Any]`:
    - Direct schema definition (same format as `schema_content` in balanced workflow).
  - `document_type: str`:
    - Used to specialize the system prompt via `generate_system_prompt(document_type, schema_content)`.

- **Outputs**:
  - A `Dict[str, Any]`:
    - Keys are schema field names.
    - Values are typed according to a dynamically built Pydantic model (same pattern as balanced).

- **Behavior and caching**:
  - Normalizes `document.page_content` via `_normalize_garbage_characters`.
  - Builds a cache key with `generate_cache_key` using:
    - `content = normalized_text`.
    - `extra_params = {"step": "extract_fields_basic", "schema": schema_content, "doc_type": document_type}`.
  - Checks `EXTRACTION_CACHE_DIR` with `get_cached_result` and returns any cached result immediately.
  - Builds a dynamic Pydantic model from `schema_content.fields` via `_create_dynamic_model`.
  - Generates a **system prompt** using `generate_system_prompt(document_type, schema_content)` (shared with balanced workflow).
  - Constructs a user prompt containing:
    - Extraction instructions (no hallucination; null/empty list for missing).
    - Filename.
    - Human-readable description of each schema field.
    - The full normalized text content between separators.
  - Uses `ChatOpenAI(model="gpt-4o-mini", temperature=0)` with `.with_structured_output(DynamicModel, method="function_calling")` to produce a typed result.
  - Dumps the model to a dict and saves it to `EXTRACTION_CACHE_DIR` via `save_to_cache`.
  - Returns the result dict.

- **Shared prompt generation**:
  - Both **basic** and **balanced** workflows call `generate_system_prompt(document_type, schema)` from `utils.prompt_generator`.
  - This ensures consistent extraction behavior and prompt caching across workflows.

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

---

## 7. Core pipeline helpers

Implemented in `core_pipeline.py`:

- **`_normalize_garbage_characters(text) -> str`**
  - Utility used by both the router and basic extraction.
  - Collapses repeated replacement characters (e.g. `�`) to clean noisy text while preserving content.

- **`load_documents(documents_dir=None) -> Iterator[Document]`**
  - Lazily loads documents from `DOCUMENTS_DIR` (or a provided path).
  - Supports `.txt` (via `TextLoader`), `.pdf` (via `PDFPlumberLoader`), and `.docx` (via `Docx2txtLoader`).
  - For each loaded `Document`, ensures `metadata["source"]` contains the filename, which is later used by the router and metadata builder.

- **`create_document_metadata(doc, index) -> DocumentMetadata`**
  - Builds the metadata object used across workflows:
    - `document_number`, `filename`, `file_size`, `file_path`, `processed_date`.
  - Computes file size and full path under `DOCUMENTS_DIR` based on `metadata["source"]`.

- **`DocumentMetadata` model**
  - Shared between router, vision, and extraction steps to keep file context consistent throughout the pipeline.

---

## 8. End-to-end request flow (summary)

This section ties together the components above into a single, end-to-end flow for one document.

### 8.1 Loading and metadata

1. **Load document**
   - `load_documents()` (or an equivalent API path) yields a LangChain `Document` with:
     - `page_content`: raw text (from `.txt`, `.pdf`, `.docx`).
     - `metadata["source"]`: filename (e.g., `claim_001.pdf`).

2. **Build metadata**
   - `create_document_metadata(doc, index)` builds a `DocumentMetadata` instance with:
     - `document_number`, `filename`, `file_size`, `file_path`, `processed_date`.

3. **User selects schema and workflow mode**
   - Frontend/consumer chooses a schema/template (with `schema_id` and `schema_content`).
   - Optionally, a `preferred_workflow` may be stored on the template but the router can still decide per document.

### 8.2 Routing decision

4. **Route document**
   - Call `route_document(document, schema_id)`:
     - Optionally reads `document_type` from Supabase schemas table.
     - Applies `.txt` heuristic and short-content optimization.
     - Builds a text `snippet` (currently first ~4000 chars; future: multi-page sampling).
     - Checks router cache (`ROUTER_CACHE_DIR`) keyed by `(snippet, schema_id)`.
     - If cache miss and enough content, calls the LLM router to decide:
       - `workflow`: `"basic"` or `"balanced"`.
       - `document_type`: from schema if present, otherwise LLM-inferred.
     - Optionally backfills `document_type` into Supabase when missing.
     - Saves `{workflow, document_type}` to router cache and returns it.

5. **Downstream choice**
   - If `workflow == "basic"` → use the **Basic extraction workflow**.
   - If `workflow == "balanced"` → use the **Balanced workflow**.

### 8.3 Balanced workflow path

6. **Vision markdown generation** (`vision_generate_markdown`)
   - Inputs: `document`, `metadata`, `schema_content`.
   - Checks vision cache (`VISION_CACHE_DIR`) via `generate_cache_key` on `file_path` + model.
   - If cache miss and file is PDF/image, converts pages to images and calls the vision model to produce:
     - `markdown_content` (rich markdown representation).
     - `structure_hints` (tables, sections, layout cues).
   - Saves result to `VISION_CACHE_DIR` and returns it.

7. **Prompt generation** (`generate_system_prompt`)
   - Inputs: `document_type`, `schema_content`.
   - Computes `(document_type, schema_hash)` cache key.
   - Reads/writes Supabase `prompt_cache` table to reuse a stable `system_prompt` across runs and deployments.

8. **Balanced extraction** (`extract_fields_balanced`)
   - Inputs:
     - `document`, `metadata`, `schema_content`.
     - `markdown_content`, `structure_hints` from the vision step.
     - `document_type` and `system_prompt` from the router/prompt generator.
   - Selects `content_to_use = markdown_content` (or raw text fallback).
   - Checks extraction cache (`EXTRACTION_CACHE_DIR`) keyed by content + schema + doc_type + hints.
   - Dynamically builds a Pydantic model from `schema_content.fields`.
   - Calls the extraction LLM (`EXTRACTION_MODEL`, default `gpt-4o-mini`) with:
     - `system_prompt` from `generate_system_prompt`.
     - A user prompt containing schema descriptions, structural hints, and document content.
   - Returns a typed dict of extracted fields and caches non-empty results.

### 8.4 Basic workflow path

9. **Prompt generation** (shared)
   - `generate_system_prompt(document_type, schema_content)` is also used by basic extraction, sharing Supabase prompt cache entries with the balanced workflow.

10. **Basic extraction** (`extract_fields_basic`)
    - Inputs:
      - `document`, `metadata`, `schema_content`, `document_type`.
    - Normalizes raw text with `_normalize_garbage_characters`.
    - Checks extraction cache (`EXTRACTION_CACHE_DIR`) keyed by content + schema + doc_type.
    - Builds a dynamic Pydantic model from `schema_content.fields`.
    - Calls `ChatOpenAI(model="gpt-4o-mini")` with:
      - System prompt from `generate_system_prompt`.
      - User prompt containing schema descriptions and full normalized text.
    - Returns and caches the typed dict result.

### 8.5 Outputs and logging

11. **Result persistence / logging (conceptual)**
    - For each run, the system can log:
      - `content_hash` or snippet hash.
      - `document_type`.
      - `schema_id`.
      - `workflow`.
    - These records can be used later to:
      - Avoid re-routing identical content.
      - Analyze routing and extraction quality over time.

