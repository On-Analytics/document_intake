import { supabase } from './supabase'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export interface ProcessResult {
  status: string
  document_id: string
  results: Record<string, unknown>
  operational_metadata: Record<string, unknown>
  batch_id?: string
}

export interface BatchProcessResult {
  status: string
  batch_id: string
  total_files: number
  successful: number
  failed: number
  results: Array<{
    status: string
    document_id: string
    results: any
    operational_metadata: any
    batch_id: string
  }>
  errors: Array<{
    filename: string
    error: string
  }>
}

export async function uploadDocumentsBatch(
  files: File[],
  schemaId?: string
): Promise<BatchProcessResult> {
  const { data: { session } } = await supabase.auth.getSession()

  if (!session) {
    throw new Error('Not authenticated')
  }

  const formData = new FormData()

  // Append all files
  for (const file of files) {
    formData.append('files', file)
  }

  // If schema ID is provided, send it; backend will fetch the schema content and document_type.
  if (schemaId) {
    formData.append('schema_id', schemaId)
  }

  const response = await fetch(`${API_URL}/process-batch`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${session.access_token}`
    },
    body: formData
  })

  if (!response.ok) {
    const errorText = await response.text()
    try {
      const error = JSON.parse(errorText)
      throw new Error(error.detail || 'Batch upload failed')
    } catch {
      throw new Error(`Batch upload failed: ${response.status} ${response.statusText}`)
    }
  }

  return await response.json()
}

export async function deleteSchema(schemaId: string): Promise<void> {
  const { data: { session } } = await supabase.auth.getSession()

  if (!session) {
    throw new Error('Not authenticated')
  }

  const response = await fetch(`${API_URL}/schemas/${schemaId}`, {
    method: 'DELETE',
    headers: {
      'Authorization': `Bearer ${session.access_token}`
    }
  })

  if (!response.ok) {
    const errorText = await response.text()
    try {
      const error = JSON.parse(errorText)
      throw new Error(error.detail || 'Delete schema failed')
    } catch {
      throw new Error(`Delete schema failed: ${response.status} ${response.statusText}`)
    }
  }
}
