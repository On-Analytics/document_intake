from pathlib import Path
from typing import Dict, Any, Optional

from langchain_core.documents import Document
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from core_pipeline import DocumentMetadata, _normalize_garbage_characters

class RefinedMarkdownOutput(BaseModel):
    verification_log: str = Field(..., description="Step-by-step reasoning checking the draft against source. Identify discrepancies, split rows, or hallucinations here first.")
    refined_content: str = Field(..., description="The corrected and refined markdown content.")
    changes_made: str = Field(..., description="A brief summary of the fixes applied (e.g., 'Merged split table row').")

def refine_markdown(
    document: Document,
    metadata: DocumentMetadata,
    schema_path: Optional[Path] = None,
    markdown_content: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Critique and refine the generated markdown.
    Focuses on fixing common extraction errors like split table rows.
    """
    
    # If no draft markdown exists, we can't refine it. Return empty or handle gracefully.
    if not markdown_content:
        return {}

    original_text = _normalize_garbage_characters(document.page_content or "")
    
    system_prompt = (
        "You are a strict QA editor for document digitization. "
        "Your job is to ensure the accuracy and integrity of markdown generated from PDF text. "
        "You must fix formatting errors, merge split rows, and REMOVE any hallucinations or duplicate data "
        "that cannot be verified in the source text."
    )
    
    user_prompt = (
        f"Document Filename: {metadata.filename}\n\n"
        "I have a DRAFT markdown representation of a document, but it may contain errors.\n"
        "Common errors include:\n"
        "1. **Hallucinations**: Information invented by the model that isn't in the source.\n"
        "2. **Duplication**: The same description pasted for multiple items when it only appears once in the source.\n\n"
        "3. **Typo Errors**: Typos or incorrect spellings in the source text.\n"
        "Your Task:\n"
        "1. **Analyze (Chain of Thought)**: Compare the DRAFT markdown against the ORIGINAL text line-by-line.\n"
        "   - For each table row in the draft, check if it exists in the source.\n"
        "2. **Execute Fixes**:\n"
        "   - Remove hallucinations.\n"
        "   - Fix duplications based on your analysis.\n"
        "   - Fix Typos Errors"
        "3. **Output Results**:\n"
        "   - Provide your reasoning in 'verification_log'.\n"
        "   - Return the final 'refined_content'.\n\n"
        "ORIGINAL TEXT (Source of Truth):\n"
        "-----\n"
        f"{original_text}\n"
        "-----\n\n"
        "DRAFT MARKDOWN (To be fixed):\n"
        "-----\n"
        f"{markdown_content}\n"
        "-----\n"
    )
    
    llm = ChatOpenAI(model="gpt-4o", temperature=0).with_structured_output(
        RefinedMarkdownOutput, method="function_calling"
    )
    
    # Using GPT-4o here for better reasoning capabilities on the "Critique" step
    model = llm.invoke(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        config={"run_name": "refine_markdown"},
    )
    
    # Return with the key 'markdown_content' to overwrite the previous draft
    # so the next step (extraction) uses the refined version.
    return {
        "markdown_content": model.refined_content,
        "refinement_changes": model.changes_made,
        "verification_log": model.verification_log
    }
