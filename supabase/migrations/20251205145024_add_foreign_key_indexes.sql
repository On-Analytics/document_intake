/*
  # Add Foreign Key Indexes for Performance Optimization

  ## Performance Improvements
  
  1. New Indexes for Foreign Keys
    - `idx_documents_tenant_id` on documents(tenant_id)
      - Improves queries filtering or joining documents by tenant
    - `idx_extraction_results_document_id` on extraction_results(document_id)
      - Speeds up lookups of extraction results for specific documents
    - `idx_extraction_results_schema_id` on extraction_results(schema_id)
      - Optimizes queries filtering results by schema
    - `idx_profiles_tenant_id` on profiles(tenant_id)
      - Enhances performance when looking up users by tenant
    - `idx_schemas_tenant_id` on schemas(tenant_id)
      - Improves queries for tenant-specific schemas
  
  ## Why These Indexes Matter
  
  Without indexes on foreign key columns, the database must perform full table scans
  when joining tables or filtering by these columns. As data grows, queries become
  progressively slower. These indexes create efficient lookup structures that allow
  the database to quickly locate related records.
  
  ## Impact
  
  - Faster page loads for dashboard views
  - Improved performance for RLS policy checks
  - Better scalability as data volume increases
  - Reduced database CPU usage for common queries
  
  Note: The idx_extraction_results_tenant_id index already exists from the initial migration.
*/

-- Add indexes for foreign keys to improve query performance
CREATE INDEX IF NOT EXISTS idx_documents_tenant_id ON public.documents(tenant_id);
CREATE INDEX IF NOT EXISTS idx_extraction_results_document_id ON public.extraction_results(document_id);
CREATE INDEX IF NOT EXISTS idx_extraction_results_schema_id ON public.extraction_results(schema_id);
CREATE INDEX IF NOT EXISTS idx_profiles_tenant_id ON public.profiles(tenant_id);
CREATE INDEX IF NOT EXISTS idx_schemas_tenant_id ON public.schemas(tenant_id);