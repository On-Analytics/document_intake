from typing import Literal, Dict, Optional
import hashlib
import json
import os
# from functools import lru_cache # Removed in favor of cache_manager
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from core_pipeline import _normalize_garbage_characters
from utils.cache_manager import (
    ROUTER_CACHE_DIR,
    generate_cache_key,
    get_cached_result,
    save_to_cache,
)

class RouterOutput(BaseModel):
    workflow: Literal["basic", "balanced"] = Field(
        ..., 
        description="The workflow to use for processing the document. 'basic' for simple text, 'balanced' for complex layouts/tables/handwriting."
    )
    document_type: str = Field(
        ...,
        description="The specific type of the document (e.g., 'resume', 'invoice', 'receipt', 'contract', 'form', 'article', 'purchase_order', 'bank_statement', 'claim', 'generic')."
    )


def _make_llm_decision(snippet: str, expected_type: Optional[str] = None) -> Dict[str, str]:
    """Perform the actual LLM call for routing."""
    system_prompt = (
        "You are a document routing assistant. Your job is to analyze a document snippet and decide:\n"
        "1. The best workflow ('basic' or 'balanced').\n"
        "2. The specific document type (e.g., 'insurance_claim', 'resume', 'invoice', 'contract', 'article', 'purchase_order', 'bank_statement', 'claim').\n\n"
        "Workflow Selection Criteria:\n\n"
        "Choose 'basic' for:\n"
        "- Plain text documents with simple paragraphs\n"
        "- Linear narratives (articles, stories, claims, complaints)\n"
        "- Documents that are already well-extracted as text\n"
        "- Simple contracts or agreements without complex formatting\n"
        "- Any .txt file content that reads naturally as paragraphs\n\n"
        "Choose 'balanced' ONLY for:\n"
        "- Documents with complex multi-column layouts\n"
        "- Tables requiring structure preservation\n"
        "- Forms with checkboxes or fill-in fields\n"
        "- Resumes with visual sidebars or complex formatting\n"
        "- Scanned documents with handwriting\n"
        "- Documents where visual layout is critical to understanding\n\n"
        "IMPORTANT: Default to 'basic' unless there's clear evidence of complex layout or visual structure."
    )

    user_prompt = (
        f"Analyze the following document content snippet.\n\n"
        f"Snippet:\n{snippet}\n"
    )

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0).with_structured_output(
        RouterOutput, method="function_calling"
    )

    try:
        result = llm.invoke(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            config={"run_name": "router"},
        )
        if expected_type:
            return {"workflow": result.workflow, "document_type": expected_type}
        else:
            return {"workflow": result.workflow, "document_type": result.document_type}
    except Exception:
        return {"workflow": "balanced", "document_type": "generic"}


def route_document(document: Document, schema_id: Optional[str] = None) -> Dict[str, str]:
    """
    Determines workflow and document type, prioritizing schema-provided types when available.
    Updates schema with document_type if not already set.
    """
    source = document.metadata.get("source", "").lower()
    
    # 1. Check for schema-provided document_type
    document_type = None
    if schema_id:
        document_type = get_schema_document_type(schema_id)

    # 2. Heuristics: Check file extension for workflow selection
    # .txt files use basic workflow, but still get LLM classification for document_type
    force_basic_workflow = source.endswith(".txt")
    
    # 3. Prepare content for analysis, useing utility function 
    content = _normalize_garbage_characters(document.page_content or "")
    snippet = content[:4000]
    
    # 4. Check Persistence Cache
    cache_key = generate_cache_key(
        content=snippet,
        extra_params={"schema_id": schema_id}
    )
    cached = get_cached_result(cache_key, cache_dir=ROUTER_CACHE_DIR)
    if cached:
        # Even if cached, update schema document_type if it's not set
        if schema_id and not document_type and cached.get("document_type") and cached["document_type"] != "generic":
            update_schema_document_type(schema_id, cached["document_type"])
        return cached
    
    # 5. Short content optimization
    if len(snippet.strip()) < 50:
        return {"workflow": "basic", "document_type": "generic"}

    # 6. Make LLM Decision (always determines workflow, only determines type if needed)
    decision = _make_llm_decision(snippet)
    
    # Use schema document_type if available, otherwise use LLM-determined type
    final_doc_type = document_type if document_type else decision["document_type"]
    
    # 7. Update schema if new document_type was determined
    if schema_id and not document_type and decision["document_type"] != "generic":
        update_schema_document_type(schema_id, decision["document_type"])
    
    # 8. Determine final workflow (force basic for .txt files)
    final_workflow = "basic" if force_basic_workflow else decision["workflow"]
    
    # 9. Save to cache
    save_to_cache(
        cache_key,
        {"workflow": final_workflow, "document_type": final_doc_type},
        cache_dir=ROUTER_CACHE_DIR,
    )
    
    return {"workflow": final_workflow, "document_type": final_doc_type}

def get_schema_document_type(schema_id: str) -> Optional[str]:
    """Fetch document_type from Supabase schemas table using service role key."""
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
        
        resp = requests.get(url, headers=headers, params={"select": "document_type"}, timeout=5)
        if resp.ok:
            data = resp.json()
            return data[0]["document_type"] if data else None
    except Exception:
        pass
    return None


def update_schema_document_type(schema_id: str, document_type: str) -> None:
    """Update document_type in Supabase schemas table using service role key."""
    try:
        supabase_url = os.getenv("VITE_SUPABASE_URL")
        # Use service role key for backend operations (bypasses RLS)
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY")
        
        if not supabase_url or not supabase_key:
            print(f"[Router] Cannot update schema document_type: missing Supabase env vars")
            return
            
        import requests
        url = f"{supabase_url.rstrip('/')}/rest/v1/schemas?id=eq.{schema_id}"
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        
        print(f"[Router] Updating schema {schema_id} with document_type='{document_type}'")
        resp = requests.patch(
            url,
            headers=headers,
            json={"document_type": document_type},
            timeout=5
        )
        if resp.ok:
            print(f"[Router] Successfully updated schema document_type")
        else:
            print(f"[Router] Failed to update schema document_type: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"[Router] Exception updating schema document_type: {e}")