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
        return data[0]["content"] if data else {"fields": []}
    
    except Exception as e:
        print(f"Error fetching schema: {str(e)}")
        return {"fields": []}  # Fallback empty schema