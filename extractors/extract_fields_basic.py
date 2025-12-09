from pathlib import Path
from typing import Dict, Any, List, Optional, Type

import json
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, create_model, Field

from core_pipeline import BASE_DIR, DocumentMetadata, _normalize_garbage_characters
from utils.cache_manager import generate_cache_key, get_cached_result, save_to_cache

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

    return create_model("DynamicExtractionBasic", **fields)


from utils.prompt_generator import generate_system_prompt

def extract_fields_basic(
    document: Document,
    metadata: DocumentMetadata,
    schema_content: Dict[str, Any],
    document_type: str = "generic",
) -> Dict[str, Any]:
    """Extract structured data using the provided schema and an LLM (Basic/Text Mode).
    
    Args:
        schema_content: Direct schema definition from Supabase/templates
    """
    content = _normalize_garbage_characters(document.page_content or "")
    schema = schema_content
    
    # Check Cache
    # Hash the content + schema structure to be safe
    cache_key = generate_cache_key(
        content=content,
        extra_params={
            "step": "extract_fields_basic", 
            "schema": schema, 
            "doc_type": document_type
        }
    )
    
    cached = get_cached_result(cache_key)
    if cached:
        print(f"[{metadata.filename}] Using cached extraction result.")
        return cached

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

    # Generate dynamic system prompt based on doc type and schema
    print(f"[{metadata.filename}] Generating dynamic system prompt for type: '{document_type}'...")
    # NOTE: structure_hints removed from here to allow caching
    system_prompt = generate_system_prompt(document_type, schema)

    # Injecting structure hints into the User Prompt instead of System Prompt
    hint_text = ""
    # Check if structure_hints was passed via kwargs or we could add it to signature
    # (For now, basic workflow usually has no hints, but we support consistency)
    
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
    save_to_cache(cache_key, result)

    return result
