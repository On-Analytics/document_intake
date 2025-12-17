from typing import Dict, Any, Optional
import json
import hashlib
import os
from pathlib import Path
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

# Local cache directory (fallback for testing without Supabase)
LOCAL_PROMPT_CACHE_DIR = Path(__file__).parent.parent / ".prompt_cache"

class SystemPromptOutput(BaseModel):
    system_prompt: str = Field(..., description="The generated system prompt for the extraction task.")


def _get_supabase_headers(user_token: Optional[str] = None) -> Dict[str, str]:
    """Get Supabase API headers."""
    supabase_key = os.getenv("VITE_SUPABASE_ANON_KEY", "")
    auth_token = user_token if user_token else supabase_key
    return {
        "apikey": supabase_key,
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _get_cached_prompt_from_supabase(
    *,
    cache_key: str,
    tenant_id: Optional[str] = None,
    schema_id: Optional[str] = None,
    schema_content_hash: Optional[str] = None,
    user_token: Optional[str] = None,
) -> Optional[str]:
    """Fetch cached prompt from Supabase prompt_cache table."""
    try:
        import requests
        supabase_url = os.getenv("VITE_SUPABASE_URL")
        if not supabase_url:
            return None
        
        url = f"{supabase_url.rstrip('/')}/rest/v1/prompt_cache"

        params: Dict[str, str] = {
            "select": "system_prompt,created_at",
            "order": "created_at.desc",
            "limit": "1",
        }

        if schema_id and schema_content_hash:
            if tenant_id:
                params["tenant_id"] = f"eq.{tenant_id}"
            else:
                params["tenant_id"] = "is.null"
            params["schema_id"] = f"eq.{schema_id}"
            params["schema_content_hash"] = f"eq.{schema_content_hash}"
        else:
            params["cache_key"] = f"eq.{cache_key}"
        
        resp = requests.get(url, headers=_get_supabase_headers(user_token), params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        
        if data and len(data) > 0:
            return data[0].get("system_prompt")
        return None
    except Exception:
        return None


def _save_prompt_to_supabase(
    *,
    cache_key: str,
    document_type: str,
    schema_hash: str,
    schema_content_hash: str,
    system_prompt: str,
    tenant_id: Optional[str] = None,
    schema_id: Optional[str] = None,
    user_token: Optional[str] = None,
) -> bool:
    """Save generated prompt to Supabase prompt_cache table."""
    try:
        import requests
        supabase_url = os.getenv("VITE_SUPABASE_URL")
        if not supabase_url:
            return False
        
        url = f"{supabase_url.rstrip('/')}/rest/v1/prompt_cache"

        payload: Dict[str, Any] = {
            "cache_key": cache_key,
            "document_type": document_type,
            "schema_hash": schema_hash,
            "schema_content_hash": schema_content_hash,
            "system_prompt": system_prompt,
        }

        if tenant_id:
            payload["tenant_id"] = tenant_id
        if schema_id:
            payload["schema_id"] = schema_id
        
        resp = requests.post(url, headers=_get_supabase_headers(user_token), json=payload, timeout=5)
        if resp.status_code == 409:
            return True

        resp.raise_for_status()
        return True
    except Exception:
        return False


def delete_prompt_from_cache(cache_key: str) -> bool:
    """Delete a prompt from the Supabase prompt_cache table."""
    try:
        import requests
        supabase_url = os.getenv("VITE_SUPABASE_URL")
        if not supabase_url:
            return False
        
        url = f"{supabase_url.rstrip('/')}/rest/v1/prompt_cache"
        params = {"cache_key": f"eq.{cache_key}"}
        
        print(f"[Prompt Generator] Deleting prompt cache for key: {cache_key}")
        resp = requests.delete(url, headers=_get_supabase_headers(), params=params, timeout=5)
        # Supabase returns 204 No Content on successful delete
        return resp.status_code in [200, 204]
    except Exception as e:
        print(f"[Prompt Generator] Failed to delete prompt cache: {e}")
        return False


def _get_cached_prompt_local(cache_key: str) -> Optional[str]:
    """Fetch cached prompt from local file (fallback for testing)."""
    try:
        cache_file = LOCAL_PROMPT_CACHE_DIR / f"{cache_key}.txt"
        if cache_file.exists():
            return cache_file.read_text(encoding="utf-8")
        return None
    except Exception:
        return None


def _save_prompt_local(cache_key: str, system_prompt: str) -> bool:
    """Save generated prompt to local file (fallback for testing)."""
    try:
        LOCAL_PROMPT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file = LOCAL_PROMPT_CACHE_DIR / f"{cache_key}.txt"
        cache_file.write_text(system_prompt, encoding="utf-8")
        return True
    except Exception:
        return False


def calculate_prompt_cache_key(document_type: str, schema: Dict[str, Any]) -> tuple[str, str]:
    """
    Calculate the cache key and schema hash for a given document type and schema.
    Returns (cache_key, schema_hash).
    """
    # Compute a stable hash of the schema based on canonical JSON
    # This ensures that logically identical schemas (e.g., from templates or Supabase)
    # map to the same cache key, even if key order differs.
    schema_canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    schema_hash = hashlib.sha256(schema_canonical.encode("utf-8")).hexdigest()

    # Generate cache key from document_type and schema_hash
    cache_key = hashlib.sha256(f"{document_type}:{schema_hash}".encode("utf-8")).hexdigest()
    
    return cache_key, schema_hash

def generate_system_prompt(
    document_type: str, 
    schema: Dict[str, Any],
    tenant_id: Optional[str] = None,
    schema_id: Optional[str] = None,
    user_token: Optional[str] = None,
) -> str:
    """
    Generates a specialized system prompt for extracting data from a specific document type
    according to a given schema.
    
    Cached in Supabase prompt_cache table for persistence across deployments.
    """
    
    cache_key, schema_hash = calculate_prompt_cache_key(document_type, schema)
    schema_content_hash = schema_hash
    
    # Check Supabase cache first (persistent across deployments)
    cached_prompt = _get_cached_prompt_from_supabase(
        cache_key=cache_key,
        tenant_id=tenant_id,
        schema_id=schema_id,
        schema_content_hash=schema_content_hash,
        user_token=user_token,
    )
    if cached_prompt:
        print(f"[Prompt Generator] Using cached prompt from Supabase for '{document_type}'")
        return cached_prompt
    
    # Fallback: check local file cache (for testing without Supabase)
    cached_prompt = _get_cached_prompt_local(cache_key)
    if cached_prompt:
        print(f"[Prompt Generator] Using cached prompt from LOCAL file for '{document_type}'")
        return cached_prompt
    
    # Convert schema to a string representation for the prompt
    schema_str = json.dumps(schema, indent=2)
    
    meta_system_prompt = (
        "You are an expert Prompt Engineer and Data Extraction Architect. "
        "Your task is to generate a highly optimized *System Prompt* that will guide an AI assistant "
        "to extract structured data from documents of any type. "
        "Focus on clarity, constraint-setting, and schema alignment."
    )
    
    # Removed specific structure_hints logic here to make prompt generic and cacheable
    
    user_prompt = (
        f"I need a system prompt for an AI that extracts data from a **{document_type}**.\n"
        f"The extraction must strictly follow this JSON schema:\n"
        f"```json\n{schema_str}\n```\n"
        "Instructions for the generated system prompt:\n"
        "1. It must instruct the AI to act as an expert in reading this specific document type.\n"
        "2. It must emphasize extracting nested fields (lists of objects) correctly by inferring structure from descriptions.\n"
        "3. For document types with tables (invoices, receipts, bank statements, forms):\n"
        "   - The AI must handle markdown tables where data may span multiple rows\n"
        "   - The AI must carefully merge multi-row entries into single objects\n"
        "4. It must enforce strict adherence to the schema keys.\n"
        "5. The output should be ONLY the system prompt text, ready to be used."
    )


    llm = ChatOpenAI(model="gpt-4o", temperature=0).with_structured_output(
        SystemPromptOutput, method="function_calling"
    )

    try:
        print(f"[Prompt Generator] Generating new prompt for '{document_type}' (not in cache)")
        result = llm.invoke(
            [
                {"role": "system", "content": meta_system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            config={"run_name": "prompt_generator"},
        )
        
        # Save to Supabase cache for persistence
        saved = _save_prompt_to_supabase(
            cache_key=cache_key,
            document_type=document_type,
            schema_hash=schema_hash,
            schema_content_hash=schema_content_hash,
            system_prompt=result.system_prompt,
            tenant_id=tenant_id,
            schema_id=schema_id,
            user_token=user_token,
        )
        if saved:
            print(f"[Prompt Generator] Saved prompt to Supabase cache for '{document_type}'")
        else:
            # Fallback: save to local file cache (for testing)
            local_saved = _save_prompt_local(cache_key, result.system_prompt)
            if local_saved:
                print(f"[Prompt Generator] Saved prompt to LOCAL file cache for '{document_type}'")
            else:
                print(f"[Prompt Generator] Warning: Failed to save prompt to any cache")
        
        return result.system_prompt
    except Exception as e:
        print(f"Prompt generation failed, using fallback. Error: {e}")
        # Fallback prompt
        return (
            "You are an expert information extraction assistant. "
            "Your task is to extract structured data from documents to match a specific schema exactly. "
            "Pay close attention to nested fields and ensure all available details are captured."
        )
