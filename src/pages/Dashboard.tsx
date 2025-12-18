import { useState, useEffect, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { supabase } from '../lib/supabase'
import { uploadDocumentsBatch } from '../lib/api'
import Dropzone from '../components/Dropzone'
import CreateSchemaModal, { SchemaData } from '../components/CreateSchemaModal'
import SuccessModal from '../components/SuccessModal'
import { Loader2, Plus, Sparkles, FileText, AlertCircle, Copy, Check, ChevronLeft, ChevronRight, Eye, Code } from 'lucide-react'
import * as pdfjsLib from 'pdfjs-dist'

type FileStatus = 'pending' | 'processing' | 'completed' | 'error'

interface FileProcessingStatus {
  file: File
  status: FileStatus
  error?: string
}

export default function Dashboard() {
  const [files, setFiles] = useState<File[]>([])
  const [selectedSchemaId, setSelectedSchemaId] = useState<string>('')
  const [status, setStatus] = useState<'idle' | 'processing'>('idle')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [processingProgress, setProcessingProgress] = useState({ current: 0, total: 0 })
  const [fileStatuses, setFileStatuses] = useState<FileProcessingStatus[]>([])

  const [processingElapsedSeconds, setProcessingElapsedSeconds] = useState<number>(0)

  const [isCountingPages, setIsCountingPages] = useState(false)
  const [totalSelectedPages, setTotalSelectedPages] = useState<number>(0)

  // Schema Preview State
  const [isSchemaPreviewOpen, setIsSchemaPreviewOpen] = useState(false)

  // Document Preview State
  const [isPreviewOpen, setIsPreviewOpen] = useState(false)
  const [previewIndex, setPreviewIndex] = useState(0)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [previewText, setPreviewText] = useState<string | null>(null)

  // New Template Modal State
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [modalInitialData, setModalInitialData] = useState<SchemaData | null>(null)

  // Success Modal State
  const [showSuccessModal, setShowSuccessModal] = useState(false)
  const [processedFilesCount, setProcessedFilesCount] = useState(0)
  const [processedFilesSummary, setProcessedFilesSummary] = useState<Array<{
    filename: string
    fieldCount: number
    status: 'completed' | 'failed'
  }>>([])
  const [currentBatchId, setCurrentBatchId] = useState<string | null>(null)

  // Generate preview URL when files change
  const currentFile = files[previewIndex]
  const isTxtFile = useMemo(() => {
    if (!currentFile) return false
    return currentFile.type === 'text/plain' || currentFile.name.toLowerCase().endsWith('.txt')
  }, [currentFile])

  const isBinaryPreviewable = useMemo(() => {
    if (!currentFile) return false
    const type = currentFile.type
    return type === 'application/pdf' || type.startsWith('image/')
  }, [currentFile])

  useEffect(() => {
    let cancelled = false

    setPreviewText(null)

    if (currentFile && isTxtFile) {
      currentFile
        .text()
        .then((t) => {
          if (!cancelled) setPreviewText(t)
        })
        .catch(() => {
          if (!cancelled) setPreviewText('Failed to load text preview.')
        })
    }

    if (currentFile && isBinaryPreviewable) {
      const url = URL.createObjectURL(currentFile)
      setPreviewUrl(url)
      return () => {
        cancelled = true
        URL.revokeObjectURL(url)
      }
    }

    setPreviewUrl(null)
    return () => {
      cancelled = true
    }
  }, [currentFile, isTxtFile, isBinaryPreviewable])

  // Reset preview index when files change
  useEffect(() => {
    setPreviewIndex(0)
  }, [files.length])

  useEffect(() => {
    pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
      'pdfjs-dist/build/pdf.worker.min.mjs',
      import.meta.url
    ).toString()
  }, [])

  useEffect(() => {
    if (status !== 'processing') {
      setProcessingElapsedSeconds(0)
      return
    }

    const startedAt = Date.now()
    setProcessingElapsedSeconds(0)

    const timer = window.setInterval(() => {
      setProcessingElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000))
    }, 1000)

    return () => window.clearInterval(timer)
  }, [status])

  useEffect(() => {
    let cancelled = false

    const countPdfPages = async (file: File): Promise<number> => {
      const buf = await file.arrayBuffer()
      const pdf = await pdfjsLib.getDocument({ data: new Uint8Array(buf) }).promise
      const pages = pdf.numPages
      await pdf.destroy()
      return pages
    }

    const computeTotalPages = async () => {
      if (files.length === 0) {
        setTotalSelectedPages(0)
        setIsCountingPages(false)
        return
      }

      setIsCountingPages(true)
      try {
        const counts = await Promise.all(
          files.map(async (f) => {
            const isPdf = f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf')
            if (!isPdf) return 1
            return await countPdfPages(f)
          })
        )

        if (cancelled) return
        setTotalSelectedPages(counts.reduce((a, b) => a + b, 0))
      } catch {
        if (cancelled) return
        // If counting fails (corrupted PDF, etc.), fall back to non-blocking estimate.
        setTotalSelectedPages(files.length)
      } finally {
        if (!cancelled) setIsCountingPages(false)
      }
    }

    computeTotalPages()

    return () => {
      cancelled = true
    }
  }, [files])

  const isOverPageLimit = totalSelectedPages > 20

  const extractDisableReason = useMemo(() => {
    if (status === 'processing') return 'Processing in progress.'
    if (files.length === 0) return 'Upload at least one file to extract.'
    if (!selectedSchemaId) return 'Select a template to enable extraction.'
    if (isCountingPages) return 'Counting pages… please wait.'
    if (isOverPageLimit) return 'Upload limit exceeded: max 20 pages per batch.'
    return null
  }, [status, files.length, selectedSchemaId, isCountingPages, isOverPageLimit])

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


  const handleExtract = async () => {
    if (files.length === 0) return

    if (isCountingPages) {
      setErrorMsg('Calculating page count. Please wait a moment and try again.')
      return
    }

    if (isOverPageLimit) {
      setErrorMsg('Upload limit exceeded. Max 20 pages per upload batch.')
      return
    }

    // Require a template/schema to be selected; backend no longer supports auto-schema mode
    if (!selectedSchemaId) {
      setErrorMsg('Please select a template before extracting.')
      return
    }

    setStatus('processing')
    setErrorMsg(null)
    setProcessingProgress({ current: 0, total: files.length })

    // Initialize file statuses as processing (batch sends all at once)
    const initialStatuses: FileProcessingStatus[] = files.map(file => ({
      file,
      status: 'processing' as FileStatus
    }))
    setFileStatuses(initialStatuses)

    try {
      // Use batch endpoint for parallel processing (up to 5 concurrent on backend)
      const batchResult = await uploadDocumentsBatch(files, selectedSchemaId)

      // Update file statuses based on results
      const updatedStatuses: FileProcessingStatus[] = files.map(file => {
        const successResult = batchResult.results.find(r => r.results?.source_file === file.name)
        const errorResult = batchResult.errors.find(e => e.filename === file.name)
        
        if (successResult) {
          // Store results in localStorage for History page
          const storageKey = `extraction_result_${batchResult.batch_id}_${file.name}`
          localStorage.setItem(storageKey, JSON.stringify({
            results: successResult.results,
            operational_metadata: successResult.operational_metadata
          }))
          return { file, status: 'completed' as FileStatus }
        } else if (errorResult) {
          return { file, status: 'error' as FileStatus, error: errorResult.error }
        }
        return { file, status: 'pending' as FileStatus }
      })
      setFileStatuses(updatedStatuses)
      setProcessingProgress({ current: files.length, total: files.length })

      if (batchResult.failed > 0) {
        const failedFiles = batchResult.errors.map(e => e.filename).join(', ')
        setErrorMsg(`Failed to process: ${failedFiles}`)
        setStatus('idle')
      } else {
        // All successful - prepare summary and show success modal
        const summary = batchResult.results.map(r => ({
          filename: r.results?.source_file as string || 'Unknown',
          fieldCount: r.results ? Object.keys(r.results).length : 0,
          status: 'completed' as const
        }))

        setStatus('idle')
        setProcessedFilesCount(batchResult.successful)
        setProcessedFilesSummary(summary)
        setCurrentBatchId(batchResult.batch_id)
        setShowSuccessModal(true)
        handleReset()
      }
    } catch (err: any) {
      setErrorMsg(err?.message || 'Batch processing failed')
      setStatus('idle')
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

  const selectedSchema = useMemo(() => {
    if (!schemas || !selectedSchemaId) return null
    return schemas.find(s => s.id === selectedSchemaId) ?? null
  }, [schemas, selectedSchemaId])

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
    <div className="flex flex-col min-h-screen">
      {/* Page Header */}
      <div className="px-6 lg:px-8 pt-6 pb-4">
        <h1 className="text-2xl font-bold text-dark">Extract Data</h1>
        <p className="text-sm text-gray-600 mt-1">Upload documents and let AI extract structured data automatically</p>
      </div>

      {/* Page Content */}
      <div className="flex-1 px-6 lg:px-8 pb-8">
        <div className="flex gap-6">
          {/* Left Column: Steps */}
          <div className="flex-1 max-w-2xl">
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">

              {/* Step 1: Upload Documents */}
              <div className="p-5 border-b border-gray-100">
                <div className="flex items-center gap-3 mb-4">
                  <div className="flex items-center justify-center h-7 w-7 rounded-full bg-primary text-dark text-sm font-bold">
                    1
                  </div>
                  <h2 className="text-base font-semibold text-dark">Upload Documents</h2>
                </div>
                <Dropzone selectedFiles={files} onFilesSelect={setFiles} />
              </div>

              {/* Step 2: Choose Template (Required) */}
              <div className={`p-5 border-b border-gray-100 transition-opacity ${files.length === 0 ? 'opacity-50' : 'opacity-100'}`}>
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className={`flex items-center justify-center h-7 w-7 rounded-full text-sm font-bold ${files.length > 0 ? 'bg-primary text-dark' : 'bg-gray-200 text-gray-500'}`}>
                      2
                    </div>
                    <div>
                      <h2 className="text-base font-semibold text-dark">Choose Template</h2>
                      <p className="text-xs text-gray-500">Required - select a template/schema to run extraction</p>
                    </div>
                  </div>
                  <button
                    onClick={openCreateModal}
                    disabled={files.length === 0}
                    className="flex items-center gap-1.5 text-xs font-medium text-primary hover:bg-primary/5 px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    New Template
                  </button>
                </div>

                <div className="flex flex-wrap gap-2">
                  {schemas?.map(schema => (
                    <button
                      key={schema.id}
                      onClick={() => setSelectedSchemaId(schema.id)}
                      disabled={files.length === 0}
                      className={`flex items-center gap-2 px-3 py-2 rounded-lg border transition-all disabled:cursor-not-allowed ${selectedSchemaId === schema.id
                        ? 'border-primary bg-primary/10 text-dark'
                        : 'border-gray-200 bg-white hover:border-primary/30 text-gray-700'
                        }`}
                    >
                      <FileText className={`h-4 w-4 ${selectedSchemaId === schema.id ? 'text-primary' : 'text-gray-400'}`} />
                      <span className="font-medium text-sm">{schema.name}</span>
                      {selectedSchemaId === schema.id && <Check className="h-3.5 w-3.5 text-primary" />}
                    </button>
                  ))}

                  {selectedSchemaId && (
                    <button
                      onClick={openCloneModal}
                      disabled={files.length === 0}
                      className="flex items-center gap-1.5 px-3 py-2 text-xs text-gray-500 hover:text-primary hover:bg-primary/5 rounded-lg transition-colors"
                      title="Clone selected template"
                    >
                      <Copy className="h-3.5 w-3.5" />
                      Clone
                    </button>
                  )}
                </div>

                {selectedSchemaId && selectedSchema && (
                  <div className="mt-4 rounded-xl border border-gray-200 bg-gray-50 overflow-hidden">
                    <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Code className="h-4 w-4 text-gray-400" />
                        <span className="text-sm font-semibold text-dark">Template Preview</span>
                      </div>
                      <button
                        type="button"
                        onClick={() => setIsSchemaPreviewOpen(v => !v)}
                        className="text-xs font-medium text-gray-600 hover:text-gray-900 hover:bg-white px-2.5 py-1.5 rounded-lg transition-all"
                      >
                        {isSchemaPreviewOpen ? 'Hide' : 'Show'}
                      </button>
                    </div>

                    {isSchemaPreviewOpen ? (
                      <pre className="p-4 overflow-auto max-h-[320px] text-xs font-mono text-gray-800 custom-scrollbar">
                        {JSON.stringify(selectedSchema.content, null, 2)}
                      </pre>
                    ) : null}
                  </div>
                )}
              </div>

              {/* Step 3: Extract */}
              <div className={`p-5 bg-gray-50 transition-opacity ${files.length === 0 ? 'opacity-50' : 'opacity-100'}`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`flex items-center justify-center h-7 w-7 rounded-full text-sm font-bold ${files.length > 0 ? 'bg-primary text-dark' : 'bg-gray-200 text-gray-500'}`}>
                      3
                    </div>
                    <div>
                      <h2 className="text-base font-semibold text-dark">Extract Data</h2>
                      <p className="text-xs text-gray-500">
                        {files.length === 0
                          ? 'Upload files to continue'
                          : selectedSchemaId
                            ? `${files.length} file${files.length > 1 ? 's' : ''} ready • ${schemas?.find(s => s.id === selectedSchemaId)?.name ?? 'Template selected'}`
                            : 'Select a template to continue'}
                      </p>
                      {files.length > 0 && (
                        <p className={`text-xs mt-1 ${isOverPageLimit ? 'text-red-600' : 'text-gray-500'}`}>
                          {isCountingPages
                            ? 'Counting pages...'
                            : `Total pages: ${totalSelectedPages} / 20 (non-PDF files count as 1 page)`}
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {files.length > 0 && (
                      <button
                        onClick={handleReset}
                        className="px-3 py-2 text-sm font-medium text-gray-600 hover:text-gray-800 hover:bg-gray-100 rounded-lg transition-all"
                      >
                        Clear
                      </button>
                    )}
                    <button
                      onClick={handleExtract}
                      disabled={!!extractDisableReason}
                      className="flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-dark hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                    >
                      {status === 'processing' ? (
                        <>
                          <Loader2 className="h-4 w-4 animate-spin" />
                          Processing...
                        </>
                      ) : (
                        <>
                          <Sparkles className="h-4 w-4" />
                          Extract Data
                        </>
                      )}
                    </button>
                  </div>
                </div>

                {extractDisableReason && status === 'idle' && (
                  <div className={`mt-2 text-xs ${isOverPageLimit ? 'text-red-700' : 'text-gray-600'}`}>
                    {extractDisableReason}
                  </div>
                )}

                {files.length > 0 && isOverPageLimit && status === 'idle' && (
                  <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
                    Upload limit exceeded: max 20 pages per batch. Remove some files/pages and try again.
                  </div>
                )}
              </div>
            </div>

            {/* Progress Indicator */}
            {status === 'processing' && (
              <div className="mt-4 bg-white rounded-xl border border-gray-200 overflow-hidden">
                <div className="p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Loader2 className="h-4 w-4 text-primary animate-spin" />
                      <span className="text-sm font-semibold text-dark">Processing…</span>
                    </div>
                    <span className="text-xs text-gray-500">
                      {processingElapsedSeconds}s elapsed
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-xs text-gray-600 mb-2">
                    <span>
                      {processingProgress.current}/{processingProgress.total || files.length} files
                    </span>
                    <span>
                      {fileStatuses.filter(s => s.status === 'completed').length} completed
                      {fileStatuses.some(s => s.status === 'error')
                        ? ` • ${fileStatuses.filter(s => s.status === 'error').length} failed`
                        : ''}
                    </span>
                  </div>

                  <div className="bg-gray-100 rounded-full h-2 overflow-hidden">
                    <div className="h-2 w-1/2 bg-primary/70 animate-pulse" />
                  </div>

                  <p className="mt-2 text-xs text-gray-500">
                    This can take 15–30 seconds per PDF.
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Right Column: Document Preview */}
          <div className="hidden lg:block flex-1 min-w-[500px]">
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden sticky top-6">
              <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Eye className="h-4 w-4 text-gray-400" />
                  <span className="text-sm font-medium text-dark">Document Preview</span>
                </div>

                <div className="flex items-center gap-2">
                  {files.length > 1 && isPreviewOpen && (
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => setPreviewIndex(Math.max(0, previewIndex - 1))}
                        disabled={previewIndex === 0}
                        className="p-1 rounded hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed"
                      >
                        <ChevronLeft className="h-4 w-4" />
                      </button>
                      <span className="text-xs text-gray-500 min-w-[3rem] text-center">
                        {previewIndex + 1} / {files.length}
                      </span>
                      <button
                        onClick={() => setPreviewIndex(Math.min(files.length - 1, previewIndex + 1))}
                        disabled={previewIndex === files.length - 1}
                        className="p-1 rounded hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed"
                      >
                        <ChevronRight className="h-4 w-4" />
                      </button>
                    </div>
                  )}

                  <button
                    type="button"
                    onClick={() => setIsPreviewOpen(v => !v)}
                    className="text-xs font-medium text-gray-600 hover:text-gray-900 hover:bg-gray-100 px-2.5 py-1.5 rounded-lg transition-all"
                  >
                    {isPreviewOpen ? 'Hide' : 'Show'}
                  </button>
                </div>
              </div>

              {isPreviewOpen ? (
                <div className="h-[700px] bg-gray-50 flex items-center justify-center">
                  {files.length === 0 ? (
                    <div className="text-center p-6">
                      <FileText className="h-12 w-12 text-gray-300 mx-auto mb-3" />
                      <p className="text-sm text-gray-500">Upload a document to preview</p>
                    </div>
                  ) : isTxtFile ? (
                    <div className="w-full h-full p-4">
                      <pre className="w-full h-full overflow-auto rounded-lg border border-gray-200 bg-white p-4 text-xs font-mono text-gray-800 custom-scrollbar whitespace-pre-wrap">
                        {previewText ?? 'Loading…'}
                      </pre>
                    </div>
                  ) : previewUrl ? (
                    currentFile?.type === 'application/pdf' ? (
                      <iframe
                        src={previewUrl}
                        className="w-full h-full"
                        title="PDF Preview"
                      />
                    ) : (
                      <img
                        src={previewUrl}
                        alt={currentFile?.name}
                        className="max-h-full max-w-full object-contain"
                      />
                    )
                  ) : (
                    <div className="text-center p-6">
                      <AlertCircle className="h-12 w-12 text-amber-400 mx-auto mb-3" />
                      <p className="text-sm text-gray-600">Preview not available for this file type</p>
                      <p className="text-xs text-gray-500 mt-1">Only PDF, TXT, and images can be previewed</p>
                    </div>
                  )}
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </div>

      {/* Error Message */}
      {
        errorMsg && status === 'idle' && (
          <div className="px-8 lg:px-12">
            <div className="max-w-7xl mx-auto rounded-2xl bg-red-50 p-8 flex items-start gap-4 text-red-800 border border-red-200 animate-in fade-in">
              <div className="h-12 w-12 bg-red-100 rounded-xl flex items-center justify-center flex-shrink-0">
                <AlertCircle className="h-6 w-6" />
              </div>
              <div className="flex-1">
                <h3 className="font-semibold text-lg">Extraction Failed</h3>
                <p className="text-sm mt-2 text-red-700">{errorMsg}</p>
              </div>
            </div>
          </div>
        )
      }

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
        processedFiles={processedFilesSummary}
        batchId={currentBatchId}
      />
    </div>
  )
}
