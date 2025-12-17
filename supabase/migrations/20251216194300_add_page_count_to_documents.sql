-- Add page_count to documents table
-- Nullable so we can create the row before page count is known, then update later.
ALTER TABLE public.documents
ADD COLUMN IF NOT EXISTS page_count integer;
