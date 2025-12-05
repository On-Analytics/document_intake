import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_DB_URL
const supabaseAnonKey = import.meta.env.VITE_DB_KEY

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error('Missing database environment variables')
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey)
