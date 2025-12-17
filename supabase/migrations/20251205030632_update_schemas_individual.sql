-- 4. Create schemas table
CREATE TABLE IF NOT EXISTS public.schemas (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  tenant_id uuid REFERENCES public.tenants ON DELETE CASCADE,
  name text NOT NULL,
  description text,
  content jsonb NOT NULL,
  is_public boolean DEFAULT false,
  document_type text,
  created_at timestamptz DEFAULT timezone('utc'::text, now()) NOT NULL,
  updated_at timestamptz DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- System templates seeded from JSON schemas under document_intake/templates/*.json.
-- If you update those schema files, keep this seed data in sync.
INSERT INTO public.schemas (name, description, is_public, document_type, content)
VALUES 
(
  'Claim', 
  'Extracts claim ID, policy number, patient info, and diagnosis.', 
  true,
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
)
ON CONFLICT DO NOTHING;