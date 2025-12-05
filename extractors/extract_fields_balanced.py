from pathlib import Path
from typing import Dict, Any, List, Optional, Type

import os
import json
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, create_model, Field

from core_pipeline import BASE_DIR, DocumentMetadata

def _get_python_type(type_str: str) -> Type:
    """Map schema type strings to Python types."""
    type_map = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "list[string]": List[str],
        "list[object]": List[Dict[str, Any]],
        "object": Dict[str, Any],
    }
    return type_map.get(type_str.lower(), str)


def _create_dynamic_model(schema: Dict[str, Any]) -> Type[BaseModel]:
    """Create a Pydantic model dynamically from the JSON schema."""
    fields = {}
    
    for field in schema.get("fields", []):
        field_name = field.get("name")
        field_type_str = field.get("type", "string")
        description = field.get("description", "")
        is_required = field.get("required", False)
        
        python_type = _get_python_type(field_type_str)
        
        # Use Optional for all fields to allow partial extraction unless strictly required
        if not is_required:
            fields[field_name] = (Optional[python_type], Field(default=None, description=description))
        else:
            fields[field_name] = (python_type, Field(..., description=description))

    return create_model("DynamicExtractionBalanced", **fields)

def _load_schema(schema_path: Path) -> Dict[str, Any]:
    if not schema_path.exists():
        return {"fields": []}

    with schema_path.open("r", encoding="utf-8") as f:
        return json.load(f)


from utils.prompt_generator import generate_system_prompt

def extract_fields_balanced(
    document: Document,
    metadata: DocumentMetadata,
    schema_path: Path,
    markdown_content: Optional[str] = None,
    document_type: str = "generic",
    structure_hints: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Extract structured data using the provided schema and an LLM (Balanced Mode).
    
    Uses markdown_content if available (from vision step), otherwise falls back to raw text.
    """

    schema = _load_schema(schema_path)
    
    # Generate the Pydantic model dynamically based on the loaded schema
    DynamicModel = _create_dynamic_model(schema)
    fields: List[Dict[str, Any]] = schema.get("fields", [])

    # Prefer markdown content from vision step, fallback to raw text
    if markdown_content:
        content_to_use = markdown_content
        print(f"[{metadata.filename}] Extracting from Markdown content (Length: {len(content_to_use)})")
    else:
        content_to_use = document.page_content or ""
        print(f"[{metadata.filename}] Extracting from Raw Text content (Length: {len(content_to_use)})")

    field_lines = []
    for field in fields:
        field_name = field.get("name")
        field_type = field.get("type", "string")
        description = field.get("description", "")
        field_lines.append(f"- {field_name} ({field_type}): {description}")

    fields_block = "\n".join(field_lines)

    # Generate dynamic system prompt based on doc type, schema, and structure hints
    print(f"[{metadata.filename}] Generating dynamic system prompt for type: '{document_type}'...")
    system_prompt = generate_system_prompt(document_type, schema, structure_hints)

    user_prompt = (
        "Extract the following fields from the document. If a field is not present, "
        "set it to null or an empty list as appropriate. Do not invent data.\n\n"
        f"Document filename: {metadata.filename}\n\n"
        "Schema fields (name and description):\n"
        f"{fields_block}\n\n"
        "Return a single JSON object where each key is exactly one of the field "
        "names above.\n\n"
        "Document content begins below this line:\n"
        "-----\n"
        f"{content_to_use}\n"
        "-----\n"
    )

    # Using gpt-4o-mini for cost-effective extraction
    # Note: If you need higher quality for complex documents, you can override by setting
    # an environment variable: EXTRACTION_MODEL=gpt-4o
    model_name = os.getenv("EXTRACTION_MODEL", "gpt-4o-mini")
    llm = ChatOpenAI(model=model_name, temperature=0).with_structured_output(
        DynamicModel, method="function_calling"
    )
    model = llm.invoke(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        config={"run_name": "extract_fields_balanced"},
    )

    return model.model_dump()
