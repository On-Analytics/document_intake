/*
  # Fix Security and Performance Issues

  ## Changes Made

  ### 1. Add Missing Indexes on Foreign Keys
  Indexes improve query performance when joining tables or filtering by foreign keys:
  - `documents.tenant_id` - Index for tenant-based document queries
  - `extraction_results.document_id` - Index for document-based extraction lookups
  - `extraction_results.schema_id` - Index for schema-based extraction lookups
  - `profiles.tenant_id` - Index for tenant-based profile queries
  - `schemas.tenant_id` - Index for tenant-based schema queries

  ### 2. Optimize RLS Policy Performance
  Updated all RLS policies to use `(select auth.uid())` instead of `auth.uid()`.
  This prevents re-evaluation of the auth function for each row, significantly improving query performance at scale.

  Policies optimized:
  - profiles: "Users can read own profile", "Users can update own profile"
  - tenants: "Users can view their own tenant"
  - documents: "Users can view own tenant documents", "Users can upload documents"
  - schemas: All 4 policies (view, create, update, delete)
  - extraction_results: All 2 policies (view, insert)

  ### 3. Fix Function Security
  Updated `handle_new_user()` function to use explicit search_path to prevent search path manipulation attacks.

  ### 4. Password Security Note
  IMPORTANT: Enable "Leaked Password Protection" in Supabase Dashboard:
  - Go to Authentication → Settings → Security
  - Enable "Check for leaked passwords"
  This feature checks passwords against HaveIBeenPwned.org database.
*/

-- 1. Add indexes for all foreign keys
CREATE INDEX IF NOT EXISTS idx_documents_tenant_id ON public.documents(tenant_id);
CREATE INDEX IF NOT EXISTS idx_extraction_results_document_id ON public.extraction_results(document_id);
CREATE INDEX IF NOT EXISTS idx_extraction_results_schema_id ON public.extraction_results(schema_id);
CREATE INDEX IF NOT EXISTS idx_profiles_tenant_id ON public.profiles(tenant_id);
CREATE INDEX IF NOT EXISTS idx_schemas_tenant_id ON public.schemas(tenant_id);

-- 2. Drop and recreate all RLS policies with optimized auth function calls

-- Profiles policies
DROP POLICY IF EXISTS "Users can read own profile" ON public.profiles;
CREATE POLICY "Users can read own profile"
ON public.profiles FOR SELECT
USING ( id = (select auth.uid()) );

DROP POLICY IF EXISTS "Users can update own profile" ON public.profiles;
CREATE POLICY "Users can update own profile"
ON public.profiles FOR UPDATE
USING ( id = (select auth.uid()) );

-- Tenants policies
DROP POLICY IF EXISTS "Users can view their own tenant" ON public.tenants;
CREATE POLICY "Users can view their own tenant"
ON public.tenants FOR SELECT
USING (
  id IN (
    SELECT tenant_id FROM public.profiles
    WHERE id = (select auth.uid())
  )
);

-- Documents policies
DROP POLICY IF EXISTS "Users can view own tenant documents" ON public.documents;
CREATE POLICY "Users can view own tenant documents"
ON public.documents FOR SELECT
USING (
  tenant_id IN (
    SELECT tenant_id FROM public.profiles
    WHERE id = (select auth.uid())
  )
);

DROP POLICY IF EXISTS "Users can upload documents" ON public.documents;
CREATE POLICY "Users can upload documents"
ON public.documents FOR INSERT
WITH CHECK (
  tenant_id IN (
    SELECT tenant_id FROM public.profiles
    WHERE id = (select auth.uid())
  )
);

-- Schemas policies
DROP POLICY IF EXISTS "Users can view own and public schemas" ON public.schemas;
CREATE POLICY "Users can view own and public schemas"
ON public.schemas FOR SELECT
USING (
  is_public = true
  OR
  tenant_id IN (
    SELECT tenant_id FROM public.profiles
    WHERE id = (select auth.uid())
  )
);

DROP POLICY IF EXISTS "Users can create schemas" ON public.schemas;
CREATE POLICY "Users can create schemas"
ON public.schemas FOR INSERT
WITH CHECK (
  tenant_id IN (
    SELECT tenant_id FROM public.profiles
    WHERE id = (select auth.uid())
  )
);

DROP POLICY IF EXISTS "Users can update own schemas" ON public.schemas;
CREATE POLICY "Users can update own schemas"
ON public.schemas FOR UPDATE
USING (
  tenant_id IN (
    SELECT tenant_id FROM public.profiles
    WHERE id = (select auth.uid())
  )
);

DROP POLICY IF EXISTS "Users can delete own schemas" ON public.schemas;
CREATE POLICY "Users can delete own schemas"
ON public.schemas FOR DELETE
USING (
  tenant_id IN (
    SELECT tenant_id FROM public.profiles
    WHERE id = (select auth.uid())
  )
);

-- Extraction results policies
DROP POLICY IF EXISTS "Users can view their own tenant's extraction results" ON public.extraction_results;
CREATE POLICY "Users can view their own tenant's extraction results"
ON public.extraction_results FOR SELECT
USING (
  tenant_id IN (
    SELECT tenant_id FROM public.profiles
    WHERE id = (select auth.uid())
  )
);

DROP POLICY IF EXISTS "Users can insert extraction results for their own tenant" ON public.extraction_results;
CREATE POLICY "Users can insert extraction results for their own tenant"
ON public.extraction_results FOR INSERT
WITH CHECK (
  tenant_id IN (
    SELECT tenant_id FROM public.profiles
    WHERE id = (select auth.uid())
  )
);

-- 3. Fix function security by setting explicit search_path
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger 
LANGUAGE plpgsql 
SECURITY DEFINER
SET search_path = public, auth
AS $$
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
$$;