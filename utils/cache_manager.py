
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
    """Generate a SHA256 hash key based on input parameters.
    
    Args:
        file_path: Path to the source file (uses file stats/content if robust, for now path+mtime).
        content: Direct string content to hash.
        extra_params: Additional parameters that affect the result (e.g. schema, model name).
    
    Returns:
        Hex digest string.
    """
    hasher = hashlib.sha256()
    
    if file_path:
        p = Path(file_path)
        if p.exists():
            # Use file size and mtime for speed, or read content for correctness
            # For large files, stat is better.
            stat = p.stat()
            file_meta = f"{str(p.resolve())}-{stat.st_size}-{stat.st_mtime}"
            hasher.update(file_meta.encode("utf-8"))
        else:
            hasher.update(file_path.encode("utf-8"))
            
    if content:
        hasher.update(content.encode("utf-8"))
        
    if extra_params:
        # Sort keys to ensure stability
        param_str = json.dumps(extra_params, sort_keys=True, default=str)
        hasher.update(param_str.encode("utf-8"))
        
    return hasher.hexdigest()

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
