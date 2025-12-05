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
