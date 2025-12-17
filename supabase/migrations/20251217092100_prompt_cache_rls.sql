ALTER TABLE public.prompt_cache ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own and system prompt cache" ON public.prompt_cache;
CREATE POLICY "Users can view own and system prompt cache"
ON public.prompt_cache FOR SELECT
USING (
  tenant_id IS NULL
  OR
  tenant_id IN (
    SELECT tenant_id FROM public.profiles
    WHERE id = auth.uid()
  )
);

DROP POLICY IF EXISTS "Users can insert own prompt cache" ON public.prompt_cache;
CREATE POLICY "Users can insert own prompt cache"
ON public.prompt_cache FOR INSERT
WITH CHECK (
  (
    tenant_id IS NULL
    AND schema_id IN (
      SELECT id FROM public.schemas
      WHERE is_public = true AND tenant_id IS NULL
    )
  )
  OR
  (
    tenant_id IN (
      SELECT tenant_id FROM public.profiles
      WHERE id = auth.uid()
    )
  )
);
