/*
  # Initial Database Setup for Document Extraction System

  1. New Tables
    - `tenants` - Organizations/tenants for multi-tenancy
      - `id` (uuid, primary key)
      - `name` (text)
      - `created_at` (timestamptz)
    
    - `profiles` - User profiles linked to tenants
      - `id` (uuid, primary key, references auth.users)
      - `tenant_id` (uuid, references tenants)
      - `full_name` (text)
      - `role` (text, defaults to 'member')
      - `created_at` (timestamptz)
    
    - `documents` - Document tracking
      - `id` (uuid, primary key)
      - `tenant_id` (uuid, references tenants)
      - `filename` (text)
      - `status` (text)
      - `storage_path` (text, nullable)
      - `file_size` (bigint)
      - `metadata` (jsonb)
      - `created_at`, `updated_at` (timestamptz)
    
    - `schemas` - Custom extraction templates
      - `id` (uuid, primary key)
      - `tenant_id` (uuid, references tenants, nullable for system templates)
      - `name` (text)
      - `description` (text)
      - `content` (jsonb)
      - `is_public` (boolean)
      - `created_at`, `updated_at` (timestamptz)
    
    - `extraction_results` - Extraction result metadata
      - `id` (uuid, primary key)
      - `tenant_id` (uuid, references tenants)
      - `document_id` (uuid, references documents)
      - `filename` (text)
      - `schema_id` (uuid, references schemas)
      - `schema_name` (text)
      - `field_count` (integer)
      - `processing_duration_ms` (integer)
      - `workflow` (text)
      - `status` (text)
      - `error_message` (text)
      - `result_storage_path` (text)
      - `created_at` (timestamptz)

  2. Security
    - Enable RLS on all tables
    - Add policies for tenant-based access control
    - Users can only access data from their own tenant
    - System templates are publicly accessible

  3. Automation
    - Trigger function to auto-create tenant and profile on user signup
    - Automatically links new users to their own organization

  4. Initial Data
    - Pre-populate three system templates: Resume/CV, Standard Invoice, Insurance Claim
*/

