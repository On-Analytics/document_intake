from typing import Literal, Dict, Optional
import hashlib
# from functools import lru_cache # Removed in favor of cache_manager
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from core_pipeline import _normalize_garbage_characters
from utils.cache_manager import generate_cache_key, get_cached_result, save_to_cache

class RouterOutput(BaseModel):
    workflow: Literal["basic", "balanced"] = Field(
        ..., 
        description="The workflow to use for processing the document. 'basic' for simple text, 'balanced' for complex layouts/tables/handwriting."
    )
    document_type: str = Field(
        ...,
        description="The specific type of the document (e.g., 'resume', 'invoice', 'receipt', 'contract', 'form', 'article', 'generic')."
    )


def _make_llm_decision(snippet: str) -> Dict[str, str]:
    """Perform the actual LLM call for routing."""
    system_prompt = (
        "You are a document routing assistant. Your job is to analyze a document snippet and decide:\n"
        "1. The best workflow ('basic' or 'balanced').\n"
        "2. The specific document type (e.g., 'insurance_claim', 'resume', 'invoice', 'contract', 'article').\n\n"
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
        return {"workflow": result.workflow, "document_type": result.document_type}
    except Exception as e:
        print(f"Router failed, defaulting to 'balanced'/'generic'. Error: {e}")
        return {"workflow": "balanced", "document_type": "generic"}


def route_document(document: Document) -> Dict[str, str]:
    """
    Determines which workflow to use and classifies the document type.
    Uses persistent caching to minimize LLM calls.
    
    Returns:
        {"workflow": "basic"|"balanced", "document_type": str}
    """
    
    # 1. Heuristics: Check file extension if available
    source = document.metadata.get("source", "").lower()
    if source.endswith(".txt"):
        print(f"[{source}] Smart Route: .txt extension -> basic/generic (Heuristic)")
        return {"workflow": "basic", "document_type": "generic"}
    
    # 2. Prepare content for analysis
    content = _normalize_garbage_characters(document.page_content or "")
    snippet = content[:4000]
    
    # 3. Check Persistence Cache
    cache_key = generate_cache_key(
        content=snippet,
        extra_params={"step": "router_decision"}
    )
    
    cached = get_cached_result(cache_key)
    if cached:
        print(f"[{source}] Using cached routing decision: {cached['workflow']} / {cached['document_type']}")
        return cached
    
    # Optimization: If snippet is very short, default to basic
    if len(snippet.strip()) < 50:
         return {"workflow": "basic", "document_type": "generic"}

    # 4. Make LLM Decision
    decision = _make_llm_decision(snippet)
    
    # Save to cache
    save_to_cache(cache_key, decision)
    
    return decision
