import asyncio
import json
import csv
import inspect
from pathlib import Path
from typing import Any, Dict, List, Optional

from core_pipeline import (
    BASE_DIR,
    DOCUMENTS_DIR,
    DocumentMetadata,
    load_documents,
    create_document_metadata,
)
from registry import WORKFLOW_REGISTRY

OUTPUTS_DIR = BASE_DIR / "outputs"
TEMPLATES_DIR = BASE_DIR / "templates"


def _ensure_outputs_dir() -> None:
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


def _flatten_for_csv(record: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten nested structures for CSV export."""
    flat = {}
    
    # Copy top-level fields
    for key in ["document_number", "filename", "file_size", "file_path", 
                "processed_date", "document_type", "document_type_reason", "detected_type"]:
        flat[key] = record.get(key, "")
    
    # Flatten extracted data
    extracted = record.get("extracted", {})
    for key, value in extracted.items():
        if key == "structure_hints":
            continue  # Skip structure hints in CSV
        elif isinstance(value, list):
            # Convert lists to semicolon-separated strings
            if value and isinstance(value[0], dict):
                # For list of dicts (e.g., line_items), convert to JSON string
                flat[key] = json.dumps(value, ensure_ascii=False)
            else:
                # For simple lists (e.g., skills), join with semicolon
                flat[key] = "; ".join(str(v) for v in value)
        elif isinstance(value, dict):
            # For nested dicts, convert to JSON string
            flat[key] = json.dumps(value, ensure_ascii=False)
        else:
            flat[key] = value
    
    return flat


def _persist_results(records: List[Dict[str, Any]], filename: str) -> str:
    _ensure_outputs_dir()
    
    # Save JSON
    json_path = OUTPUTS_DIR / filename
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, default=str, ensure_ascii=False)
    
    # Save CSV
    csv_filename = filename.replace(".json", ".csv")
    csv_path = OUTPUTS_DIR / csv_filename
    
    if records:
        flattened_records = [_flatten_for_csv(r) for r in records]
        # Get all unique keys from all records
        all_keys = set()
        for record in flattened_records:
            all_keys.update(record.keys())
        fieldnames = sorted(all_keys)
        
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(flattened_records)
    
    print(f"Results saved to:\n  JSON: {json_path}\n  CSV: {csv_path}")
    
    return str(json_path)


def _process_single_document(
    doc: Document, 
    idx: int, 
    doc_type: str, 
    schema_path: Optional[Path]
) -> Optional[Dict[str, Any]]:
    """Process a single document and return the result record."""
    meta = create_document_metadata(doc, idx)
    
    # Determine effective doc_type and config for this document
    detected_doc_type = "generic"
    
    if doc_type == "auto":
        from router import route_document
        route_result = route_document(doc)
        effective_workflow = route_result["workflow"]
        detected_doc_type = route_result["document_type"]
        
        # Map 'basic' -> 'text' to match registry key
        if effective_workflow == "basic":
            effective_workflow = "text"
        
        print(f"[{meta.filename}] Auto-routed to: {effective_workflow} (Type: {detected_doc_type})")
    else:
        effective_workflow = doc_type

    if effective_workflow not in WORKFLOW_REGISTRY:
            print(f"Skipping {meta.filename}: Unknown workflow '{effective_workflow}'")
            return None

    config = WORKFLOW_REGISTRY[effective_workflow]
    steps = config.steps
    
    # Use provided schema path or default from registry (for the effective type)
    current_schema_path = schema_path
    if not current_schema_path:
        current_schema_path = TEMPLATES_DIR / config.default_schema_name

    record = meta.model_dump()
    record["document_type"] = effective_workflow
    record["document_type_reason"] = "auto_router" if doc_type == "auto" else "user_selected"
    record["detected_type"] = detected_doc_type

    # Run all pipeline steps and merge results
    pipeline_results: Dict[str, Any] = {}
    for step in steps:
        # Prepare kwargs
        kwargs = {
            "schema_path": current_schema_path,
            "document_type": detected_doc_type # Pass detected type to extractors
        }
        
        # Check if step accepts markdown_content
        sig = inspect.signature(step)
        if "markdown_content" in sig.parameters:
            if "markdown_content" in pipeline_results:
                kwargs["markdown_content"] = pipeline_results["markdown_content"]
        
        # Check if step accepts structure_hints
        if "structure_hints" in sig.parameters:
            if "structure_hints" in pipeline_results:
                kwargs["structure_hints"] = pipeline_results["structure_hints"]
        
        # Only pass document_type if the step accepts it
        if "document_type" not in sig.parameters:
            kwargs.pop("document_type")

        step_output = step(doc, meta, **kwargs) or {}
        pipeline_results.update(step_output)

    # Do not persist raw markdown_content in the final extracted payload
    if "markdown_content" in pipeline_results:
        pipeline_results.pop("markdown_content", None)

    if pipeline_results:
        record["extracted"] = pipeline_results

    return record


async def _process_document_safe(
    doc: Document,
    idx: int,
    doc_type: str,
    schema_path: Optional[Path],
    semaphore: asyncio.Semaphore
) -> Optional[Dict[str, Any]]:
    """Async wrapper for document processing with semaphore."""
    async with semaphore:
        # Run the synchronous processing in a separate thread
        return await asyncio.to_thread(
            _process_single_document, doc, idx, doc_type, schema_path
        )


async def run_workflow_async(
    doc_type: str,
    documents_dir: Optional[Path] = None,
    schema_path: Optional[Path] = None,
    output_filename: Optional[str] = None,
    max_concurrent: int = 5
) -> Dict[str, Any]:
    """Run the workflow asynchronously with parallel processing."""
    
    # If doc_type is NOT 'auto', validate it immediately
    if doc_type != "auto" and doc_type not in WORKFLOW_REGISTRY:
        raise ValueError(f"Unknown document type: {doc_type}")
    
    import os
    env_max = os.getenv("MAX_CONCURRENT_DOCS")
    if env_max:
        try:
            max_concurrent = int(env_max)
        except ValueError:
            pass
            
    semaphore = asyncio.Semaphore(max_concurrent)
    tasks = []
    
    # Lazy load documents and create tasks
    for idx, doc in enumerate(load_documents(documents_dir), start=1):
        task = _process_document_safe(doc, idx, doc_type, schema_path, semaphore)
        tasks.append(task)
    
    if not tasks:
        print("No documents found to process.")
        return {"final_results": [], "output_path": None}
        
    print(f"Processing {len(tasks)} documents with concurrency limit: {max_concurrent}")
    
    # Run tasks concurrently
    results = await asyncio.gather(*tasks)
    
    # Filter out None results (skipped documents)
    combined = [r for r in results if r is not None]
    
    filename = output_filename or f"{doc_type}_analysis.json"
    output_path = _persist_results(combined, filename)

    return {"final_results": combined, "output_path": output_path}


def run_workflow(
    doc_type: str,
    documents_dir: Optional[Path] = None,
    schema_path: Optional[Path] = None,
    output_filename: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the workflow synchronously (legacy wrapper)."""
    
    # If doc_type is NOT 'auto', validate it immediately
    if doc_type != "auto" and doc_type not in WORKFLOW_REGISTRY:
        raise ValueError(f"Unknown document type: {doc_type}")
        
    combined: List[Dict[str, Any]] = []

    # Lazy load documents and process one by one
    for idx, doc in enumerate(load_documents(documents_dir), start=1):
        result = _process_single_document(doc, idx, doc_type, schema_path)
        if result:
            combined.append(result)

    filename = output_filename or f"{doc_type}_analysis.json"
    output_path = _persist_results(combined, filename)

    return {"final_results": combined, "output_path": output_path}

