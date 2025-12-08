import json
from pathlib import Path
from typing import Any, Dict, Optional

from core_pipeline import BASE_DIR


TEMPLATE_METADATA_PATH = BASE_DIR / "templates" / "template_metadata.json"


def _load_all_metadata() -> Dict[str, Dict[str, Any]]:
    if not TEMPLATE_METADATA_PATH.exists():
        return {}
    try:
        with TEMPLATE_METADATA_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
            # Expecting {template_id: {"document_type": ..., "preferred_workflow": ...}}
            if isinstance(data, dict):
                return data  # type: ignore[return-value]
            return {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_all_metadata(data: Dict[str, Dict[str, Any]]) -> None:
    TEMPLATE_METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TEMPLATE_METADATA_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_template_metadata(template_id: str) -> Optional[Dict[str, Any]]:
    """Return stored metadata for a user/cloned template, if any."""
    data = _load_all_metadata()
    return data.get(template_id)


def upsert_template_metadata(
    template_id: str,
    document_type: str,
    preferred_workflow: Optional[str] = None,
) -> None:
    """Create or update metadata for a template.

    Built-in templates already define document_type/preferred_workflow in code;
    this helper is mainly for user-created or cloned templates.
    """
    data = _load_all_metadata()
    entry: Dict[str, Any] = data.get(template_id, {})
    entry["document_type"] = document_type
    if preferred_workflow is not None:
        entry["preferred_workflow"] = preferred_workflow
    data[template_id] = entry
    _save_all_metadata(data)


def list_all_template_metadata() -> Dict[str, Dict[str, Any]]:
    """Return the full template metadata mapping.

    Useful for debugging/admin tools to see what document types/workflows have been
    learned for user/cloned templates.
    """
    return _load_all_metadata()


def clear_template_metadata() -> None:
    """Delete all stored template metadata.

    This is intended for maintenance/admin scenarios. It will remove
    templates/template_metadata.json, forcing document types to be
    re-inferred on first use for user/cloned templates.
    """
    if TEMPLATE_METADATA_PATH.exists():
        try:
            TEMPLATE_METADATA_PATH.unlink()
        except OSError:
            # Failing to delete metadata should not break the app
            pass
