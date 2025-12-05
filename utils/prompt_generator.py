from typing import Dict, Any, Optional
import json
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

class SystemPromptOutput(BaseModel):
    system_prompt: str = Field(..., description="The generated system prompt for the extraction task.")

def generate_system_prompt(
    document_type: str, 
    schema: Dict[str, Any],
    structure_hints: Optional[Dict[str, Any]] = None
) -> str:
    """
    Generates a specialized system prompt for extracting data from a specific document type
    according to a given schema, optionally using structural hints from vision analysis.
    """
    
    # Convert schema to a string representation for the prompt
    schema_str = json.dumps(schema, indent=2)
    
    meta_system_prompt = (
        "You are an expert Prompt Engineer and Data Extraction Architect. "
        "Your task is to generate a highly optimized *System Prompt* that will guide an AI assistant "
        "to extract structured data from documents of any type. "
        "Focus on clarity, constraint-setting, and schema alignment."
    )
    
    # Build structure context from hints
    structure_context = ""
    if structure_hints and isinstance(structure_hints, dict):
        hints_list = []
        if structure_hints.get("has_tables"):
            table_cols = structure_hints.get("table_columns", [])
            col_info = f" with columns: {', '.join(table_cols[:5])}" if table_cols else ""
            hints_list.append(f"- Document contains {structure_hints.get('table_count', 1)} table(s){col_info}")
        if structure_hints.get("multi_row_entries"):
            hints_list.append("- Tables have multi-row entries that need merging")
        if structure_hints.get("has_multi_column_layout"):
            hints_list.append("- Document has multi-column layout")
        if structure_hints.get("section_count", 0) > 0:
            hints_list.append(f"- Document has {structure_hints['section_count']} sections")
        
        if hints_list:
            structure_context = "\n\nStructural hints from document analysis:\n" + "\n".join(hints_list) + "\n"
    
    user_prompt = (
        f"I need a system prompt for an AI that extracts data from a **{document_type}**.\n"
        f"The extraction must strictly follow this JSON schema:\n"
        f"```json\n{schema_str}\n```\n"
        f"Also consider the following structural hints:\n"
        f"{structure_context}\n"
        "Instructions for the generated system prompt:\n"
        "1. It must instruct the AI to act as an expert in reading this specific document type.\n"
        "2. It must emphasize extracting nested fields (lists of objects) correctly by inferring structure from descriptions.\n"
        "3. For document types with tables (invoices, receipts, bank statements, forms):\n"
        "   - The AI must handle markdown tables where data may span multiple rows\n"
        "   - The AI must carefully merge multi-row entries into single objects\n"
        "4. If structural context hints are provided above, incorporate relevant guidance into the prompt.\n"
        "5. It must enforce strict adherence to the schema keys.\n"
        "6. The output should be ONLY the system prompt text, ready to be used."
    )


    llm = ChatOpenAI(model="gpt-4o", temperature=0).with_structured_output(
        SystemPromptOutput, method="function_calling"
    )

    try:
        result = llm.invoke(
            [
                {"role": "system", "content": meta_system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            config={"run_name": "prompt_generator"},
        )
        return result.system_prompt
    except Exception as e:
        print(f"Prompt generation failed, using fallback. Error: {e}")
        # Fallback prompt
        return (
            "You are an expert information extraction assistant. "
            "Your task is to extract structured data from documents to match a specific schema exactly. "
            "Pay close attention to nested fields and ensure all available details are captured."
        )
