from typing import Dict, Any, Optional
import json
import hashlib
import os
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

class SystemPromptOutput(BaseModel):
    system_prompt: str = Field(..., description="The generated system prompt for the extraction task.")


def _get_supabase_headers() -> Dict[str, str]:
    """Get Supabase API headers."""
    supabase_key = os.getenv("VITE_SUPABASE_ANON_KEY", "")
    return {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _get_cached_prompt_from_supabase(cache_key: str) -> Optional[str]:
    """Fetch cached prompt from Supabase prompt_cache table."""
    try:
        import requests
        supabase_url = os.getenv("VITE_SUPABASE_URL")
        if not supabase_url:
            return None
        
        url = f"{supabase_url.rstrip('/')}/rest/v1/prompt_cache"
        params = {"cache_key": f"eq.{cache_key}", "select": "system_prompt"}
        
        resp = requests.get(url, headers=_get_supabase_headers(), params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        
        if data and len(data) > 0:
            return data[0].get("system_prompt")
        return None
    except Exception:
        return None


def _save_prompt_to_supabase(cache_key: str, document_type: str, schema_hash: str, system_prompt: str) -> bool:
    """Save generated prompt to Supabase prompt_cache table."""
    try:
        import requests
        supabase_url = os.getenv("VITE_SUPABASE_URL")
        if not supabase_url:
            return False
        
        url = f"{supabase_url.rstrip('/')}/rest/v1/prompt_cache"
        payload = {
            "cache_key": cache_key,
            "document_type": document_type,
            "schema_hash": schema_hash,
            "system_prompt": system_prompt,
        }
        
        resp = requests.post(url, headers=_get_supabase_headers(), json=payload, timeout=5)
        resp.raise_for_status()
        return True
    except Exception:
        return False

def generate_system_prompt(
    document_type: str, 
    schema: Dict[str, Any],
) -> str:
    """
    Generates a specialized system prompt for extracting data from a specific document type
    according to a given schema.
    
    Cached in Supabase prompt_cache table for persistence across deployments.
    """
    
    # Compute a stable hash of the schema based on canonical JSON
    # This ensures that logically identical schemas (e.g., from templates or Supabase)
    # map to the same cache key, even if key order differs.
    schema_canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    schema_hash = hashlib.sha256(schema_canonical.encode("utf-8")).hexdigest()

    # Generate cache key from document_type and schema_hash
    cache_key = hashlib.sha256(f"{document_type}:{schema_hash}".encode("utf-8")).hexdigest()
    
    # Check Supabase cache first (persistent across deployments)
    cached_prompt = _get_cached_prompt_from_supabase(cache_key)
    if cached_prompt:
        print(f"[Prompt Generator] Using cached prompt from Supabase for '{document_type}'")
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
        saved = _save_prompt_to_supabase(cache_key, document_type, schema_hash, result.system_prompt)
        if saved:
            print(f"[Prompt Generator] Saved prompt to Supabase cache for '{document_type}'")
        else:
            print(f"[Prompt Generator] Warning: Failed to save prompt to Supabase cache")
        
        return result.system_prompt
    except Exception as e:
        print(f"Prompt generation failed, using fallback. Error: {e}")
        # Fallback prompt
        return (
            "You are an expert information extraction assistant. "
            "Your task is to extract structured data from documents to match a specific schema exactly. "
            "Pay close attention to nested fields and ensure all available details are captured."
        )
