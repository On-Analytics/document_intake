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
  'Resume / CV', 
  'Extracts candidate info, experience, education, and skills.', 
  true,
  'resume',
  '{
  "document_type": "resume",
  "description": "General schema for CV / resume documents.",
  "fields": [
    {"name": "candidate_name", "type": "string", "required": false, "description": "Full name of the candidate."},
    {"name": "contact_email", "type": "string", "required": false, "description": "Candidate email address."},
    {"name": "contact_phone", "type": "string", "required": false, "description": "Candidate phone number."},
    {"name": "location", "type": "string", "required": false, "description": "City, region, or country."},
    {"name": "headline", "type": "string", "required": false, "description": "Short title or headline."},
    {"name": "summary", "type": "string", "required": false, "description": "Professional summary or objective section."},
    {"name": "skills", "type": "list[string]", "required": false, "description": "List of key skills or technologies."},
    {"name": "work_experience", "type": "list[object]", "required": false, "description": "List of jobs/roles (employer, title, dates)."},
    {"name": "education", "type": "list[object]", "required": false, "description": "List of educational records."},
    {"name": "certifications", "type": "list[string]", "required": false, "description": "Relevant certifications."},
    {"name": "languages", "type": "list[string]", "required": false, "description": "Languages spoken."},
    {"name": "projects", "type": "list[object]", "required": false, "description": "Key projects or portfolio items."},
    {"name": "links", "type": "list[string]", "required": false, "description": "URLs (LinkedIn, GitHub, etc)."}
  ]
  }'::jsonb
),
(
  'Standard Invoice', 
  'Extracts invoice number, date, total, vendor, and line items.', 
  true,
  'invoice',
  '{
  "document_type": "invoice",
  "description": "General schema for B2B/B2C invoices.",
  "fields": [
    {"name": "invoice_number", "type": "string", "required": false, "description": "Invoice identifier or reference number."},
    {"name": "invoice_date", "type": "date", "required": false, "description": "Date the invoice was issued."},
    {"name": "due_date", "type": "date", "required": false, "description": "Payment due date if present."},
    {"name": "seller_name", "type": "string", "required": false, "description": "Name of the seller/vendor/issuer."},
    {"name": "seller_address", "type": "string", "required": false, "description": "Address or contact details of the seller."},
    {"name": "buyer_name", "type": "string", "required": false, "description": "Name of the buyer/customer."},
    {"name": "buyer_address", "type": "string", "required": false, "description": "Address or contact details of the buyer."},
    {"name": "line_items", "type": "list[object]", "required": false, "description": "List of line items (products or services). Each item may include description, quantity, unit_price, tax, line_total."},
    {"name": "subtotal", "type": "number", "required": false, "description": "Subtotal amount before tax and discounts."},
    {"name": "tax_amount", "type": "number", "required": false, "description": "Total tax amount on the invoice."},
    {"name": "discount_amount", "type": "number", "required": false, "description": "Total discount amount if present."},
    {"name": "total_amount", "type": "number", "required": false, "description": "Grand total amount to be paid."},
    {"name": "currency", "type": "string", "required": false, "description": "Currency code for monetary amounts (e.g., USD, EUR)."},
    {"name": "payment_terms", "type": "string", "required": false, "description": "Payment terms such as Net 30, immediate, partial payments, etc."},
    {"name": "payment_instructions", "type": "string", "required": false, "description": "Bank details, payment links, or instructions for how to pay."}
  ]
  }'::jsonb
),
(
  'Bank Statement', 
  'Extracts balances, statement period, and transactions from bank statements.', 
  true,
  'bank_statement',
  '{
  "document_type": "bank_statement",
  "description": "General schema for bank account statements.",
  "fields": [
    {"name": "account_holder", "type": "string", "required": false, "description": "Name of the account holder."},
    {"name": "account_number", "type": "string", "required": false, "description": "Bank account number or masked identifier."},
    {"name": "bank_name", "type": "string", "required": false, "description": "Name of the bank or financial institution."},
    {"name": "statement_period_start", "type": "date", "required": false, "description": "Start date of the statement period."},
    {"name": "statement_period_end", "type": "date", "required": false, "description": "End date of the statement period."},
    {"name": "opening_balance", "type": "number", "required": false, "description": "Balance at the beginning of the statement period."},
    {"name": "closing_balance", "type": "number", "required": false, "description": "Balance at the end of the statement period."},
    {"name": "currency", "type": "string", "required": false, "description": "Currency code for monetary amounts (e.g., USD, EUR)."},
    {"name": "transactions", "type": "list[object]", "required": false, "description": "List of transactions. Each may include date, description, amount, balance_after, transaction_type (debit/credit)."}
  ]
  }'::jsonb
),
(
  'Purchase Order', 
  'Extracts key information from purchase orders, including parties and line items.', 
  true,
  'purchase_order',
  '{
  "document_type": "purchase_order",
  "description": "General schema for purchase order documents.",
  "fields": [
    {"name": "po_number", "type": "string", "required": false, "description": "Purchase order identifier or reference number."},
    {"name": "po_date", "type": "date", "required": false, "description": "Date the purchase order was issued."},
    {"name": "buyer_name", "type": "string", "required": false, "description": "Name of the buyer or purchasing organization."},
    {"name": "buyer_address", "type": "string", "required": false, "description": "Address or contact details of the buyer if present."},
    {"name": "seller_name", "type": "string", "required": false, "description": "Name of the supplier or vendor."},
    {"name": "seller_address", "type": "string", "required": false, "description": "Address or contact details of the supplier if present."},
    {"name": "line_items", "type": "list[object]", "required": false, "description": "List of ordered items. Each may include description, quantity, unit_price, tax, line_total."},
    {"name": "subtotal", "type": "number", "required": false, "description": "Subtotal amount before tax and discounts."},
    {"name": "tax_amount", "type": "number", "required": false, "description": "Total tax amount for the order if present."},
    {"name": "discount_amount", "type": "number", "required": false, "description": "Total discount amount if present."},
    {"name": "total_amount", "type": "number", "required": false, "description": "Total amount of the purchase order."},
    {"name": "currency", "type": "string", "required": false, "description": "Currency code for monetary amounts (e.g., USD, EUR)."}
  ]
  }'::jsonb
),
(
  'Insurance Claim', 
  'Extracts claim ID, policy number, patient info, and diagnosis.', 
  true,
  'claim',
  '{
  "document_type": "claim",
  "description": "General schema for financial or insurance claims.",
  "fields": [
    {"name": "claim_id", "type": "string", "required": false, "description": "Unique identifier of the claim if present."},
    {"name": "claimant_name", "type": "string", "required": false, "description": "Name of the person or entity submitting the claim."},
    {"name": "claimant_contact", "type": "string", "required": false, "description": "Email, phone, or address for the claimant."},
    {"name": "claim_type", "type": "string", "required": false, "description": "Type of claim (e.g., bank_dispute, insurance, chargeback)."},
    {"name": "claim_date", "type": "date", "required": false, "description": "Date the claim was created or submitted."},
    {"name": "incident_date", "type": "date", "required": false, "description": "Date of the incident or transaction being claimed."},
    {"name": "account_identifier", "type": "string", "required": false, "description": "Account number, policy number, or reference identifier."},
    {"name": "amount_claimed", "type": "number", "required": false, "description": "Total monetary amount being claimed."},
    {"name": "currency", "type": "string", "required": false, "description": "Currency code for the claimed amount (e.g., USD, EUR)."},
    {"name": "counterparty", "type": "string", "required": false, "description": "Merchant, bank, or other party involved in the claim."},
    {"name": "claim_reason", "type": "string", "required": false, "description": "Short description of why the claim is being raised."},
    {"name": "claim_details", "type": "string", "required": false, "description": "Free-form narrative describing the situation in detail."},
    {"name": "supporting_documents", "type": "list[string]", "required": false, "description": "List of referenced attachments or evidence if explicitly mentioned."},
    {"name": "resolution_requested", "type": "string", "required": false, "description": "What the claimant is asking for (refund, reversal, investigation, etc.)."}
  ]
  }'::jsonb
)
ON CONFLICT DO NOTHING;