import { supabase } from './supabase'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export async function uploadDocument(file: File, schemaId?: string) {
  console.log('uploadDocument called for:', file.name, 'with schema:', schemaId)
  console.log('API_URL:', API_URL)

  const { data: { session } } = await supabase.auth.getSession()

  if (!session) {
    console.error('No session found')
    throw new Error('Not authenticated')
  }

  console.log('Session found, creating FormData...')
  const formData = new FormData()
  formData.append('file', file)

  // If schema ID is provided, fetch the schema content and send it
  if (schemaId) {
    formData.append('schema_id', schemaId)

    const { data: schema, error } = await supabase
      .from('schemas')
      .select('content')
      .eq('id', schemaId)
      .single()

    if (error) {
      console.error('Error fetching schema:', error)
      throw new Error('Failed to fetch schema')
    }

    if (schema && schema.content) {
      console.log('Adding schema content to request')
      formData.append('schema_content', JSON.stringify(schema.content))
    }
  }

  console.log('Sending request to:', `${API_URL}/process`)
  
  try {
    const response = await fetch(`${API_URL}/process`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${session.access_token}`
      },
      body: formData
    })

    console.log('Response status:', response.status)

    if (!response.ok) {
      const errorText = await response.text()
      console.error('Error response:', errorText)
      try {
        const error = JSON.parse(errorText)
        throw new Error(error.detail || 'Upload failed')
      } catch {
        throw new Error(`Upload failed: ${response.status} ${response.statusText}`)
      }
    }

    const result = await response.json()
    console.log('Upload successful:', result)
    return result
  } catch (error) {
    console.error('Fetch error:', error)
    throw error
  }
}
