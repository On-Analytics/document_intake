INSERT INTO public.schemas (name, description, is_public, tenant_id, document_type, content)
SELECT
  'Claim',
  'Extracts claim ID, policy number, patient info, and diagnosis.',
  true,
  NULL,
  'claim',
  '{
  "document_type": "claim",
  "description": "General schema for general type claimms.",
  "fields": [
    {"name": "claim_id", "type": "string", "required": false, "description": "Unique identifier of the claim if present."},
    {"name": "claimant_name", "type": "string", "required": false, "description": "Name of the person or entity submitting the claim."},
    {"name": "claimant_contact", "type": "string", "required": false, "description": "Email, phone, or address for the claimant."},
    {"name": "claim_type", "type": "string", "required": false, "description": "Type of claim (e.g., bank_dispute, insurance, chargeback)."},
    {"name": "claim_date", "type": "date", "required": false, "description": "Date the claim was created or submitted."},
    {"name": "incident_date", "type": "date", "required": false, "description": "Date of the incident or transaction being claimed."},
    {"name": "claim_reason", "type": "string", "required": false, "description": "Short description of why the claim is being raised."},
    {"name": "resolution_requested", "type": "string", "required": false, "description": "What the claimant is asking for (refund, reversal, investigation, etc.)."}
  ]
  }'::jsonb
WHERE NOT EXISTS (
  SELECT 1
  FROM public.schemas
  WHERE tenant_id IS NULL
    AND is_public = true
    AND document_type = 'claim'
    AND name = 'Claim'
);
