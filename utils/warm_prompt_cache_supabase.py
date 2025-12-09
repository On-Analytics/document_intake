import json
import os
from typing import Any, Dict, List

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None  # type: ignore[assignment]

try:
    import requests
except ImportError:  # pragma: no cover - optional dependency
    requests = None  # type: ignore[assignment]

from utils.prompt_generator import generate_system_prompt

# Load environment variables from a local .env file if python-dotenv is
# available. This makes it easy to reuse the same Vite/Supabase vars in
# this warm script without manually exporting them in the shell.
if load_dotenv is not None:
    load_dotenv()

# Prefer the Vite-style env vars used by the frontend, but fall back to the
# generic SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY if present.
SUPABASE_URL = os.getenv("VITE_SUPABASE_URL") or os.getenv("SUPABASE_URL")
SUPABASE_API_KEY = os.getenv("VITE_SUPABASE_ANON_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")


def _fetch_schemas() -> List[Dict[str, Any]]:
    """Fetch public schemas from Supabase.

    We read from the `schemas` table using the REST API so we warm prompts
    against the *same* JSON that production uses at runtime.
    """
    if not SUPABASE_URL or not SUPABASE_API_KEY:
        print("[WARM-SUPABASE] SUPABASE_URL or Supabase API key not set; skipping.")
        return []

    if requests is None:
        print("[WARM-SUPABASE] 'requests' not installed; cannot contact Supabase.")
        return []

    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/schemas"

    # Select only what we need; you can adjust the filter (e.g. is_public=eq.true)
    params = {
        "select": "id,name,document_type,content,is_public",
    }

    headers = {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
        "Accept": "application/json",
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        if not resp.ok:
            print(f"[WARM-SUPABASE] Failed to fetch schemas: {resp.status_code} {resp.text}")
            return []
        data = resp.json()
        if not isinstance(data, list):
            print("[WARM-SUPABASE] Unexpected response format from Supabase.")
            return []
        return data
    except Exception as e:  # pragma: no cover - best-effort only
        print(f"[WARM-SUPABASE] Error fetching schemas: {e}")
        return []


def warm_prompt_cache_from_supabase() -> None:
    """Pre-generate and cache system prompts for schemas stored in Supabase.

    For each row in `public.schemas` that has a non-null document_type and
    valid JSON `content`, this will call generate_system_prompt(document_type,
    content). The prompt generator will then either hit `.cache` or call the
    LLM once and store the result there.
    """
    schemas = _fetch_schemas()
    if not schemas:
        print("[WARM-SUPABASE] No schemas fetched; nothing to warm.")
        return

    for row in schemas:
        schema_id = row.get("id")
        name = row.get("name") or "<unnamed>"
        document_type = row.get("document_type")
        content = row.get("content")

        if not document_type:
            print(f"[WARM-SUPABASE] Skipping schema {schema_id} ('{name}') without document_type.")
            continue

        if not isinstance(content, dict):
            print(f"[WARM-SUPABASE] Skipping schema {schema_id} ('{name}') with non-object content.")
            continue

        print(f"[WARM-SUPABASE] Warming prompt for schema {schema_id} ('{name}') type='{document_type}'...")
        system_prompt = generate_system_prompt(document_type, content)
        print(f"[WARM-SUPABASE] Cached system prompt for '{document_type}' (len={len(system_prompt)})")


if __name__ == "__main__":
    warm_prompt_cache_from_supabase()
