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
  status: 'completed' | 'partial' | 'failed'
  batch_id: string
  total_files: number
  successful: number
  failed: number
  results: ProcessResult[]
  errors: Array<{ filename: string; error: string }>
}

export async function uploadDocument(file: File, schemaId?: string, batchId?: string) {
  const { data: { session } } = await supabase.auth.getSession()

  if (!session) {
    throw new Error('Not authenticated')
  }
  const formData = new FormData()
  formData.append('file', file)

  // Add batch_id for grouping multiple files
  if (batchId) {
    formData.append('batch_id', batchId)
  }

  // If schema ID is provided, fetch the schema content and send it
  if (schemaId) {
    formData.append('schema_id', schemaId)

    const { data: schema, error } = await supabase
      .from('schemas')
      .select('content, document_type')
      .eq('id', schemaId)
      .single()

    if (error) {
      throw new Error('Failed to fetch schema')
    }

    if (schema && schema.content) {
      formData.append('schema_content', JSON.stringify(schema.content))
    }

    if (schema && schema.document_type) {
      formData.append('document_type', schema.document_type)
    }
  }

  try {
    const response = await fetch(`${API_URL}/process`, {
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
        throw new Error(error.detail || 'Upload failed')
      } catch {
        throw new Error(`Upload failed: ${response.status} ${response.statusText}`)
      }
    }

    const result = await response.json()
    return result
  } catch (error) {
    throw error
  }
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

  // If schema ID is provided, fetch the schema content and send it
  if (schemaId) {
    formData.append('schema_id', schemaId)

    const { data: schema, error } = await supabase
      .from('schemas')
      .select('content, document_type')
      .eq('id', schemaId)
      .single()

    if (error) {
      throw new Error('Failed to fetch schema')
    }

    if (schema && schema.content) {
      formData.append('schema_content_from_request', JSON.stringify(schema.content))
    }

    if (schema && schema.document_type) {
      formData.append('document_type', schema.document_type)
    }
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
