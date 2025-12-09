from pathlib import Path
from typing import Dict, Any, Optional
import os
import base64

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from core_pipeline import DocumentMetadata, _normalize_garbage_characters
from utils.image_utils import convert_pdf_to_images
from utils.cache_manager import generate_cache_key, get_cached_result, save_to_cache


class MarkdownOutput(BaseModel):
    markdown_content: str = Field(
        ..., description="The human-readable markdown representation of the document."
    )
    structure_hints: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata about document structure (tables, columns, sections, etc.)"
    )


def _analyze_markdown_structure(markdown: str) -> Dict[str, Any]:
    """Analyze markdown content and extract structural metadata hints."""
    hints = {
        "has_tables": False,
        "table_count": 0,
        "table_columns": [],
        "multi_row_entries": False,
        "has_multi_column_layout": False,
        "section_count": 0,
    }
    
    lines = markdown.split('\n')
    
    # Detect tables
    table_lines = [line for line in lines if '|' in line and line.strip().startswith('|')]
    if table_lines:
        hints["has_tables"] = True
        # Count table separators (---) as table count indicator
        hints["table_count"] = len([line for line in lines if '---' in line and '|' in line])
        
        # Extract column names from first table header
        for line in table_lines:
            if line.strip().startswith('|') and not '---' in line:
                columns = [col.strip() for col in line.split('|') if col.strip()]
                if columns and not hints["table_columns"]:
                    hints["table_columns"] = columns
                break
        
        # Detect multi-row entries (incomplete table rows)
        for i, line in enumerate(table_lines):
            if '|' in line and line.count('|') > 2:
                cells = [c.strip() for c in line.split('|')]
                # If we have many empty cells, might be multi-row
                if cells.count('') > len(cells) / 2:
                    hints["multi_row_entries"] = True
                    break
    
    # Detect sections (headers)
    hints["section_count"] = len([line for line in lines if line.strip().startswith('#')])
    
    # Detect multi-column layout (multiple top-level headers at same level)
    h2_count = len([line for line in lines if line.strip().startswith('## ')])
    if h2_count > 3:
        hints["has_multi_column_layout"] = True
    
    return hints


def vision_generate_markdown(
    document: Document,
    metadata: DocumentMetadata,
    schema_content: Dict[str, Any],  # Changed parameter
) -> Dict[str, Any]:
    """Generate markdown representation using GPT-4o Vision.
    
    Args:
        schema_content: Direct schema definition from Supabase/templates
    """
    # Rest of function remains exactly the same
    # Check cache first
    cache_key = generate_cache_key(
        file_path=str(metadata.file_path),
        extra_params={"step": "vision_generate_markdown", "model": os.getenv("VISION_MODEL", "gpt-4o-mini")}
    )
    
    cached = get_cached_result(cache_key)
    if cached:
        print(f"[{metadata.filename}] Using cached markdown result.")
        return cached

    system_prompt_text = (
        "You are an expert document summarizer and formatter. "
        "Your goal is to convert the given document content into a clear, "
        "human-readable markdown format. Preserve the structure and key information."
    )

    base_instruction = (
        f"Document filename: {metadata.filename}\n\n"
        "Please convert the following document content into a well-formatted markdown document.\n"
        "Guidelines:\n"
        "1. Use appropriate headers, lists, and tables to structure the data.\n"
        "2. **Tables**: Ensure that each logical item corresponds to exactly one row in the table. "
        "Do not split a single item's description or details across multiple table rows. "
        "Merge multi-line text into a single cell/row.\n"
        "3. **Layouts**: Be careful with multi-column layouts. Do not merge text from independent columns. "
        "Visually separate distinct sections.\n"
        "4. Preserve all key information values exactly as they appear.\n"
    )

    images = []
    # Handle PDF conversion
    if metadata.file_path and metadata.file_path.lower().endswith(".pdf"):
        images = convert_pdf_to_images(metadata.file_path)
    # Handle Image files directly
    elif metadata.file_path and metadata.file_path.lower().endswith((".png", ".jpg", ".jpeg")):
        try:
            with open(metadata.file_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                images = [encoded_string]
        except Exception as e:
            print(f"Error reading image file: {e}")
            images = []

    if images:
        # Vision Path
        print(f"Using Vision Generator for {metadata.filename} ({len(images)} pages)")
        content_parts = [
            {
                "type": "text",
                "text": base_instruction
                + "\nReview the attached document images and generate the markdown.",
            }
        ]

        for img_b64 in images:
            content_parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                }
            )

        messages = [
            SystemMessage(content=system_prompt_text),
            HumanMessage(content=content_parts),
        ]

        # Use gpt-4o-mini for Vision (cost-effective)
        # Override with VISION_MODEL=gpt-4o if needed
        model_name = os.getenv("VISION_MODEL", "gpt-4o-mini")
        llm = ChatOpenAI(model=model_name, temperature=0).with_structured_output(
            MarkdownOutput, method="function_calling"
        )
    else:
        # No images available (not a PDF or conversion failed)
        print(f"Skipping Vision Generator for {metadata.filename} (No images)")
        return {"markdown_content": "", "structure_hints": {}}

    model = llm.invoke(
        messages,
        config={"run_name": "vision_generate_markdown"},
    )

    # Analyze the generated markdown for structural hints
    markdown_content = model.markdown_content
    structure_hints = _analyze_markdown_structure(markdown_content)
    
    print(f"[{metadata.filename}] Structure hints: {structure_hints}")
    
    result = {
        "markdown_content": markdown_content,
        "structure_hints": structure_hints
    }
    
    # Save to cache
    save_to_cache(cache_key, result)

    return result
