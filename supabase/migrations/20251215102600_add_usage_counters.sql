/*
  # Add usage_counters for monthly per-user quotas

  Adds:
  - public.usage_counters table
  - RLS policies for per-user access
  - RPC function to atomically increment pages with a maximum cap
*/

CREATE TABLE IF NOT EXISTS public.usage_counters (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id uuid REFERENCES auth.users ON DELETE CASCADE NOT NULL,
  period_start date NOT NULL,
  pages_used integer DEFAULT 0 NOT NULL,
  created_at timestamptz DEFAULT timezone('utc'::text, now()) NOT NULL,
  updated_at timestamptz DEFAULT timezone('utc'::text, now()) NOT NULL,
  UNIQUE (user_id, period_start)
);

ALTER TABLE public.usage_counters ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own usage" ON public.usage_counters;
CREATE POLICY "Users can view own usage"
ON public.usage_counters FOR SELECT
USING ( user_id = (select auth.uid()) );

DROP POLICY IF EXISTS "Users can insert own usage" ON public.usage_counters;
CREATE POLICY "Users can insert own usage"
ON public.usage_counters FOR INSERT
WITH CHECK ( user_id = (select auth.uid()) );

DROP POLICY IF EXISTS "Users can update own usage" ON public.usage_counters;
CREATE POLICY "Users can update own usage"
ON public.usage_counters FOR UPDATE
USING ( user_id = (select auth.uid()) );

CREATE INDEX IF NOT EXISTS idx_usage_counters_user_period ON public.usage_counters(user_id, period_start);

CREATE OR REPLACE FUNCTION public.increment_usage_pages(
  p_user_id uuid,
  p_period_start date,
  p_pages integer,
  p_max_pages integer
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth
AS $$
DECLARE
  current_pages integer;
BEGIN
  IF p_pages IS NULL OR p_pages = 0 THEN
    RETURN true;
  END IF;

  SELECT pages_used INTO current_pages
  FROM public.usage_counters
  WHERE user_id = p_user_id AND period_start = p_period_start
  FOR UPDATE;

  IF FOUND THEN
    IF p_pages > 0 AND current_pages + p_pages > p_max_pages THEN
      RETURN false;
    END IF;

    UPDATE public.usage_counters
    SET pages_used = GREATEST(pages_used + p_pages, 0),
        updated_at = timezone('utc'::text, now())
    WHERE user_id = p_user_id AND period_start = p_period_start;

    RETURN true;
  ELSE
    IF p_pages > 0 AND p_pages > p_max_pages THEN
      RETURN false;
    END IF;

    INSERT INTO public.usage_counters (user_id, period_start, pages_used)
    VALUES (p_user_id, p_period_start, GREATEST(p_pages, 0));

    RETURN true;
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION public.increment_usage_pages(uuid, date, integer, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.increment_usage_pages(uuid, date, integer, integer) TO authenticated;
