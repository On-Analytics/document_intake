-- Add batch_id to extraction_results table
ALTER TABLE public.extraction_results 
ADD COLUMN batch_id UUID;

-- Create index for faster queries on batch_id
CREATE INDEX IF NOT EXISTS idx_extraction_results_batch_id ON public.extraction_results(batch_id);
