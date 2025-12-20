from typing import Dict, Any, List, Optional, Type
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, create_model, Field

from core_pipeline import DocumentMetadata, _normalize_garbage_characters
from utils.prompt_generator import generate_system_prompt

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
        
        if not is_required:
            fields[field_name] = (Optional[python_type], Field(default=None, description=description))
        else:
            fields[field_name] = (python_type, Field(..., description=description))

    return create_model("DynamicExtractionBasic", **fields)

def extract_fields_basic(
    document: Document,
    metadata: DocumentMetadata,
    schema_content: Dict[str, Any],  # Changed from schema_path
    document_type: str = "generic",
    system_prompt: Optional[str] = None,  # Pre-computed prompt from leader
) -> Dict[str, Any]:
    """Extract structured data using the provided schema and an LLM (Basic/Text Mode).
    
    Args:
        schema_content: Direct schema definition from Supabase/templates
        system_prompt: Optional pre-computed system prompt (for batch processing)
    """
    content = _normalize_garbage_characters(document.page_content or "")
    schema = schema_content
    
    fields_count = len(schema.get("fields", []))
    print(f"[BasicExtractor] Starting extraction with {fields_count} fields, doc_type='{document_type}'")

    # Generate the Pydantic model dynamically based on the loaded schema
    DynamicModel = _create_dynamic_model(schema)
    fields: List[Dict[str, Any]] = schema.get("fields", [])

    field_lines = []
    for field in fields:
        field_name = field.get("name")
        field_type = field.get("type", "string")
        description = field.get("description", "")
        field_lines.append(f"- {field_name} ({field_type}): {description}")

    fields_block = "\n".join(field_lines)

    # Use pre-computed prompt or generate if not provided
    if not system_prompt:
        system_prompt = generate_system_prompt(document_type, schema)

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
        f"{content}\n"
        "-----\n"
    )

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0).with_structured_output(
        DynamicModel, method="function_calling"
    )
    model = llm.invoke(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        config={"run_name": "extract_fields_basic"},
    )
    
    result = model.model_dump()

    return result
