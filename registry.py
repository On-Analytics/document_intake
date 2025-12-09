from extractors.extract_fields_basic import extract_fields_basic
from extractors.extract_fields_balanced import extract_fields_balanced
from extractors.vision_generate_markdown import vision_generate_markdown

class WorkflowConfig(NamedTuple):
    display_name: str
    steps: List[Callable[..., Dict[str, Any]]]  # Type hint remains the same
    default_schema_name: str

WORKFLOW_REGISTRY: Dict[str, WorkflowConfig] = {
    "text": WorkflowConfig(
        display_name="Text (Basic)",
        steps=[extract_fields_basic],  # Now uses updated function
        default_schema_name="claim_schema.json"
    ),
    "balanced": WorkflowConfig(
        display_name="Balanced (Vision + Text)", 
        steps=[vision_generate_markdown, extract_fields_balanced],  # Already updated
        default_schema_name="invoice_schema.json"
    ),
}