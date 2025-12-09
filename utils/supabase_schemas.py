import os
import json
from typing import Dict, Any

def get_schema_content(schema_id: str) -> Dict[str, Any]:
    """Fetch schema content from Supabase."""
    try:
        supabase_url = os.getenv("VITE_SUPABASE_URL")
        supabase_key = os.getenv("VITE_SUPABASE_ANON_KEY")
        
        if not supabase_url or not supabase_key:
            raise ValueError("Supabase credentials not configured")
            
        import requests
        url = f"{supabase_url.rstrip('/')}/rest/v1/schemas?id=eq.{schema_id}"
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
        }
        
        resp = requests.get(url, headers=headers, params={"select": "content"}, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return {"fields": []}

        content = data[0].get("content")
        
        # Debug: Log raw content from Supabase
        print(f"[get_schema_content] Raw content type: {type(content)}")
        print(f"[get_schema_content] Raw content preview: {str(content)[:300]}")

        # Supabase returns jsonb as objects, but if the column is text we may
        # receive a string. Normalize to dict to avoid empty-field extractions.
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                print("Error: Supabase schema content is not valid JSON string.")
                return {"fields": []}

        if not isinstance(content, dict):
            print("Error: Supabase schema content is not a JSON object.")
            return {"fields": []}

        # Debug: Log parsed content structure
        print(f"[get_schema_content] Parsed content keys: {content.keys()}")
        print(f"[get_schema_content] Fields count: {len(content.get('fields', []))}")
        
        return content
    
    except Exception as e:
        print(f"Error fetching schema: {str(e)}")
        return {"fields": []}  # Fallback empty schema