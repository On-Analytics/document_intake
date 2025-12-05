import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { supabase } from '../lib/supabase'
import { uploadDocument } from '../lib/api'
import Dropzone from '../components/Dropzone'
import CreateSchemaModal, { SchemaData } from '../components/CreateSchemaModal'
import { Loader2, Plus, ChevronRight, Sparkles, FileText, AlertCircle, Copy } from 'lucide-react'

export default function Dashboard() {
  const navigate = useNavigate()
  const [files, setFiles] = useState<File[]>([])
  const [selectedSchemaId, setSelectedSchemaId] = useState<string>('')
  const [status, setStatus] = useState<'idle' | 'processing'>('idle')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [processingProgress, setProcessingProgress] = useState({ current: 0, total: 0 })

  // New Template Modal State
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [modalInitialData, setModalInitialData] = useState<SchemaData | null>(null)

  // Fetch Schemas
  const { data: schemas, refetch: refetchSchemas } = useQuery({
    queryKey: ['schemas'],
    queryFn: async () => {
      // Fetch content too so we can clone it
      const { data, error } = await supabase
        .from('schemas')
        .select('id, name, is_public, description, content')
        .order('is_public', { ascending: false })
        .order('name')
      
      if (error) throw error
      return data
    }
  })

  const handleExtract = async () => {
    if (files.length === 0) return

    console.log('Starting extraction for', files.length, 'files')
    console.log('Selected schema ID:', selectedSchemaId)
    
    setStatus('processing')
    setErrorMsg(null)
    setProcessingProgress({ current: 0, total: files.length })

    try {
      // Get current user's tenant_id
      const { data: { user } } = await supabase.auth.getUser()
      if (!user) throw new Error('Not authenticated')
      
      const { data: profile } = await supabase
        .from('profiles')
        .select('tenant_id')
        .eq('id', user.id)
        .single()
      
      if (!profile) throw new Error('Profile not found')

      // Get schema name if selected
      let schemaName = null
      if (selectedSchemaId) {
        const { data: schema } = await supabase
          .from('schemas')
          .select('name')
          .eq('id', selectedSchemaId)
          .single()
        schemaName = schema?.name
      }

      // Process all files in parallel for faster results
      const uploadPromises = files.map(async (file, index) => {
        console.log(`Starting upload for file ${index + 1}/${files.length}:`, file.name)
        try {
          const data = await uploadDocument(file, selectedSchemaId || undefined)
          console.log(`Successfully processed ${file.name}:`, data)
          
          // Save metadata to database
          const { data: savedResult } = await supabase.from('extraction_results').insert({
            tenant_id: profile.tenant_id,
            filename: file.name,
            schema_id: selectedSchemaId || null,
            schema_name: schemaName,
            field_count: data.results ? Object.keys(data.results).length : 0,
            processing_duration_ms: data.operational_metadata?.processing_duration_ms || null,
            workflow: data.operational_metadata?.workflow || null,
            status: 'completed'
          }).select().single()
          
          // Store full results in localStorage with the result ID
          if (savedResult) {
            const storageKey = `extraction_result_${savedResult.id}`
            const dataToStore = {
              results: data.results,
              operational_metadata: data.operational_metadata
            }
            console.log('Saving to localStorage:', storageKey, dataToStore)
            localStorage.setItem(storageKey, JSON.stringify(dataToStore))
            console.log('Saved successfully. Verifying:', localStorage.getItem(storageKey) !== null)
          } else {
            console.error('No savedResult returned from database insert')
          }
          
          return { file: file.name, success: true, data, resultId: savedResult?.id }
        } catch (err: any) {
          console.error(`Error processing ${file.name}:`, err)
          
          // Save error metadata to database
          await supabase.from('extraction_results').insert({
            tenant_id: profile.tenant_id,
            filename: file.name,
            schema_id: selectedSchemaId || null,
            schema_name: schemaName,
            field_count: 0,
            status: 'failed',
            error_message: err.message
          })
          
          return { file: file.name, success: false, error: err.message || 'Processing failed' }
        }
      })

      // Wait for all uploads to complete
      console.log('Waiting for all uploads to complete...')
      const processedResults = await Promise.all(uploadPromises)
      console.log('All uploads completed:', processedResults)
      
      const hasError = processedResults.some(r => !r.success)
      
      if (hasError) {
        const failedFiles = processedResults.filter(r => !r.success).map(r => r.file).join(', ')
        setErrorMsg(`Failed to process: ${failedFiles}`)
        setStatus('idle')
      } else {
        // All successful - redirect to results page
        navigate('/history')
      }
    } catch (err: any) {
      console.error('Fatal error during extraction:', err)
      setStatus('idle')
      setErrorMsg(err.message || 'An unexpected error occurred')
    }
  }

  const handleReset = () => {
    setFiles([])
    setStatus('idle')
    setSelectedSchemaId('')
    setProcessingProgress({ current: 0, total: 0 })
    setErrorMsg(null)
  }

  const openCreateModal = () => {
    setModalInitialData(null)
    setIsModalOpen(true)
  }

  const openCloneModal = () => {
    const schema = schemas?.find(s => s.id === selectedSchemaId)
    if (!schema) return

    // Map the DB schema structure to the UI structure
    const initialData: SchemaData = {
      name: schema.name,
      description: schema.description || '',
      fields: schema.content.fields?.map((f: any) => ({
        name: f.name,
        type: f.type,
        description: f.description || ''
      })) || []
    }
    
    setModalInitialData(initialData)
    setIsModalOpen(true)
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6 -mt-20">
      {/* Header */}
      <div className="text-center space-y-3">
        <div className="inline-flex items-center gap-2 px-4 py-2 bg-primary/10 text-primary rounded-full text-sm font-medium">
          <Sparkles className="h-4 w-4" />
          AI-Powered Extraction
        </div>
        <h1 className="text-4xl font-bold text-gray-900">Extract Data</h1>
        <p className="text-gray-600 text-lg max-w-2xl mx-auto">Upload your documents, select a template, and let AI extract structured data in seconds.</p>
      </div>

      {/* Main Card */}
      <div className="bg-white rounded-2xl shadow-lg border border-gray-200 overflow-hidden">
        {/* Step 1: File Upload */}
        <div className="p-8 border-b border-gray-100">
          <div className="flex items-center gap-3 mb-6">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-sm font-bold text-dark shadow-sm">
              1
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Upload Document</h2>
              <p className="text-sm text-gray-500">Select a PDF or image file to process</p>
            </div>
          </div>
          <Dropzone selectedFiles={files} onFilesSelect={setFiles} />
        </div>

        {/* Step 2: Select Template */}
        {files.length > 0 && (
          <div className="p-8 border-b border-gray-100 bg-gradient-to-br from-gray-50 to-white animate-in slide-in-from-top-2">
            <div className="flex items-center gap-3 mb-6">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-sm font-bold text-dark shadow-sm">
                2
              </div>
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Choose Template</h2>
                <p className="text-sm text-gray-500">Select or create an extraction schema</p>
              </div>
            </div>
            
            <div className="flex flex-col sm:flex-row gap-4 items-stretch sm:items-end">
              <div className="flex-1">
                <label className="block text-sm font-medium text-gray-700 mb-2">Extraction Schema</label>
                <select
                  className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary focus:ring-2 focus:ring-primary/50 text-sm p-3 border transition-all"
                  value={selectedSchemaId}
                  onChange={(e) => setSelectedSchemaId(e.target.value)}
                >
                  <option value="">✨ Auto-detect (Generic)</option>
                  {schemas?.map(s => (
                    <option key={s.id} value={s.id}>
                      {s.name} {s.is_public ? '• System' : ''}
                    </option>
                  ))}
                </select>
              </div>
              
              <div className="hidden sm:flex items-center pb-3 text-gray-400 text-sm font-medium">OR</div>

              <div className="flex gap-2">
                {selectedSchemaId && (
                   <button
                    onClick={openCloneModal}
                    title="Clone & Edit Template"
                    className="flex items-center gap-2 rounded-lg bg-white px-4 py-3 text-sm font-medium text-gray-700 shadow-sm border border-gray-300 hover:bg-gray-50 hover:border-gray-400 transition-all"
                  >
                    <Copy className="h-4 w-4" />
                    Clone
                  </button>
                )}

                <button
                  onClick={openCreateModal}
                  className="flex items-center gap-2 rounded-lg bg-primary px-4 py-3 text-sm font-medium text-dark shadow-sm hover:bg-primary-600 transition-all"
                >
                  <Plus className="h-4 w-4" />
                  New Template
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Step 3: Action */}
        {files.length > 0 && (
          <div className="p-8 bg-gradient-to-br from-gray-50 to-white">
            <div className="flex justify-between items-center">
              <p className="text-sm text-gray-600">
                <FileText className="inline h-4 w-4 mr-1" />
                Ready to process: <span className="font-medium text-gray-900">{files.length} file{files.length > 1 ? 's' : ''}</span>
              </p>
              <div className="flex gap-3">
                <button
                  onClick={handleReset}
                  className="rounded-lg bg-white px-4 py-2.5 text-sm font-medium text-gray-700 shadow-sm border border-gray-300 hover:bg-gray-50 hover:border-gray-400 transition-all"
                >
                  Clear
                </button>
                <button
                  onClick={handleExtract}
                  disabled={status === 'processing'}
                  className="flex items-center gap-2 rounded-lg bg-primary px-6 py-2.5 text-sm font-semibold text-dark shadow-md hover:shadow-lg hover:bg-primary-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                >
                  {status === 'processing' ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Processing {processingProgress.current}/{processingProgress.total}...
                    </>
                  ) : (
                    <>
                      <Sparkles className="h-4 w-4" />
                      Extract Data
                      <ChevronRight className="h-4 w-4" />
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Error Message */}
      {errorMsg && status === 'idle' && (
        <div className="rounded-xl bg-red-50 p-6 flex items-start gap-4 text-red-800 border border-red-200 shadow-sm animate-in fade-in">
          <div className="p-2 bg-red-100 rounded-lg">
            <AlertCircle className="h-6 w-6 shrink-0" />
          </div>
          <div className="flex-1">
            <h3 className="font-semibold text-lg">Extraction Failed</h3>
            <p className="text-sm mt-1 text-red-700">{errorMsg}</p>
          </div>
        </div>
      )}

      {/* Create Template Modal */}
      <CreateSchemaModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSuccess={(newId) => {
          refetchSchemas()
          setSelectedSchemaId(newId)
        }}
        initialData={modalInitialData}
      />
    </div>
  )
}
