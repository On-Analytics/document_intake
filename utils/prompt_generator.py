from typing import Dict, Any, Optional
import json
import hashlib
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from utils.cache_manager import generate_cache_key, get_cached_result, save_to_cache

class SystemPromptOutput(BaseModel):
    system_prompt: str = Field(..., description="The generated system prompt for the extraction task.")

def generate_system_prompt(
    document_type: str, 
    schema: Dict[str, Any],
    # structure_hints removed to allow caching
) -> str:
    """
    Generates a specialized system prompt for extracting data from a specific document type
    according to a given schema.
    
    Now cached using cache_manager to avoid expensive re-generation.
    """
    
    # Compute a stable hash of the schema based on canonical JSON
    # This ensures that logically identical schemas (e.g., from templates or Supabase)
    # map to the same cache key, even if key order differs.
    schema_canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    schema_hash = hashlib.sha256(schema_canonical.encode("utf-8")).hexdigest()

    # Check Cache
    cache_key = generate_cache_key(
        content=None,
        extra_params={
            "step": "generate_system_prompt",
            "document_type": document_type,
            "schema_hash": schema_hash,
        },
    )
    
    cached = get_cached_result(cache_key)
    if cached and "system_prompt" in cached:
        print(f"[Prompt Generator] Using cached system prompt for '{document_type}'")
        return cached["system_prompt"]
    
    print(f"[Prompt Generator] Generatng NEW system prompt for '{document_type}'...")

    # Convert schema to a string representation for the prompt
    schema_str = json.dumps(schema, indent=2)
    
    meta_system_prompt = (
        "You are an expert Prompt Engineer and Data Extraction Architect. "
        "Your task is to generate a highly optimized *System Prompt* that will guide an AI assistant "
        "to extract structured data from documents of any type. "
        "Focus on clarity, constraint-setting, and schema alignment."
    )
    
    # Removed specific structure_hints logic here to make prompt generic and cacheable
    
    user_prompt = (
        f"I need a system prompt for an AI that extracts data from a **{document_type}**.\n"
        f"The extraction must strictly follow this JSON schema:\n"
        f"```json\n{schema_str}\n```\n"
        "Instructions for the generated system prompt:\n"
        "1. It must instruct the AI to act as an expert in reading this specific document type.\n"
        "2. It must emphasize extracting nested fields (lists of objects) correctly by inferring structure from descriptions.\n"
        "3. For document types with tables (invoices, receipts, bank statements, forms):\n"
        "   - The AI must handle markdown tables where data may span multiple rows\n"
        "   - The AI must carefully merge multi-row entries into single objects\n"
        "4. It must enforce strict adherence to the schema keys.\n"
        "5. The output should be ONLY the system prompt text, ready to be used."
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
        
        # Save to cache
        save_to_cache(cache_key, {"system_prompt": result.system_prompt})
        
        return result.system_prompt
    except Exception as e:
        print(f"Prompt generation failed, using fallback. Error: {e}")
        # Fallback prompt
        return (
            "You are an expert information extraction assistant. "
            "Your task is to extract structured data from documents to match a specific schema exactly. "
            "Pay close attention to nested fields and ensure all available details are captured."
        )
