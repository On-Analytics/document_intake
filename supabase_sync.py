import json
import os
from typing import Optional

try:
    import requests
except ImportError:  # pragma: no cover - optional dependency
    requests = None  # type: ignore[assignment]


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")


def update_schema_document_type(schema_id: Optional[str], document_type: Optional[str]) -> None:
    """Best-effort sync of document_type into Supabase schemas table.

    This is intentionally a no-op if:
    - SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are not configured, or
    - requests is not installed, or
    - schema_id / document_type are missing.

    It uses the standard Supabase REST endpoint:
      PATCH /rest/v1/schemas?id=eq.<schema_id>
    """
    if not schema_id or not document_type:
        return

    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return

    if requests is None:
        print("[SupabaseSync] 'requests' not installed, skipping schema document_type update.")
        return

    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/schemas?id=eq.{schema_id}"
    payload = {"document_type": document_type}

    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    try:
        resp = requests.patch(url, headers=headers, data=json.dumps(payload), timeout=5)
        if not resp.ok:
            print(f"[SupabaseSync] Failed to update document_type for schema {schema_id}: {resp.status_code} {resp.text}")
    except Exception as e:  # pragma: no cover - best effort only
        print(f"[SupabaseSync] Error updating document_type for schema {schema_id}: {e}")
