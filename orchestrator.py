from pathlib import Path
from typing import Any, Dict, List

import asyncio
from workflows import (
    TEMPLATES_DIR,
    run_workflow,
    run_workflow_async,
)
from registry import WORKFLOW_REGISTRY


def _select_schema_path(doc_type: str) -> Path:
    """Ask the user which template/schema to use for the given document type."""

    config = WORKFLOW_REGISTRY[doc_type]
    default_path = TEMPLATES_DIR / config.default_schema_name
    
    print(f"\nDefault template for '{doc_type}': {default_path}")
    print("You can press Enter to use the default, or type a different schema filename")
    print("(relative to the templates folder), e.g. 'custom_claim_schema.json'.")

    user_input = input("Schema filename (or Enter for default): ").strip()

    if not user_input:
        schema_path = default_path
    else:
        schema_path = TEMPLATES_DIR / user_input

    if not schema_path.exists():
        print(f"Schema file '{schema_path}' not found. Falling back to default: {default_path}")
        schema_path = default_path

    return schema_path


def run_orchestrator() -> Dict[str, Any]:
    print("Document Processor - Auto-Routing Mode")
    print("--------------------------------------")

    # List available schemas in templates directory
    schema_files = list(TEMPLATES_DIR.glob("*.json"))
    if not schema_files:
        print("No schema templates found in 'templates/' directory.")
        return {"final_results": [], "output_path": None}

    print("\nAvailable Schemas:")
    for i, p in enumerate(schema_files, start=1):
        print(f"  {i}) {p.name}")

    while True:
        selection = input("\nSelect a schema by number: ").strip()
        try:
            sel_idx = int(selection) - 1
            if 0 <= sel_idx < len(schema_files):
                schema_path = schema_files[sel_idx]
                break
            else:
                print("Invalid selection. Please try again.")
        except ValueError:
            print("Invalid input. Please enter a number.")
    
    print(f"Selected schema: {schema_path.name}")
    
    # Always use 'auto' doc_type as requested
    doc_type = "auto"
    
    # Run the generic workflow using the registry-based runner (Async/Parallel)
    print("Starting parallel processing...")
    state = asyncio.run(run_workflow_async(
        doc_type, 
        schema_path=schema_path, 
        output_filename="results.json",
        max_concurrent=5
    ))

    final_results = state.get("final_results", [])
    output_path = state.get("output_path")

    print(f"Processed {len(final_results)} document(s).")
    if output_path:
        print(f"Final results written to: {output_path}")

    return state


if __name__ == "__main__":
    run_orchestrator()
