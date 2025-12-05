from pathlib import Path
from typing import Dict, Any, Optional

from langchain_core.documents import Document
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from core_pipeline import DocumentMetadata, _normalize_garbage_characters

class MarkdownOutput(BaseModel):
    markdown_content: str = Field(..., description="The human-readable markdown representation of the document.")

def generate_markdown(
    document: Document,
    metadata: DocumentMetadata,
    schema_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Generate a human-readable markdown representation of the document using text extraction.
    Faster and cheaper than Vision, but may struggle with complex layouts.
    """
    
    content = _normalize_garbage_characters(document.page_content or "")
    
    system_prompt = (
        "You are an expert document summarizer and formatter. "
        "Your goal is to convert the given document content into a clear, "
        "human-readable markdown format. Preserve the structure and key information."
    )
    
    user_prompt = (
        f"Document filename: {metadata.filename}\n\n"
        "Please convert the following document content into a well-formatted markdown document.\n"
        "Guidelines:\n"
        "1. Use appropriate headers, lists, and tables to structure the data.\n"
        "2. **Tables**: Ensure that each logical item corresponds to exactly one row in the table. "
        "Do not split a single item's description or details across multiple table rows. "
        "Merge multi-line text into a single cell/row.\n"
        "3. Preserve all key information values exactly as they appear.\n\n"
        "Document content:\n"
        "-----\n"
        f"{content}\n"
        "-----\n"
    )
    
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0).with_structured_output(
        MarkdownOutput, method="function_calling"
    )
    
    model = llm.invoke(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        config={"run_name": "generate_markdown"},
    )
    
    return model.model_dump()
