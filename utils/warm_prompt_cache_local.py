from pathlib import Path
import json

from core_pipeline import BASE_DIR
from utils.prompt_generator import generate_system_prompt


TEMPLATES_DIR = BASE_DIR / "templates"

# Define the standard (document_type, schema filename) pairs
# Keep this in sync with your known templates.
STANDARD_TEMPLATES = [
    ("invoice", "invoice_schema.json"),
    ("claim", "claim_schema.json"),
    ("bank_statement", "bank_statement_schema.json"),
    ("purchase_order", "purchase_order_schema.json"),
    ("resume", "resume_schema.json"),
]


def _load_schema(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def warm_prompt_cache() -> None:
    """Pre-generate and cache system prompts for standard templates.

    For each (document_type, schema) pair in STANDARD_TEMPLATES, this will:
    - Load the JSON schema from BASE_DIR/templates
    - Call generate_system_prompt(document_type, schema)
    - Which will in turn write the cached prompt into .cache/
    """

    if not STANDARD_TEMPLATES:
        print("No STANDARD_TEMPLATES configured. Edit utils/warm_prompt_cache.py to add some.")
        return

    for document_type, schema_filename in STANDARD_TEMPLATES:
        schema_path = TEMPLATES_DIR / schema_filename
        if not schema_path.exists():
            print(f"[SKIP] Schema file not found for {document_type}: {schema_path}")
            continue

        print(f"[WARM] Loading schema for '{document_type}' from {schema_path}")
        schema = _load_schema(schema_path)

        print(f"[WARM] Generating system prompt for '{document_type}' (may hit LLM once)...")
        system_prompt = generate_system_prompt(document_type, schema)

        # Just to confirm something was generated; content is already persisted via cache_manager.
        print(f"[OK] Cached system prompt for '{document_type}' (length={len(system_prompt)})")


if __name__ == "__main__":
    warm_prompt_cache()
