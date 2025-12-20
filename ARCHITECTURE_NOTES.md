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

The router is implemented as `classify_document_type(document, schema_id=None, tenant_id=None)` in [processors/document_classifier.py](file:///c:/Users/oscar/CascadeProjects/DocumentProcessor/document_intake/processors/document_classifier.py).

- **Inputs**:
  - `document`: a LangChain `Document` with `page_content` and `metadata` (especially `metadata["source"]`).
  - `schema_id` (optional): Supabase schema ID used to read/update `document_type` and for routing cache keys.

- **Outputs**:
  - A `dict` with:
    - `workflow`: `"basic"` or `"balanced"`.
    - `document_type`: final document type string used downstream (may come from schema or LLM).

### 3.1 High-level decision flow (Multi-Layered Caching)

The system uses a hierarchical approach to identify the document type, prioritizing speed and cost-efficiency:

1. **Layer 1: Database-Provided document_type (Highest Priority)**
   - Before any AI or file checks, `get_schema_document_type(schema_id, tenant_id)` is called.
   - It checks the Supabase `schemas` table for a `document_type` associated with that schema and tenant.
   - If found, this value is used as the **authoritative** type. **The AI classification call is skipped entirely.**
   - If missing, the system moves to Layer 2.

2. **Layer 2: Router Cache Lookup (File-Content Hashing)**
   - Computes a unique cache key based on the first 2,000 characters of the document and the `schema_id`.
   - Looks up this key in the local `.router_cache/` directory.
   - If a match is found, the cached result is returned instantly. **The AI classification call is skipped.**

3. **Layer 3: LLM Router Decision (The "Thinking" Step)**
   - Only if Layer 1 and 2 fail, the system calls `gpt-4o-mini`.
   - It performs a structured classification to determine the `document_type`.
   - The result is then:
     - Written back to Supabase (Layer 1 backfill) so future runs skip the AI.
     - Saved to the `.router_cache/` (Layer 2) for near-instant repeated access.

### 3.2 Snippet Construction & Optimization

- **Normalize content**: Uses `_normalize_garbage_characters` to clean noisy text.
- **Snippet size**: Takes the first **2,000 characters** for routing. This is sufficient to cover the header/first page where most identifying context resides.
- **Short-content optimization**: If the snippet has < 50 characters, it instantly returns `document_type = "generic"` without calling the LLM.

### 3.3 Per-File Workflow Selection

The final workflow for a specific file is determined by `_determine_workflow(extension, length)`:
- **"basic"**: Triggered for `.txt` files or very short content (< 50 characters).
- **"balanced"**: Default for all other files (PDFs, Docx, Images), utilizing the Vision-enhanced pipeline.

---

## 4. Balanced workflow

The **balanced** workflow (Vision-Enhanced) involves two primary stages before final extraction:

### `vision_generate_markdown`

Implemented in [processors/vision_generate_markdown.py](file:///c:/Users/oscar/CascadeProjects/DocumentProcessor/document_intake/processors/vision_generate_markdown.py) as:

`vision_generate_markdown(document, metadata, schema_content) -> Dict[str, Any]`

- **Operation**: 
  - Converts PDFs or images into base64 images.
  - Calls `gpt-4o-mini` (Vision) to produce a structured **Markdown** representation.
  - Runs `_analyze_markdown_structure` to extract `structure_hints` (tables, multi-column signs, etc.).

### `prompt_generator`

Implemented in [utils/prompt_generator.py](file:///c:/Users/oscar/CascadeProjects/DocumentProcessor/document_intake/utils/prompt_generator.py) as:

`generate_system_prompt(document_type, schema, tenant_id=None, schema_id=None, user_token=None) -> str`

- **Operation**:
  - Dynamically builds a set of instructions tailored to the specific `document_type` and JSON schema.
  - Utilizes the **Supabase `prompt_cache`** to ensure expensive instruction generation only happens once per (Type + Schema) combination.

### `extract_fields_balanced`

Implemented in [processors/extract_fields_balanced.py](file:///c:/Users/oscar/CascadeProjects/DocumentProcessor/document_intake/processors/extract_fields_balanced.py) as:

`extract_fields_balanced(schema_content, system_prompt, markdown_content, document_type="generic", structure_hints=None) -> Dict[str, Any]`

- **Operation**:
  - Dynamically creates a **Pydantic model** matching the selected schema.
  - Combines the pre-computed `system_prompt`, `markdown_content`, and `structure_hints` into a comprehensive request to `gpt-4o-mini`.
  - Returns raw JSON extraction results.

- **Dynamic schema/model construction**:
  - Reads `fields = schema_content.get("fields", [])`.
  - Uses `_get_python_type` to map field `type` strings (e.g. `"string"`, `"integer"`, `"list[object]"`) to Python types.
  - Builds a dynamic `BaseModel` subclass via `_create_dynamic_model(schema)`.

- **LLM call and model**:
  - Uses `ChatOpenAI` with `model = os.getenv("EXTRACTION_MODEL", "gpt-4o-mini")`.
  - Sends the system prompt from `generate_system_prompt` and a constructed user prompt containing structural hints and content.
  - Returns the result dict.

---

## 5. Basic extraction workflow

The **basic** workflow is used for plain text documents or simple content that doesn't require Vision analysis.

### `extract_fields_basic`

Implemented in [processors/extract_fields_basic.py](file:///c:/Users/oscar/CascadeProjects/DocumentProcessor/document_intake/processors/extract_fields_basic.py) as:

`extract_fields_basic(document, metadata, schema_content, document_type="generic", system_prompt=None) -> Dict[str, Any]`

- **Operation**:
  - Uses the same dynamic **Pydantic model** and `system_prompt` as the balanced workflow.
  - Operates on the raw text content (`router_doc`) instead of markdown.
  - Ideal for low-cost, high-speed extraction from clean text files.

---

## 6. Prompt caching

- `generate_system_prompt(document_type, schema)`:
  - First call for a `(document_type, schema)` pair:
    - Calls LLM.  
    - Saves the resulting `system_prompt` to the Supabase `prompt_cache` table (when configured).
  - Subsequent calls for the same pair:
    - No LLM call.  
    - System prompt is reused from the Supabase `prompt_cache` table.

- We can warm this cache ahead of time for standard templates via `utils/warm_prompt_cache.py` so first-time users don’t pay the LLM cost for prompt generation on those schemas.

---

## 9. Batch processing modes (`/process-batch`)

The batch endpoint (`POST /process-batch` in `main.py`) supports two high-level modes for determining `document_type` and choosing a workflow.

### 9.1 Optimistic Mode (Parallel Processing)

Optimistic Mode activates when a `schema_id` or explicit `document_type` is provided upfront.

- **Operation**:
  - The system bypasses the leader-follower bottleneck.
  - All files in the batch are processed concurrently (limited by `BATCH_SEMAPHORE` of 5).
  - Each file independently fetches the cached system prompt and executes its determined workflow (`basic` or `balanced`).

### 9.2 Leader–Follower Mode (Legacy Support)

Used when the `document_type` is unknown and no schema is provided (rare in current configuration).

- **Leader**: Runs the classification/routing and generates the system prompt.
- **Followers**: Wait for the leader to complete, then reuse the `shared_context` (Type, Schema, Prompt) to process their specific content.

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

4. **Classify document type**
   - Call `classify_document_type(document, schema_id, tenant_id)` in `processors/document_classifier.py`:
     - **Layer 1**: Performs instant database lookup for `document_type` on the schema.
     - **Layer 2**: Checks `.router_cache` using a hash of the first **2,000 chars**.
     - **Layer 3**: Calls LLM (`gpt-4o-mini`) to classify content if layers 1 & 2 fail.
     - Applies `.txt` heuristic and short-content optimization.
     - Automatically backfills `document_type` into Supabase once determined.
     - Returns final `document_type` to the pipeline.

5. **Downstream choice**
   - If `workflow == "basic"` → use the **Basic extraction workflow**.
   - If `workflow == "balanced"` → use the **Balanced workflow**.

### 8.3 Balanced workflow path

6. **Vision markdown generation** (`vision_generate_markdown`)
   - Inputs: `document`, `metadata`, `schema_content`.
   - If file is PDF/image, converts pages to images and calls the vision model to produce:
     - `markdown_content` (rich markdown representation).
     - `structure_hints` (tables, sections, layout cues).
   - Returns the result.

7. **Prompt generation** (`generate_system_prompt`)
   - Inputs: `document_type`, `schema_content`, `tenant_id`, `schema_id`, `user_token`.
   - Computes `(document_type, schema_hash)` cache key.
   - Reads/writes Supabase `prompt_cache` table to reuse a stable `system_prompt`.

8. **Balanced extraction** (`extract_fields_balanced`)
   - Inputs: `schema_content`, `system_prompt`, `markdown_content`, `document_type`, `structure_hints`.
   - Runs `extract_fields_balanced` as detailed in Section 4.
   - Returns a typed dict of extracted fields.

### 8.4 Basic workflow path

9. **Prompt generation** (shared)
   - `generate_system_prompt(document_type, schema_content)` is also used by basic extraction, sharing Supabase prompt cache entries with the balanced workflow.

10. **Basic extraction** (`extract_fields_basic`)
    - Inputs:
      - `document`, `metadata`, `schema_content`, `document_type`.
    - Normalizes raw text with `_normalize_garbage_characters`.
    - Builds a dynamic Pydantic model from `schema_content.fields`.
    - Calls `ChatOpenAI(model="gpt-4o-mini")` with:
      - System prompt from `generate_system_prompt`.
      - User prompt containing schema descriptions and full normalized text.
    - Returns the typed dict result.

### 8.5 Persistence and Logging

11. **Supabase Storage**
    - **Documents Table**: Stores per-file metadata (`filename`, `file_size`, `page_count`, `tenant_id`).
    - **Extraction Results Table**: Stores the actual results (`status`, `field_count`, `processing_duration_ms`, `workflow`, `batch_id`).
    - **Deferred Persistence**: For high-volume batches, extraction results are collected and written in chunks to optimize database performance.

