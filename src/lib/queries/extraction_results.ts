import { supabase } from '../supabase'
import { toFriendlyErrorMessage } from '../errors'

export async function getLatestBatchId(): Promise<string | undefined> {
  const { data, error } = await supabase
    .from('extraction_results')
    .select('batch_id')
    .not('batch_id', 'is', null)
    .order('created_at', { ascending: false })
    .limit(1)
    .single()

  if (error) {
    throw new Error(toFriendlyErrorMessage(error, 'Failed to load recent results.'))
  }
  return data?.batch_id as string | undefined
}

export async function getExtractionResultsByBatchId(batchId: string) {
  const { data, error } = await supabase
    .from('extraction_results')
    .select('*')
    .eq('batch_id', batchId)
    .order('created_at', { ascending: false })

  if (error) {
    throw new Error(toFriendlyErrorMessage(error, 'Failed to load extraction results.'))
  }
  return data
}

export async function getExtractionResultsForHistory(navBatchId?: string) {
  let targetBatchId = navBatchId

  if (!targetBatchId) {
    targetBatchId = await getLatestBatchId()
  }

  if (!targetBatchId) return []

  return await getExtractionResultsByBatchId(targetBatchId)
}
