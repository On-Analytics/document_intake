
import time
import shutil
from pathlib import Path
import os
import sys

# Ensure we can import from local modules
sys.path.append(os.getcwd())

from langchain_core.documents import Document
from core_pipeline import DocumentMetadata
from extractors.extract_fields_basic import extract_fields_basic
from utils.cache_manager import CACHE_DIR

def run_test():
    print("Setting up test environment...")
    
    # Setup
    documents_dir = Path("documents")
    documents_dir.mkdir(exist_ok=True)
    dummy_file = documents_dir / "test_doc.txt"
    dummy_file.write_text("The patient John Doe was treated on 2023-10-01 for a broken arm. Cost: $500.", encoding="utf-8")

    schema_path = Path("templates/test_schema.json")
    schema_path.parent.mkdir(exist_ok=True)
    schema_path.write_text('{"fields": [{"name": "patient_name", "type": "string"}, {"name": "cost", "type": "integer"}]}', encoding="utf-8")

    doc = Document(page_content=dummy_file.read_text(encoding="utf-8"), metadata={"source": "test_doc.txt"})
    meta = DocumentMetadata(
        document_number="1",
        filename="test_doc.txt",
        file_size=100,
        file_path=str(dummy_file.resolve())
    )

    # Clear cache for this specific test item if it exists (optional, but good for clean test)
    # For now we just rely on standard behavior

    print("\n--- First Run (Expect API Call) ---")
    start = time.time()
    try:
        res1 = extract_fields_basic(doc, meta, schema_path)
    except Exception as e:
        print(f"Error in first run: {e}")
        return

    end = time.time()
    duration1 = end - start
    print(f"Time: {duration1:.4f}s")
    print("Result:", res1)

    print("\n--- Second Run (Expect Cache Hit) ---")
    start = time.time()
    res2 = extract_fields_basic(doc, meta, schema_path)
    end = time.time()
    duration2 = end - start
    print(f"Time: {duration2:.4f}s")
    print("Result:", res2)

    if res1 != res2:
        print("FAILED: Results do not match.")
    elif duration2 > 1.0: # generous threshold, usually it's < 0.01s
        print(f"FAILED: Second run took {duration2}s which is too long for cache.")
    else:
        print("\nPASSED: Caching works successfully.")
        print(f"Speedup: {duration1/duration2:.1f}x")

if __name__ == "__main__":
    run_test()
