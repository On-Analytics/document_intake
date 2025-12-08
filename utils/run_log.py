import json
from pathlib import Path
from typing import Optional

from core_pipeline import BASE_DIR
from utils.cache_manager import generate_cache_key


LOGS_DIR = BASE_DIR / "outputs" / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
RUN_LOG_PATH = LOGS_DIR / "runs.jsonl"


def log_run(
    content: str,
    document_type: str,
    schema_id: Optional[str],
    workflow: str,
    filename: str,
) -> None:
    """Append a single run record to a JSONL log file.

    This is a lightweight observability helper and does not affect core behavior.
    """

    try:
        content_hash = generate_cache_key(
            content=content,
            extra_params={"step": "run_log"},
        )

        record = {
            "content_hash": content_hash,
            "document_type": document_type,
            "schema_id": schema_id,
            "workflow": workflow,
            "filename": filename,
        }

        with RUN_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        # Logging should never break main processing flow
        return
