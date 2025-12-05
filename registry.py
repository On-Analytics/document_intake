from typing import Callable, Dict, NamedTuple, Any, Optional, List
from pathlib import Path

from extractors.extract_fields_basic import extract_fields_basic
from extractors.extract_fields_balanced import extract_fields_balanced
from extractors.vision_generate_markdown import vision_generate_markdown

class WorkflowConfig(NamedTuple):
    display_name: str
    steps: List[Callable[..., Dict[str, Any]]]
    default_schema_name: str

WORKFLOW_REGISTRY: Dict[str, WorkflowConfig] = {
    "text": WorkflowConfig(
        display_name="Text (Basic)",
        steps=[extract_fields_basic],
        default_schema_name="claim_schema.json"
    ),
    "balanced": WorkflowConfig(
        display_name="Balanced (Vision + Text)",
        steps=[vision_generate_markdown, extract_fields_balanced],
        default_schema_name="invoice_schema.json"
    ),
}
