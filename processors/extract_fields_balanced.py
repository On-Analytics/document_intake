from typing import Dict, Any, List, Optional, Type

import os
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, create_model, Field

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



def extract_fields_balanced(
    schema_content: Dict[str, Any],
    system_prompt: str,
    markdown_content: str,
    document_type: str = "generic",
    structure_hints: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Extract structured data using the provided schema and an LLM (Balanced Mode).
    
    Uses markdown_content from vision step for extraction.
    """
    
    schema = schema_content

    # Generate the Pydantic model dynamically based on the loaded schema
    fields: List[Dict[str, Any]] = schema.get("fields", [])
    
    # Early return if schema has no fields - this would produce empty results
    if not fields:
        return {}
    
    DynamicModel = _create_dynamic_model(schema)

    # Build structure hints section if available
    hints_section = ""
    if structure_hints and isinstance(structure_hints, dict):
        hints_list = []
        if structure_hints.get("has_tables"):
            table_cols = structure_hints.get("table_columns", [])
            col_info = f" with columns: {', '.join(table_cols[:5])}" if table_cols else ""
            hints_list.append(f"Document contains {structure_hints.get('table_count', 1)} table(s){col_info}")
        if structure_hints.get("multi_row_entries"):
            hints_list.append("Tables have multi-row entries that need merging")
        if structure_hints.get("has_multi_column_layout"):
            hints_list.append("Document has multi-column layout")
        if structure_hints.get("section_count", 0) > 0:
            hints_list.append(f"Document has {structure_hints['section_count']} sections")
        
        if hints_list:
            hints_section = "<structure_hints>\n" + "\n".join(hints_list) + "\n</structure_hints>\n\n"

    user_prompt = (
        "<instructions>\n"
        "Extract data from the document according to the schema. "
        "Return null for missing fields. Do not invent data.\n"
        "</instructions>\n\n"
        f"{hints_section}"
        "<document>\n"
        f"{markdown_content}\n"
        "</document>"
    )

    # Using gpt-4o for high-quality extraction
    # Note: If you need to use a different model, you can override by setting
    # an environment variable: EXTRACTION_MODEL=model_name
    model_name = os.getenv("EXTRACTION_MODEL", "gpt-4o-mini")  # gpt-4o
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
    
    result = model.model_dump()

    return result
