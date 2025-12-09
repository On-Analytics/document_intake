import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

# Define cache directory relative to project root or use a temp dir
# We use a hidden .cache folder in the document_intake directory
CACHE_DIR = Path(__file__).parent.parent / ".cache"

def _ensure_cache_dir():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

def generate_cache_key(
    file_path: Optional[str] = None, 
    content: Optional[str] = None, 
    extra_params: Optional[Dict[str, Any]] = None
) -> str:
    """Generate identical cache keys to prompt_generator.py's implementation"""
    components = []
    
    # File component (matches prompt_generator.py's None content handling)
    if file_path:
        p = Path(file_path)
        if p.exists():
            stat = p.stat()
            components.append(f"file:{str(p.resolve())}-{stat.st_size}-{stat.st_mtime}")
        else:
            components.append(f"file:{file_path}")
    
    # Content component (direct match)
    if content:
        components.append(f"content:{content}")
    
    # Extra params handling (must match prompt_generator.py exactly)
    if extra_params:
        if "step" in extra_params:
            components.append(f"step:{extra_params['step']}")
        if "document_type" in extra_params:
            components.append(f"doc_type:{extra_params['document_type']}")
        if "schema" in extra_params:
            schema_str = json.dumps(extra_params["schema"], sort_keys=True, separators=(",", ":"))
            components.append(f"schema_hash:{hashlib.sha256(schema_str.encode('utf-8')).hexdigest()}")
        if "hints" in extra_params:
            components.append(f"hints:{json.dumps(extra_params['hints'], sort_keys=True)}")
    
    # Final combination matches prompt_generator.py's approach
    combined = "|".join(sorted(components))
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()

def get_cached_result(key: str) -> Optional[Dict[str, Any]]:
    """Retrieve result from cache if it exists."""
    _ensure_cache_dir()
    cache_file = CACHE_DIR / f"{key}.json"
    
    if cache_file.exists():
        try:
            with cache_file.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
    return None

def save_to_cache(key: str, data: Dict[str, Any]) -> None:
    """Save result to cache."""
    _ensure_cache_dir()
    cache_file = CACHE_DIR / f"{key}.json"
    
    try:
        with cache_file.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except OSError as e:
        print(f"Warning: Failed to save to cache: {e}")
