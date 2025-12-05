-- 1. Create a table for Tenants (Organizations)
create table public.tenants (
  id uuid default gen_random_uuid() primary key,
  name text not null,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- 2. Create a table for User Profiles (links auth.users to tenants)
create table public.profiles (
  id uuid references auth.users on delete cascade primary key,
  tenant_id uuid references public.tenants on delete cascade,
  full_name text,
  role text default 'member',
  created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- 3. Create the Documents table
-- STATELESS MODE: 
-- 1. storage_path is optional (NULL) - we don't store the file.
-- 2. metadata is for OPERATIONAL INFO ONLY (e.g. {"page_count": 5, "processing_time_ms": 1200}). 
--    Do NOT store sensitive extraction results here.
create table public.documents (
  id uuid default gen_random_uuid() primary key,
  tenant_id uuid references public.tenants on delete cascade not null,
  filename text not null,
  status text default 'pending', -- pending, processing, completed, failed
  storage_path text, -- Can be NULL if we are not storing the file
  file_size bigint,
  metadata jsonb default '{}'::jsonb, -- Operational metadata ONLY
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,
  updated_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- 4. Enable Row Level Security (RLS)
-- This is CRITICAL for multi-tenancy. It ensures users can only see their own tenant's data.

alter table public.tenants enable row level security;
alter table public.profiles enable row level security;
alter table public.documents enable row level security;

-- Policy: Users can see their own tenant
create policy "Users can view their own tenant"
on public.tenants for select
using (
  id in (
    select tenant_id from public.profiles
    where id = auth.uid()
  )
);

-- Policy: Users can see documents belonging to their tenant
create policy "Users can view own tenant documents"
on public.documents for select
using (
  tenant_id in (
    select tenant_id from public.profiles
    where id = auth.uid()
  )
);

-- Policy: Users can insert documents for their tenant
create policy "Users can upload documents"
on public.documents for insert
with check (
  tenant_id in (
    select tenant_id from public.profiles
    where id = auth.uid()
  )
);
-- NOTE: Storage Bucket creation is skipped for Stateless/Lightweight Mode.
-- If you decide to add storage later, you can just run the storage creation SQL then.

-- ----------------------------------------------------------------
-- NEW: Schemas Table (For Custom Templates)
-- Run this section if you already have the previous tables!
-- ----------------------------------------------------------------

create table public.schemas (
  id uuid default gen_random_uuid() primary key,
  tenant_id uuid references public.tenants on delete cascade, -- Nullable for system templates
  name text not null,
  description text,
  content jsonb not null, -- The actual JSON schema definition
  is_public boolean default false,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,
  updated_at timestamp with time zone default timezone('utc'::text, now()) not null
);

alter table public.schemas enable row level security;

-- Policy: Users can view their own templates OR public system templates
create policy "Users can view own and public schemas"
on public.schemas for select
using (
  is_public = true
  or
  tenant_id in (
    select tenant_id from public.profiles
    where id = auth.uid()
  )
);

-- Policy: Users can insert templates for their tenant
create policy "Users can create schemas"
on public.schemas for insert
with check (
  tenant_id in (
    select tenant_id from public.profiles
    where id = auth.uid()
  )
);

-- Policy: Users can update their own templates
create policy "Users can update own schemas"
on public.schemas for update
using (
  tenant_id in (
    select tenant_id from public.profiles
    where id = auth.uid()
  )
);

-- Policy: Users can delete their own templates
create policy "Users can delete own schemas"
on public.schemas for delete
using (
  tenant_id in (
    select tenant_id from public.profiles
    where id = auth.uid()
  )
);

-- Insert Default System Templates (Optional)
-- You can run this to populate the DB with your base templates
insert into public.schemas (name, description, is_public, content)
values 
(
  'Standard Invoice', 
  'Extracts invoice number, date, total, vendor, and line items.', 
  true,
  '{
    "fields": [
      {"name": "invoice_number", "type": "string", "description": "Unique identifier for the invoice"},
      {"name": "invoice_date", "type": "string", "description": "Date of issue"},
      {"name": "total_amount", "type": "number", "description": "Grand total including tax"},
      {"name": "vendor_name", "type": "string", "description": "Name of the seller/provider"},
      {"name": "line_items", "type": "list[object]", "description": "List of items purchased"}
    ]
  }'::jsonb
),
(
  'Insurance Claim', 
  'Extracts claim ID, policy number, patient info, and diagnosis.', 
  true,
  '{
    "fields": [
      {"name": "claim_id", "type": "string", "description": "Unique claim identifier"},
      {"name": "policy_number", "type": "string", "description": "Insurance policy number"},
      {"name": "patient_name", "type": "string", "description": "Full name of the patient"},
      {"name": "diagnosis_codes", "type": "list[string]", "description": "ICD-10 or other diagnosis codes"}
    ]
  }'::jsonb
);


-- ----------------------------------------------------------------
-- FIX: RLS Policies for Profiles & Auto-Signup Trigger
-- Run this section to fix "Could not validate credentials" errors
-- ----------------------------------------------------------------

-- 1. Allow users to read their own profile
create policy "Users can read own profile"
on public.profiles for select
using ( id = auth.uid() );

-- 2. Allow users to update their own profile
create policy "Users can update own profile"
on public.profiles for update
using ( id = auth.uid() );

-- 3. Trigger to handle New User Signup
--    Automatically creates a Tenant and a Profile for the new user.
create or replace function public.handle_new_user()
returns trigger as $$
declare
  new_tenant_id uuid;
begin
  -- 1. Create a new Tenant for this user
  insert into public.tenants (name)
  values ('My Organization')
  returning id into new_tenant_id;

  -- 2. Create the Profile linking user to the new tenant
  insert into public.profiles (id, tenant_id, full_name, role)
  values (new.id, new_tenant_id, new.raw_user_meta_data->>'full_name', 'admin');

  return new;
end;
$$ language plpgsql security definer;

-- 4. Attach the trigger to auth.users
--    (Safe to run even if trigger exists, drop first to be clean)
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();


-- ----------------------------------------------------------------
-- UPDATE: Refresh System Templates (Resume, Invoice, Claim)
-- Run this to populate the dropdown with the correct file-based templates
-- ----------------------------------------------------------------

-- 1. Clear old system templates to avoid duplicates
delete from public.schemas where is_public = true;

-- 2. Insert Templates with FULL JSON content from files
insert into public.schemas (name, description, is_public, content)
values 
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
);

