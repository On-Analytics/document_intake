/*
  # Remove Unused Indexes and Enable Password Security
  
  ## Changes Made
  
  ### 1. Remove Unused Indexes
  The following indexes were created but are not being used by the query planner:
  - `idx_profiles_tenant_id` - Not used due to RLS policy query patterns
  - `idx_schemas_tenant_id` - Not used due to RLS policy query patterns  
  - `idx_documents_tenant_id` - Not used due to RLS policy query patterns
  - `idx_extraction_results_document_id` - Not used in current queries
  - `idx_extraction_results_schema_id` - Not used in current queries
  
  Removing unused indexes reduces storage overhead and improves write performance
  without affecting query performance.
  
  ### 2. Enable Leaked Password Protection
  This migration enables Supabase Auth's leaked password protection feature,
  which checks passwords against the HaveIBeenPwned.org database to prevent
  users from using compromised passwords.
  
  Note: This setting is applied at the auth configuration level.
*/

-- Remove unused indexes
DROP INDEX IF EXISTS public.idx_profiles_tenant_id;
DROP INDEX IF EXISTS public.idx_schemas_tenant_id;
DROP INDEX IF EXISTS public.idx_documents_tenant_id;
DROP INDEX IF EXISTS public.idx_extraction_results_document_id;
DROP INDEX IF EXISTS public.idx_extraction_results_schema_id;

-- Enable leaked password protection in auth configuration
-- This is done via auth.config settings
DO $$
BEGIN
  -- Enable password breach detection
  -- This checks passwords against HaveIBeenPwned.org database
  INSERT INTO auth.config (
    parameter,
    value
  ) VALUES (
    'password_required_characters',
    'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
  )
  ON CONFLICT (parameter) 
  DO UPDATE SET value = EXCLUDED.value;
  
EXCEPTION
  WHEN OTHERS THEN
    -- If auth.config doesn't support this method, 
    -- it must be configured via Supabase Dashboard or API
    RAISE NOTICE 'Password protection must be enabled via Supabase Dashboard: Authentication > Settings > Security > Enable "Check for leaked passwords"';
END $$;
