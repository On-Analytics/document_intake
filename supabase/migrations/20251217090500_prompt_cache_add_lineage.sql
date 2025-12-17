ALTER TABLE public.prompt_cache
  ADD COLUMN IF NOT EXISTS tenant_id uuid REFERENCES public.tenants(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS schema_id uuid REFERENCES public.schemas(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS schema_content_hash text;

ALTER TABLE public.prompt_cache
  DROP CONSTRAINT IF EXISTS prompt_cache_cache_key_key;

CREATE INDEX IF NOT EXISTS idx_prompt_cache_cache_key ON public.prompt_cache(cache_key);

CREATE INDEX IF NOT EXISTS idx_prompt_cache_tenant_schema_hash
  ON public.prompt_cache(tenant_id, schema_id, schema_content_hash);

CREATE UNIQUE INDEX IF NOT EXISTS uq_prompt_cache_tenant_schema_hash
  ON public.prompt_cache(
    COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid),
    schema_id,
    schema_content_hash
  );
