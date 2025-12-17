-- Allow tenant members to update documents rows (needed to move status from processing -> completed/failed)
-- RLS is enabled on public.documents but the initial schema only added SELECT and INSERT policies.

DROP POLICY IF EXISTS "Users can update own tenant documents" ON public.documents;
CREATE POLICY "Users can update own tenant documents"
ON public.documents FOR UPDATE
USING (
  tenant_id IN (
    SELECT tenant_id FROM public.profiles
    WHERE id = auth.uid()
  )
)
WITH CHECK (
  tenant_id IN (
    SELECT tenant_id FROM public.profiles
    WHERE id = auth.uid()
  )
);
