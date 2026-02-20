# Document Intake & Schema Manager

This project is a document intake and schema management service. It provides:

- A **Python backend** for orchestrating document processing workflows.
- A **React + TypeScript + Vite frontend** for uploading documents and managing schemas.
- A set of **JSON templates** describing common document types.

## Project Structure

- `main.py`, `core_pipeline.py`, `workflows.py` – backend entrypoint and processing logic.
- `src/` – React frontend (Vite + TypeScript).
- `templates/` – JSON templates used to define extraction schemas.

## Templates

The `templates/` folder contains simple JSON schema definitions for common document types, including:

- `claim_schema.json`
- `invoice_schema.json`
- `resume_schema.json`
- `purchase_order_schema.json`
- `bank_statement_schema.json`

Each file declares a `document_type`, a short `description`, and a list of `fields` with basic metadata.

## Configuration

1.  **Environment Variables**: Copy `.env.example` to `.env` and fill in your API keys and Supabase credentials.
    ```bash
    cp .env.example .env
    ```
2.  **Database Setup**: The initial database schema can be found in `supabase/setup_db.sql`. This script sets up the necessary tables and functions in your Supabase project.

## Running the Backend

Create and activate a virtual environment, install dependencies, and run the API server (for example, with Uvicorn):

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Adjust the command if your entrypoint or module path differs.

## Running the Frontend

Install Node dependencies and start the Vite dev server from the project root:

```bash
npm install
npm run dev
```

Then open the printed local URL in your browser.

## Schemas and Supabase

In production, schemas are stored in the Supabase `public.schemas` table:

- `content` (jsonb): the full JSON schema (same shape as files under `templates/`).
- `document_type` (text): canonical type used for routing and prompt generation (e.g. `invoice`, `resume`).

The frontend reads `content, document_type` from Supabase and sends them to the backend as `schema_content` and `document_type` form fields. The backend treats `document_type` from the DB as the source of truth once it has been set.

For newly created/cloned schemas, the router infers `document_type` on first use and the backend writes it back into `public.schemas.document_type` so subsequent runs use the stored value.

## Prompt Generation and Caching

Both basic and balanced extraction workflows call a shared helper:

- `generate_system_prompt(document_type, schema)` in `utils/prompt_generator.py`.

Behavior:

- Computes a stable cache key based on:
  - `document_type`.
  - A hash of the canonical JSON `schema`.
- Looks for a JSON file under `.cache/` for that key.
  - If present: returns the cached `system_prompt` and **does not** call the LLM.
  - If missing: calls the LLM once to generate a new `system_prompt`, then writes it to `.cache/` for future reuse.

The `.cache` directory is created automatically on demand by `utils/cache_manager.py`.

## Warming Prompts

There are two utility scripts for pre-warming prompts so the first user request does not need to pay the prompt-generation LLM cost.

### 1. Warm from local templates (development / CLI)

Uses the JSON files under `templates/`:

```bash
python -m utils.warm_prompt_cache_local
```

This is useful when running the orchestrator or local workflows that read schemas directly from `templates/`.

### 2. Warm from Supabase schemas (production-like)

Uses the `public.schemas` table via Supabase REST so prompts are generated from the **exact** JSON the app uses at runtime:

```bash
python -m utils.warm_prompt_cache_supabase
```

Requirements:

- Environment / `.env` must provide either:
  - `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` (preferred), or
  - `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`.
- `requests` and `python-dotenv` installed in the Python environment.

This script:

- Fetches `id, name, document_type, content` from `public.schemas`.
- For each row with a non-null `document_type` and valid JSON `content`, calls `generate_system_prompt(document_type, content)`.
- This populates `.cache/` in that environment so later extractions for those schemas reuse the cached system prompts.


