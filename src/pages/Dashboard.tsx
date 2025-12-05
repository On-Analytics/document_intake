import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { supabase } from '../lib/supabase'
import { uploadDocument } from '../lib/api'
import Dropzone from '../components/Dropzone'
import CreateSchemaModal, { SchemaData } from '../components/CreateSchemaModal'
import SuccessModal from '../components/SuccessModal'
import { Loader2, Plus, ChevronRight, Sparkles, FileText, AlertCircle, Copy, Clock, TrendingUp, Zap, CheckCircle2, XCircle, Type, Hash, Calendar, ToggleLeft, List, Box, Check } from 'lucide-react'

type FileStatus = 'pending' | 'processing' | 'completed' | 'error'

interface FileProcessingStatus {
  file: File
  status: FileStatus
  error?: string
}

const getFieldTypeIcon = (type: string) => {
  switch (type) {
    case 'string':
      return <Type className="h-3.5 w-3.5" />
    case 'number':
      return <Hash className="h-3.5 w-3.5" />
    case 'date':
      return <Calendar className="h-3.5 w-3.5" />
    case 'boolean':
      return <ToggleLeft className="h-3.5 w-3.5" />
    case 'list[string]':
      return <List className="h-3.5 w-3.5" />
    case 'object':
      return <Box className="h-3.5 w-3.5" />
    case 'list[object]':
      return <List className="h-3.5 w-3.5" />
    default:
      return <Type className="h-3.5 w-3.5" />
  }
}

const getFieldTypeLabel = (type: string) => {
  switch (type) {
    case 'string':
      return 'Text'
    case 'number':
      return 'Number'
    case 'date':
      return 'Date'
    case 'boolean':
      return 'Yes/No'
    case 'list[string]':
      return 'List'
    case 'object':
      return 'Object'
    case 'list[object]':
      return 'List (Objects)'
    default:
      return type
  }
}

