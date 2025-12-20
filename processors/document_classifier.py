from typing import Optional
import os
import requests
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
    document_type: str = Field(
        ...,
        description="The specific type of the document (e.g., 'resume', 'invoice', 'receipt', 'contract', 'form', 'article', 'purchase_order', 'bank_statement', 'claim', 'generic')."
    )


def _make_llm_decision(snippet: str, expected_type: Optional[str] = None) -> str:
    """Perform the actual LLM call for document type classification.
    
    Args:
        snippet: Document content snippet to analyze
        expected_type: If provided, skip LLM and return this type
        
    Returns:
        Document type string
    """
    if expected_type:
        return expected_type
    
    system_prompt = (
        "You are a document classification assistant. Your job is to analyze a document snippet "
        "and identify the specific document type.\n\n"
        "Common document types include:\n"
        "- insurance_claim, medical_claim, auto_claim\n"
        "- resume, cv\n"
        "- invoice, receipt, purchase_order\n"
        "- contract, agreement\n"
        "- bank_statement, financial_statement\n"
        "- form, application\n"
        "- article, report\n"
        "- generic (for unclassifiable documents)\n\n"
        "Be specific when possible (e.g., 'insurance_claim' rather than just 'claim')."
    )

    user_prompt = f"Classify the following document content snippet:\n\n{snippet}"

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
        return result.document_type
    except Exception:
        return "generic"


def classify_document_type(document: Document, schema_id: Optional[str] = None, tenant_id: Optional[str] = None) -> str:
    """Determines document type, prioritizing schema-provided types when available.
    Updates schema with document_type if not already set.
    
    Args:
        document: Document to classify
        schema_id: Schema ID if available
        tenant_id: Tenant ID for security checks
        
    Returns:
        Document type string
    """
    # 1. Check for schema-provided document_type
    document_type = None
    if schema_id:
        document_type = get_schema_document_type(schema_id, tenant_id)

    # 2. Prepare content for analysis
    content = _normalize_garbage_characters(document.page_content or "")
    snippet = content[:2000]
    
    # 3. Check Persistence Cache
    cache_key = generate_cache_key(
        content=snippet,
        extra_params={"schema_id": schema_id}
    )
    cached = get_cached_result(cache_key, cache_dir=ROUTER_CACHE_DIR)
    if cached:
        cached_doc_type = cached.get("document_type") if isinstance(cached, dict) else cached
        # Even if cached, update schema document_type if it's not set
        if schema_id and not document_type and cached_doc_type and cached_doc_type != "generic":
            update_schema_document_type(schema_id, cached_doc_type, tenant_id)
        return cached_doc_type
    
    # 4. Short content optimization
    if len(snippet.strip()) < 50:
        return "generic"

    # 5. Make LLM Decision (only determines type if not already known from schema)
    llm_doc_type = _make_llm_decision(snippet, expected_type=document_type)
    
    # Use schema document_type if available, otherwise use LLM-determined type
    final_doc_type = document_type if document_type else llm_doc_type
    
    # 6. Update schema if new document_type was determined
    if schema_id and not document_type and llm_doc_type != "generic":
        update_schema_document_type(schema_id, llm_doc_type, tenant_id)
    
    # 7. Save to cache
    save_to_cache(
        cache_key,
        final_doc_type,
        cache_dir=ROUTER_CACHE_DIR,
    )
    
    return final_doc_type

def get_schema_document_type(schema_id: str, tenant_id: Optional[str] = None) -> Optional[str]:
    """Fetch document_type from Supabase schemas table using service role key.
    
    Args:
        schema_id: Schema ID to fetch
        tenant_id: Tenant ID for security check (allows global templates if None)
        
    Returns:
        Document type if found and accessible, None otherwise
    """
    try:
        supabase_url = os.getenv("VITE_SUPABASE_URL")
        # Use service role key for backend operations (bypasses RLS)
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY")
        
        if not supabase_url or not supabase_key:
            return None
        
        # Build query: allow global templates (tenant_id IS NULL) or tenant-owned schemas
        url = f"{supabase_url.rstrip('/')}/rest/v1/schemas?id=eq.{schema_id}"
        if tenant_id:
            url += f"&or=(tenant_id.is.null,tenant_id.eq.{tenant_id})"
        else:
            url += "&tenant_id=is.null"
        
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


def update_schema_document_type(schema_id: str, document_type: str, tenant_id: Optional[str] = None) -> None:
    """Update document_type in Supabase schemas table using service role key.
    
    Only allows updating tenant-owned schemas, not global templates.
    
    Args:
        schema_id: Schema ID to update
        document_type: Document type to set
        tenant_id: Tenant ID for security check (required to update)
    """
    try:
        supabase_url = os.getenv("VITE_SUPABASE_URL")
        # Use service role key for backend operations (bypasses RLS)
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY")
        
        if not supabase_url or not supabase_key:
            return
        
        # Only allow updating tenant-owned schemas, not global templates
        url = f"{supabase_url.rstrip('/')}/rest/v1/schemas?id=eq.{schema_id}"
        if tenant_id:
            # Require tenant_id match (no NULL check - can't modify globals)
            url += f"&tenant_id=eq.{tenant_id}"
        else:
            # No tenant_id provided, don't allow any updates
            return
        
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        
        resp = requests.patch(
            url,
            headers=headers,
            json={"document_type": document_type},
            timeout=5
        )
        _ = resp.ok
    except Exception:
        return
