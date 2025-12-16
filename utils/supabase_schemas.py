import os
import json
from typing import Dict, Any, Optional

def get_schema_content(schema_id: str) -> Dict[str, Any]:
    """Fetch schema content from Supabase using service role key to bypass RLS."""
    try:
        supabase_url = os.getenv("VITE_SUPABASE_URL")
        # Use service role key for backend operations (bypasses RLS)
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY")
        
        if not supabase_url or not supabase_key:
            print(f"[Schema] Missing Supabase credentials")
            raise ValueError("Supabase credentials not configured")
            
        import requests
        url = f"{supabase_url.rstrip('/')}/rest/v1/schemas?id=eq.{schema_id}"
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
        }
        
        print(f"[Schema] Fetching schema {schema_id}")
        resp = requests.get(url, headers=headers, params={"select": "content"}, timeout=5)
        print(f"[Schema] Response status: {resp.status_code}, body: {resp.text[:500] if resp.text else 'empty'}")
        resp.raise_for_status()
        data = resp.json()
        if not data:
            print(f"[Schema] No schema found for id={schema_id} (empty array returned)")
            return {"fields": []}

        content = data[0].get("content")
        print(f"[Schema] Raw content type: {type(content)}, has fields: {'fields' in content if isinstance(content, dict) else 'N/A'}")

        # Supabase returns jsonb as objects, but if the column is text we may
        # receive a string. Normalize to dict to avoid empty-field extractions.
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                print(f"[Schema] Failed to parse content as JSON")
                return {"fields": []}

        if not isinstance(content, dict):
            print(f"[Schema] Content is not a dict: {type(content)}")
            return {"fields": []}

        fields_count = len(content.get("fields", []))
        print(f"[Schema] Loaded schema with {fields_count} fields")
        return content
    
    except Exception as e:
        print(f"[Schema] Exception fetching schema: {e}")
        return {"fields": []}  # Fallback empty schema


def get_schema_details(schema_id: str) -> Optional[Dict[str, Any]]:
    """Fetch full schema details including document_type and content."""
    try:
        supabase_url = os.getenv("VITE_SUPABASE_URL")
        # Use service role key for backend operations (bypasses RLS)
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY")
        
        if not supabase_url or not supabase_key:
            return None
            
        import requests
        url = f"{supabase_url.rstrip('/')}/rest/v1/schemas?id=eq.{schema_id}"
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
        }
        
        resp = requests.get(url, headers=headers, params={"select": "id,document_type,content"}, timeout=5)
        if resp.ok:
            data = resp.json()
            if data:
                return data[0]
        return None
    except Exception as e:
        print(f"[Schema] Exception fetching schema details: {e}")
        return None


def delete_schema(schema_id: str) -> bool:
    """Delete a schema from the Supabase schemas table."""
    try:
        supabase_url = os.getenv("VITE_SUPABASE_URL")
        # Use service role key for backend operations (bypasses RLS)
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY")
        
        if not supabase_url or not supabase_key:
            return False
            
        import requests
        url = f"{supabase_url.rstrip('/')}/rest/v1/schemas?id=eq.{schema_id}"
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
        }
        
        print(f"[Schema] Deleting schema {schema_id}")
        resp = requests.delete(url, headers=headers, timeout=5)
        # Supabase returns 204 No Content on successful delete
        return resp.status_code in [200, 204]
    except Exception as e:
        print(f"[Schema] Exception deleting schema: {e}")
        return False