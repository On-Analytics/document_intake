from typing import NamedTuple, Dict


class TemplateConfig(NamedTuple):
    schema_filename: str
    document_type: str


# Built-in templates shipped with the application.
# NOTE: These IDs are the logical template IDs the frontend should send as `schema_id`.
TEMPLATES: Dict[str, TemplateConfig] = {
    "invoice": TemplateConfig(
        schema_filename="invoice_schema.json",
        document_type="invoice",
    ),
    "claim": TemplateConfig(
        schema_filename="claim_schema.json",
        document_type="claim",
    ),
    "bank_statement": TemplateConfig(
        schema_filename="bank_statement_schema.json",
        document_type="bank_statement",
    ),
    "purchase_order": TemplateConfig(
        schema_filename="purchase_order_schema.json",
        document_type="purchase_order",
    ),
    "resume": TemplateConfig(
        schema_filename="resume_schema.json",
        document_type="resume",
    ),
}
