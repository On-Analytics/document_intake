import { supabase } from '../supabase'
import { toFriendlyErrorMessage } from '../errors'

export async function getSchemas() {
  const { data, error } = await supabase
    .from('schemas')
    .select('*')
    .order('is_public', { ascending: false })
    .order('name')

  if (error) {
    throw new Error(toFriendlyErrorMessage(error, 'Failed to load templates.'))
  }
  return data
}