-- Create extraction_results table to store metadata only (not full results)
CREATE TABLE IF NOT EXISTS public.extraction_results (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  tenant_id UUID REFERENCES public.tenants ON DELETE CASCADE NOT NULL,
  document_id UUID REFERENCES public.documents ON DELETE CASCADE,
  filename TEXT NOT NULL,
  schema_id UUID REFERENCES public.schemas ON DELETE SET NULL,
  schema_name TEXT,
  field_count INTEGER DEFAULT 0, -- Number of fields extracted
  processing_duration_ms INTEGER, -- Processing time in milliseconds
  workflow TEXT, -- Workflow used (e.g., 'basic', 'advanced')
  status TEXT DEFAULT 'completed', -- completed, failed
  error_message TEXT,
  result_storage_path TEXT, -- Path to stored result file (if we store files)
  created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Enable Row Level Security
ALTER TABLE public.extraction_results ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only see their own tenant's extraction results
CREATE POLICY "Users can view their own tenant's extraction results"
ON public.extraction_results FOR SELECT
USING (
  tenant_id IN (
    SELECT tenant_id FROM public.profiles
    WHERE id = auth.uid()
  )
);

-- Policy: Users can insert extraction results for their own tenant
CREATE POLICY "Users can insert extraction results for their own tenant"
ON public.extraction_results FOR INSERT
WITH CHECK (
  tenant_id IN (
    SELECT tenant_id FROM public.profiles
    WHERE id = auth.uid()
  )
);

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_extraction_results_tenant_id ON public.extraction_results(tenant_id);
CREATE INDEX IF NOT EXISTS idx_extraction_results_created_at ON public.extraction_results(created_at DESC);