export default function Dashboard() {
  const navigate = useNavigate()
  const [files, setFiles] = useState<File[]>([])
  const [selectedSchemaId, setSelectedSchemaId] = useState<string>('')
  const [status, setStatus] = useState<'idle' | 'processing'>('idle')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [processingProgress, setProcessingProgress] = useState({ current: 0, total: 0 })
  const [fileStatuses, setFileStatuses] = useState<FileProcessingStatus[]>([])

  // New Template Modal State
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [modalInitialData, setModalInitialData] = useState<SchemaData | null>(null)

  // Success Modal State
  const [showSuccessModal, setShowSuccessModal] = useState(false)
  const [processedFilesCount, setProcessedFilesCount] = useState(0)

  // Fetch Schemas
  const { data: schemas, refetch: refetchSchemas } = useQuery({
    queryKey: ['schemas'],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('schemas')
        .select('id, name, is_public, description, content')
        .order('is_public', { ascending: false })
        .order('name')

      if (error) throw error
      return data
    }
  })

  // Fetch Recent Extractions for stats
  const { data: recentExtractions } = useQuery({
    queryKey: ['recentExtractions'],
    queryFn: async () => {
      const { data: { user } } = await supabase.auth.getUser()
      if (!user) return []

      const { data: profile } = await supabase
        .from('profiles')
        .select('tenant_id')
        .eq('id', user.id)
        .single()

      if (!profile) return []

      const { data, error } = await supabase
        .from('extraction_results')
        .select('id, filename, created_at, status, schema_name')
        .eq('tenant_id', profile.tenant_id)
        .order('created_at', { ascending: false })
        .limit(3)

      if (error) throw error
      return data || []
    }
  })

  // Calculate stats
  const totalExtractions = recentExtractions?.length || 0

  const handleExtract = async () => {
    if (files.length === 0) return

    console.log('Starting extraction for', files.length, 'files')
    console.log('Selected schema ID:', selectedSchemaId)

    setStatus('processing')
    setErrorMsg(null)
    setProcessingProgress({ current: 0, total: files.length })

    // Initialize file statuses as pending
    const initialStatuses: FileProcessingStatus[] = files.map(file => ({
      file,
      status: 'pending' as FileStatus
    }))
    setFileStatuses(initialStatuses)

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

        // Update status to processing
        setFileStatuses(prev => prev.map(fs =>
          fs.file.name === file.name ? { ...fs, status: 'processing' as FileStatus } : fs
        ))

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

          // Update status to completed
          setFileStatuses(prev => prev.map(fs =>
            fs.file.name === file.name ? { ...fs, status: 'completed' as FileStatus } : fs
          ))
          setProcessingProgress(prev => ({ ...prev, current: prev.current + 1 }))

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

          // Update status to error
          setFileStatuses(prev => prev.map(fs =>
            fs.file.name === file.name ? { ...fs, status: 'error' as FileStatus, error: err.message } : fs
          ))
          setProcessingProgress(prev => ({ ...prev, current: prev.current + 1 }))

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
        // All successful - show success modal
        setStatus('idle')
        setProcessedFilesCount(files.length)
        setShowSuccessModal(true)
        handleReset()
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
    setFileStatuses([])
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
    <div className="max-w-5xl mx-auto space-y-4 -mt-32">
      {/* Header */}
      <div className="text-center space-y-2">
        <div className="inline-flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-green-500/10 to-emerald-500/10 text-green-700 rounded-full text-sm font-medium shadow-sm">
          <Sparkles className="h-4 w-4" />
          AI-Powered Extraction
        </div>
        <h1 className="text-3xl font-bold text-gray-900">Extract Data</h1>
        <p className="text-gray-600 max-w-2xl mx-auto">Upload your documents, select a template, and let AI extract structured data in seconds.</p>
      </div>

      {/* Quick Stats - Only show if user has extractions */}
      {files.length === 0 && recentExtractions && recentExtractions.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="bg-gradient-to-br from-blue-50 to-blue-100/50 rounded-xl p-5 border border-blue-200">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-blue-500 rounded-lg">
                <FileText className="h-5 w-5 text-white" />
              </div>
              <div>
                <p className="text-2xl font-bold text-gray-900">{totalExtractions}</p>
                <p className="text-sm text-gray-600">Recent Files</p>
              </div>
            </div>
          </div>

          <div className="bg-gradient-to-br from-green-50 to-emerald-100/50 rounded-xl p-5 border border-green-200">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-green-500 rounded-lg">
                <Zap className="h-5 w-5 text-white" />
              </div>
              <div>
                <p className="text-2xl font-bold text-gray-900">{schemas?.length || 0}</p>
                <p className="text-sm text-gray-600">Templates</p>
              </div>
            </div>
          </div>

          <div className="bg-gradient-to-br from-amber-50 to-orange-100/50 rounded-xl p-5 border border-amber-200">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-amber-500 rounded-lg">
                <TrendingUp className="h-5 w-5 text-white" />
              </div>
              <div>
                <p className="text-2xl font-bold text-gray-900">100%</p>
                <p className="text-sm text-gray-600">Success Rate</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Recent Activity - Only show when no files selected */}
      {files.length === 0 && recentExtractions && recentExtractions.length > 0 && (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
              <Clock className="h-5 w-5 text-gray-500" />
              Recent Extractions
            </h3>
            <button
              onClick={() => navigate('/history')}
              className="text-sm font-medium text-green-600 hover:text-green-700 flex items-center gap-1"
            >
              View All
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
          <div className="space-y-2">
            {recentExtractions.map((extraction) => (
              <div
                key={extraction.id}
                className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-all cursor-pointer"
                onClick={() => navigate('/history')}
              >
                <div className="flex items-center gap-3">
                  <CheckCircle2 className="h-5 w-5 text-green-600" />
                  <div>
                    <p className="font-medium text-gray-900 text-sm">{extraction.filename}</p>
                    <p className="text-xs text-gray-500">
                      {extraction.schema_name || 'Auto-detected'} • {new Date(extraction.created_at).toLocaleDateString()}
                    </p>
                  </div>
                </div>
                <ChevronRight className="h-4 w-4 text-gray-400" />
              </div>
            ))}
          </div>
        </div>
      )}

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
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-sm font-bold text-dark shadow-sm">
                  2
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-gray-900">Choose Template</h2>
                  <p className="text-sm text-gray-500">Select or create an extraction schema</p>
                </div>
              </div>

              <div className="flex gap-2">
                {selectedSchemaId && (
                  <button
                    onClick={openCloneModal}
                    title="Clone & Edit Template"
                    className="flex items-center gap-2 rounded-lg bg-white px-3 py-2 text-sm font-medium text-gray-700 shadow-sm border border-gray-300 hover:bg-gray-50 hover:border-gray-400 transition-all"
                  >
                    <Copy className="h-4 w-4" />
                    Clone
                  </button>
                )}

                <button
                  onClick={openCreateModal}
                  className="flex items-center gap-2 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-dark shadow-sm hover:bg-primary-600 transition-all"
                >
                  <Plus className="h-4 w-4" />
                  New Template
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {/* Auto-detect Card */}
              <button
                onClick={() => setSelectedSchemaId('')}
                className={`relative text-left p-5 rounded-xl border-2 transition-all group hover:shadow-md ${
                  selectedSchemaId === ''
                    ? 'border-green-500 bg-gradient-to-br from-green-50 to-emerald-50 shadow-md'
                    : 'border-gray-200 bg-white hover:border-green-300'
                }`}
              >
                {selectedSchemaId === '' && (
                  <div className="absolute top-3 right-3">
                    <div className="bg-green-500 rounded-full p-1">
                      <Check className="h-3 w-3 text-white" />
                    </div>
                  </div>
                )}
                <div className="flex items-start gap-3 mb-3">
                  <div className={`p-2.5 rounded-lg transition-all ${
                    selectedSchemaId === ''
                      ? 'bg-green-500 text-white'
                      : 'bg-gradient-to-br from-green-100 to-emerald-100 text-green-600 group-hover:from-green-200 group-hover:to-emerald-200'
                  }`}>
                    <Sparkles className="h-5 w-5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-gray-900 text-sm mb-1">Auto-detect</h3>
                    <p className="text-xs text-gray-600 leading-relaxed">
                      AI automatically detects and extracts all key information
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-1.5 text-xs font-medium text-green-600">
                  <Sparkles className="h-3 w-3" />
                  Generic extraction
                </div>
              </button>

              {/* Template Cards */}
              {schemas?.map(schema => {
                const fields = schema.content?.fields || []
                const fieldCount = fields.length
                const maxPreviewFields = 4

                return (
                  <button
                    key={schema.id}
                    onClick={() => setSelectedSchemaId(schema.id)}
                    className={`relative text-left p-5 rounded-xl border-2 transition-all group hover:shadow-md ${
                      selectedSchemaId === schema.id
                        ? 'border-blue-500 bg-gradient-to-br from-blue-50 to-cyan-50 shadow-md'
                        : 'border-gray-200 bg-white hover:border-blue-300'
                    }`}
                  >
                    {selectedSchemaId === schema.id && (
                      <div className="absolute top-3 right-3">
                        <div className="bg-blue-500 rounded-full p-1">
                          <Check className="h-3 w-3 text-white" />
                        </div>
                      </div>
                    )}

                    <div className="flex items-start gap-3 mb-3">
                      <div className={`p-2.5 rounded-lg transition-all ${
                        selectedSchemaId === schema.id
                          ? 'bg-blue-500 text-white'
                          : 'bg-gradient-to-br from-blue-100 to-cyan-100 text-blue-600 group-hover:from-blue-200 group-hover:to-cyan-200'
                      }`}>
                        <FileText className="h-5 w-5" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <h3 className="font-semibold text-gray-900 text-sm mb-1 truncate pr-6">
                          {schema.name}
                        </h3>
                        {schema.description && (
                          <p className="text-xs text-gray-600 line-clamp-2 leading-relaxed">
                            {schema.description}
                          </p>
                        )}
                      </div>
                    </div>

                    {/* Field Preview */}
                    {fieldCount > 0 && (
                      <div className="space-y-1.5 mb-3">
                        {fields.slice(0, maxPreviewFields).map((field: any, idx: number) => (
                          <div
                            key={idx}
                            className="flex items-center gap-2 text-xs bg-gray-50 rounded-md px-2 py-1.5 border border-gray-100"
                          >
                            <div className="text-gray-500">
                              {getFieldTypeIcon(field.type)}
                            </div>
                            <span className="font-medium text-gray-700 truncate flex-1">
                              {field.name}
                            </span>
                            <span className="text-gray-500 text-[10px] uppercase tracking-wide">
                              {getFieldTypeLabel(field.type)}
                            </span>
                          </div>
                        ))}
                        {fieldCount > maxPreviewFields && (
                          <div className="text-xs text-gray-500 italic px-2">
                            +{fieldCount - maxPreviewFields} more field{fieldCount - maxPreviewFields > 1 ? 's' : ''}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Footer */}
                    <div className="flex items-center justify-between pt-2 border-t border-gray-100">
                      <span className="text-xs font-medium text-gray-600">
                        {fieldCount} field{fieldCount !== 1 ? 's' : ''}
                      </span>
                      {schema.is_public && (
                        <span className="text-[10px] font-medium bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full uppercase tracking-wide">
                          System
                        </span>
                      )}
                    </div>
                  </button>
                )
              })}
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

      {/* Batch Processing Progress Indicator */}
      {status === 'processing' && fileStatuses.length > 0 && (
        <div className="bg-white rounded-2xl shadow-lg border border-gray-200 overflow-hidden">
          <div className="p-6 border-b border-gray-100 bg-gradient-to-r from-green-50 to-emerald-50">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Loader2 className="h-6 w-6 text-green-600 animate-spin" />
                <div>
                  <h3 className="text-lg font-semibold text-gray-900">Processing Files</h3>
                  <p className="text-sm text-gray-600">
                    {processingProgress.current} of {processingProgress.total} completed
                  </p>
                </div>
              </div>
              <div className="text-right">
                <div className="text-2xl font-bold text-gray-900">
                  {Math.round((processingProgress.current / processingProgress.total) * 100)}%
                </div>
              </div>
            </div>
            <div className="mt-4 bg-gray-200 rounded-full h-2.5 overflow-hidden">
              <div
                className="bg-gradient-to-r from-green-500 to-emerald-500 h-2.5 rounded-full transition-all duration-500"
                style={{ width: `${(processingProgress.current / processingProgress.total) * 100}%` }}
              />
            </div>
          </div>

          <div className="p-6 space-y-3 max-h-96 overflow-y-auto">
            {fileStatuses.map((fileStatus, index) => {
              const StatusIcon = fileStatus.status === 'completed'
                ? CheckCircle2
                : fileStatus.status === 'error'
                ? XCircle
                : fileStatus.status === 'processing'
                ? Loader2
                : Clock

              const statusColor = fileStatus.status === 'completed'
                ? 'text-green-600 bg-green-50'
                : fileStatus.status === 'error'
                ? 'text-red-600 bg-red-50'
                : fileStatus.status === 'processing'
                ? 'text-blue-600 bg-blue-50'
                : 'text-gray-400 bg-gray-50'

              const statusText = fileStatus.status === 'completed'
                ? 'Completed'
                : fileStatus.status === 'error'
                ? 'Failed'
                : fileStatus.status === 'processing'
                ? 'Processing...'
                : 'Pending'

              return (
                <div
                  key={index}
                  className={`flex items-center justify-between p-4 rounded-lg border transition-all ${
                    fileStatus.status === 'error'
                      ? 'border-red-200 bg-red-50/50'
                      : 'border-gray-200 bg-gray-50'
                  }`}
                >
                  <div className="flex items-center gap-3 flex-1 min-w-0">
                    <div className={`p-2 rounded-lg ${statusColor}`}>
                      <StatusIcon className={`h-5 w-5 ${fileStatus.status === 'processing' ? 'animate-spin' : ''}`} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-gray-900 text-sm truncate">
                        {fileStatus.file.name}
                      </p>
                      {fileStatus.error && (
                        <p className="text-xs text-red-600 mt-1 truncate">
                          {fileStatus.error}
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="ml-3">
                    <span className={`text-xs font-medium px-3 py-1 rounded-full ${statusColor}`}>
                      {statusText}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

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

      {/* Success Modal */}
      <SuccessModal
        isOpen={showSuccessModal}
        onClose={() => setShowSuccessModal(false)}
        filesCount={processedFilesCount}
      />
    </div>
  )
}