-- 1. Create tenants table
CREATE TABLE IF NOT EXISTS public.tenants (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  name text NOT NULL,
  created_at timestamptz DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 2. Create profiles table
CREATE TABLE IF NOT EXISTS public.profiles (
  id uuid REFERENCES auth.users ON DELETE CASCADE PRIMARY KEY,
  tenant_id uuid REFERENCES public.tenants ON DELETE CASCADE,
  full_name text,
  role text DEFAULT 'member',
  created_at timestamptz DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 3. Create documents table
CREATE TABLE IF NOT EXISTS public.documents (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  tenant_id uuid REFERENCES public.tenants ON DELETE CASCADE NOT NULL,
  filename text NOT NULL,
  status text DEFAULT 'pending',
  storage_path text,
  file_size bigint,
  metadata jsonb DEFAULT '{}'::jsonb,
  created_at timestamptz DEFAULT timezone('utc'::text, now()) NOT NULL,
  updated_at timestamptz DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 4. Create schemas table
CREATE TABLE IF NOT EXISTS public.schemas (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  tenant_id uuid REFERENCES public.tenants ON DELETE CASCADE,
  name text NOT NULL,
  description text,
  content jsonb NOT NULL,
  is_public boolean DEFAULT false,
  created_at timestamptz DEFAULT timezone('utc'::text, now()) NOT NULL,
  updated_at timestamptz DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 5. Create extraction_results table
CREATE TABLE IF NOT EXISTS public.extraction_results (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  tenant_id uuid REFERENCES public.tenants ON DELETE CASCADE NOT NULL,
  document_id uuid REFERENCES public.documents ON DELETE CASCADE,
  filename text NOT NULL,
  schema_id uuid REFERENCES public.schemas ON DELETE SET NULL,
  schema_name text,
  field_count integer DEFAULT 0,
  processing_duration_ms integer,
  workflow text,
  status text DEFAULT 'completed',
  error_message text,
  result_storage_path text,
  created_at timestamptz DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Enable Row Level Security
ALTER TABLE public.tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.schemas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.extraction_results ENABLE ROW LEVEL SECURITY;

-- Profiles policies
CREATE POLICY "Users can read own profile"
ON public.profiles FOR SELECT
USING ( id = auth.uid() );

CREATE POLICY "Users can update own profile"
ON public.profiles FOR UPDATE
USING ( id = auth.uid() );

-- Tenants policies
CREATE POLICY "Users can view their own tenant"
ON public.tenants FOR SELECT
USING (
  id IN (
    SELECT tenant_id FROM public.profiles
    WHERE id = auth.uid()
  )
);

-- Documents policies
CREATE POLICY "Users can view own tenant documents"
ON public.documents FOR SELECT
USING (
  tenant_id IN (
    SELECT tenant_id FROM public.profiles
    WHERE id = auth.uid()
  )
);

CREATE POLICY "Users can upload documents"
ON public.documents FOR INSERT
WITH CHECK (
  tenant_id IN (
    SELECT tenant_id FROM public.profiles
    WHERE id = auth.uid()
  )
);

-- Schemas policies
CREATE POLICY "Users can view own and public schemas"
ON public.schemas FOR SELECT
USING (
  is_public = true
  OR
  tenant_id IN (
    SELECT tenant_id FROM public.profiles
    WHERE id = auth.uid()
  )
);

CREATE POLICY "Users can create schemas"
ON public.schemas FOR INSERT
WITH CHECK (
  tenant_id IN (
    SELECT tenant_id FROM public.profiles
    WHERE id = auth.uid()
  )
);

CREATE POLICY "Users can update own schemas"
ON public.schemas FOR UPDATE
USING (
  tenant_id IN (
    SELECT tenant_id FROM public.profiles
    WHERE id = auth.uid()
  )
);

CREATE POLICY "Users can delete own schemas"
ON public.schemas FOR DELETE
USING (
  tenant_id IN (
    SELECT tenant_id FROM public.profiles
    WHERE id = auth.uid()
  )
);

-- Extraction results policies
CREATE POLICY "Users can view their own tenant's extraction results"
ON public.extraction_results FOR SELECT
USING (
  tenant_id IN (
    SELECT tenant_id FROM public.profiles
    WHERE id = auth.uid()
  )
);

CREATE POLICY "Users can insert extraction results for their own tenant"
ON public.extraction_results FOR INSERT
WITH CHECK (
  tenant_id IN (
    SELECT tenant_id FROM public.profiles
    WHERE id = auth.uid()
  )
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_extraction_results_tenant_id ON public.extraction_results(tenant_id);
CREATE INDEX IF NOT EXISTS idx_extraction_results_created_at ON public.extraction_results(created_at DESC);

-- Auto-signup trigger function
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger AS $$
DECLARE
  new_tenant_id uuid;
BEGIN
  -- Create a new Tenant for this user
  INSERT INTO public.tenants (name)
  VALUES ('My Organization')
  RETURNING id INTO new_tenant_id;

  -- Create the Profile linking user to the new tenant
  INSERT INTO public.profiles (id, tenant_id, full_name, role)
  VALUES (new.id, new_tenant_id, new.raw_user_meta_data->>'full_name', 'admin');

  RETURN new;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Attach the trigger
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE PROCEDURE public.handle_new_user();

-- Insert system templates
INSERT INTO public.schemas (name, description, is_public, content)
VALUES 
(
  'Resume / CV', 
  'Extracts candidate info, experience, education, and skills.', 
  true,
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
  '{
  "document_type": "invoice",
  "description": "General schema for B2B/B2C invoices.",
  "fields": [
    {"name": "invoice_number", "type": "string", "required": false, "description": "Invoice identifier."},
    {"name": "invoice_date", "type": "date", "required": false, "description": "Date issued."},
    {"name": "due_date", "type": "date", "required": false, "description": "Payment due date."},
    {"name": "seller_name", "type": "string", "required": false, "description": "Vendor name."},
    {"name": "seller_address", "type": "string", "required": false, "description": "Vendor address."},
    {"name": "buyer_name", "type": "string", "required": false, "description": "Customer name."},
    {"name": "buyer_address", "type": "string", "required": false, "description": "Customer address."},
    {"name": "line_items", "type": "list[object]", "required": false, "description": "Products/Services list."},
    {"name": "subtotal", "type": "number", "required": false, "description": "Subtotal before tax."},
    {"name": "tax_amount", "type": "number", "required": false, "description": "Total tax."},
    {"name": "total_amount", "type": "number", "required": false, "description": "Grand total."},
    {"name": "currency", "type": "string", "required": false, "description": "Currency code (USD, EUR)."}
  ]
  }'::jsonb
),
(
  'Insurance Claim', 
  'Extracts claim ID, policy number, patient info, and diagnosis.', 
  true,
  '{
  "document_type": "claim",
  "description": "General schema for financial or insurance claims.",
  "fields": [
    {"name": "claim_id", "type": "string", "required": false, "description": "Unique claim identifier."},
    {"name": "claimant_name", "type": "string", "required": false, "description": "Name of claimant."},
    {"name": "claim_type", "type": "string", "required": false, "description": "Type of claim."},
    {"name": "claim_date", "type": "date", "required": false, "description": "Date submitted."},
    {"name": "amount_claimed", "type": "number", "required": false, "description": "Total amount claimed."},
    {"name": "policy_number", "type": "string", "required": false, "description": "Policy/Account number."},
    {"name": "diagnosis_codes", "type": "list[string]", "required": false, "description": "ICD-10 or diagnosis codes."},
    {"name": "claim_reason", "type": "string", "required": false, "description": "Reason for claim."},
    {"name": "claim_details", "type": "string", "required": false, "description": "Narrative description."}
  ]
  }'::jsonb
)
ON CONFLICT DO NOTHING;