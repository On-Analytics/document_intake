import { supabase } from '../supabase'
import { toFriendlyErrorMessage } from '../errors'

type TimeRange = 'month' | 'lifetime'

export async function getOverviewStats(timeRange: TimeRange) {
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) return null

  const { data: profile, error: profileError } = await supabase
    .from('profiles')
    .select('tenant_id')
    .eq('id', user.id)
    .single()

  if (profileError) {
    throw new Error(toFriendlyErrorMessage(profileError, 'Failed to load overview.'))
  }
  if (!profile) return null

  const periodStart = new Date()
  periodStart.setUTCDate(1)
  periodStart.setUTCHours(0, 0, 0, 0)

  const createdAtFilterIso = periodStart.toISOString()

  const extractionsQuery = supabase
    .from('extraction_results')
    .select('id, status')
    .eq('tenant_id', profile.tenant_id)

  const { data: extractions, error: extractionsError } = timeRange === 'month'
    ? await extractionsQuery.gte('created_at', createdAtFilterIso)
    : await extractionsQuery

  if (extractionsError) {
    throw new Error(toFriendlyErrorMessage(extractionsError, 'Failed to load overview.'))
  }

  const { data: schemas, error: schemasError } = await supabase
    .from('schemas')
    .select('id')
    .or(`tenant_id.eq.${profile.tenant_id},is_public.eq.true`)

  if (schemasError) {
    throw new Error(toFriendlyErrorMessage(schemasError, 'Failed to load overview.'))
  }

  const documentsCountQuery = supabase
    .from('documents')
    .select('id', { count: 'exact', head: true })
    .eq('tenant_id', profile.tenant_id)

  const { count: documentsCount, error: documentsCountError } = timeRange === 'month'
    ? await documentsCountQuery.gte('created_at', createdAtFilterIso)
    : await documentsCountQuery

  if (documentsCountError) {
    throw new Error(toFriendlyErrorMessage(documentsCountError, 'Failed to load overview.'))
  }

  const documentsPagesQuery = supabase
    .from('documents')
    .select('page_count')
    .eq('tenant_id', profile.tenant_id)

  const { data: documentPagesInRange, error: pagesError } = timeRange === 'month'
    ? await documentsPagesQuery.gte('created_at', createdAtFilterIso)
    : await documentsPagesQuery

  if (pagesError) {
    throw new Error(toFriendlyErrorMessage(pagesError, 'Failed to load overview.'))
  }

  const total = extractions?.length || 0
  const successful = extractions?.filter(e => e.status === 'completed').length || 0
  const failed = extractions?.filter(e => e.status === 'failed').length || 0
  const successRate = total > 0 ? Math.round((successful / total) * 100) : 0

  return {
    totalExtractions: total,
    totalDocuments: documentsCount || 0,
    totalPages: documentPagesInRange?.reduce((acc, d) => acc + (d.page_count || 0), 0) || 0,
    successful,
    failed,
    successRate,
    totalSchemas: schemas?.length || 0
  }
}
