import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useLocation } from 'react-router-dom'
import { supabase } from '../lib/supabase'
import { FileText, Calendar, Clock, CheckCircle, AlertCircle, Code, ChevronDown, ChevronRight, FileJson, FileSpreadsheet } from 'lucide-react'

interface ExtractionResult {
  id: string
  document_id: string
  filename: string
  schema_name: string
  field_count: number
  processing_duration_ms: number
  workflow: string
  status: string
  error_message: string
  created_at: string
  batch_id?: string
}

interface StoredResult {
  results: Record<string, any>
  operational_metadata: any
}

export default function History() {
  const [expandedResults, setExpandedResults] = useState<Set<string>>(new Set())
  const [loadedResults, setLoadedResults] = useState<Map<string, StoredResult>>(new Map())
  const location = useLocation()
  const navBatchId = location.state?.batchId as string | undefined

  // Fetch extraction results
  const { data: results, isLoading } = useQuery({
    queryKey: ['extraction-results', navBatchId], // Add navBatchId to key to re-fetch on change
    queryFn: async () => {
      let targetBatchId = navBatchId

      // If no ID passed from navigation, find the latest one
      if (!targetBatchId) {
        // 1. Get the latest batch_id
        const { data: latest } = await supabase
          .from('extraction_results')
          .select('batch_id')
          .not('batch_id', 'is', null) // Filter out legacy records without batch_id
          .order('created_at', { ascending: false })
          .limit(1)
          .single()

        targetBatchId = latest?.batch_id
      }

      if (!targetBatchId) {
        // Fallback: If no batched results exist, return empty
        return []
      }

      // 2. Fetch results for that batch
      const { data, error } = await supabase
        .from('extraction_results')
        .select('*')
        .eq('batch_id', targetBatchId)
        .order('created_at', { ascending: false })

      if (error) throw error
      return data as ExtractionResult[]
    }
  })

  const toggleExpanded = (id: string) => {
    const newExpanded = new Set(expandedResults)
    if (newExpanded.has(id)) {
      newExpanded.delete(id)
    } else {
      newExpanded.add(id)
    }
    setExpandedResults(newExpanded)
  }

  // Load results from localStorage when results are fetched
  useEffect(() => {
    if (results && results.length > 0) {
      const newLoadedResults = new Map<string, StoredResult>()

      results.forEach(result => {
        // Use batch_id + filename as key (matches Dashboard storage)
        const storageKey = `extraction_result_${result.batch_id}_${result.filename}`
        const stored = localStorage.getItem(storageKey)
        if (stored) {
          try {
            const parsed = JSON.parse(stored)
            newLoadedResults.set(result.id, parsed)
          } catch {
            // Ignore malformed localStorage entries
          }
        }
      })

      setLoadedResults(newLoadedResults)
    }
  }, [results])

  const downloadAllJSON = () => {
    if (!results || results.length === 0) {
      alert('No results to download')
      return
    }

    const allResults = results
      .filter(r => r.status === 'completed' && loadedResults.has(r.id))
      .map(r => ({
        filename: r.filename,
        schema_name: r.schema_name,
        processing_duration_ms: r.processing_duration_ms,
        workflow: r.workflow,
        created_at: r.created_at,
        extracted_data: loadedResults.get(r.id)?.results
      }))

    if (allResults.length === 0) {
      alert('No completed results available to download')
      return
    }

    const dataStr = JSON.stringify(allResults, null, 2)
    const dataBlob = new Blob([dataStr], { type: 'application/json' })
    const url = URL.createObjectURL(dataBlob)
    const link = document.createElement('a')
    link.href = url
    link.download = `all_extraction_results_${new Date().toISOString().split('T')[0]}.json`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  const downloadSingleCSV = (result: ExtractionResult) => {
    const stored = loadedResults.get(result.id)
    if (!stored?.results) {
      alert('Result is not loaded yet')
      return
    }

    const baseFields = {
      filename: result.filename,
      schema_name: result.schema_name || '',
      processing_duration_ms: result.processing_duration_ms || '',
      workflow: result.workflow || '',
      created_at: result.created_at
    }

    const resultFields = stored.results || {}
    const allFieldNames = new Set<string>([...Object.keys(baseFields), ...Object.keys(resultFields)])
    const headers = Array.from(allFieldNames)

    const row: any = { ...baseFields }
    Object.entries(resultFields).forEach(([key, value]) => {
      row[key] = typeof value === 'object' ? JSON.stringify(value) : String(value)
    })

    const csvRow = headers.map(h => {
      const value = row[h] ?? ''
      return `"${String(value).replace(/"/g, '""')}"`
    }).join(',')

    const csvContent = [headers.join(','), csvRow].join('\n')

    const dataBlob = new Blob([csvContent], { type: 'text/csv' })
    const url = URL.createObjectURL(dataBlob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${result.filename.replace(/\.[^/.]+$/, '')}_extraction.csv`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  const downloadSingleJSON = (result: ExtractionResult) => {
    const stored = loadedResults.get(result.id)
    if (!stored) {
      alert('Result is not loaded yet')
      return
    }

    const single = {
      filename: result.filename,
      schema_name: result.schema_name,
      processing_duration_ms: result.processing_duration_ms,
      workflow: result.workflow,
      created_at: result.created_at,
      extracted_data: stored.results
    }

    const dataStr = JSON.stringify(single, null, 2)
    const dataBlob = new Blob([dataStr], { type: 'application/json' })
    const url = URL.createObjectURL(dataBlob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${result.filename.replace(/\.[^/.]+$/, '')}_extraction.json`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  const downloadAllCSV = () => {
    if (!results || results.length === 0) {
      alert('No results to download')
      return
    }

    const completedResults = results.filter(r => r.status === 'completed' && loadedResults.has(r.id))

    if (completedResults.length === 0) {
      alert('No completed results available to download')
      return
    }

    // Collect all unique field names across all results
    const allFieldNames = new Set<string>(['filename', 'schema_name', 'processing_duration_ms', 'workflow', 'created_at'])
    completedResults.forEach(r => {
      const stored = loadedResults.get(r.id)
      if (stored?.results) {
        Object.keys(stored.results).forEach(key => allFieldNames.add(key))
      }
    })

    const headers = Array.from(allFieldNames)

    // Create rows
    const rows = completedResults.map(r => {
      const stored = loadedResults.get(r.id)
      const row: any = {
        filename: r.filename,
        schema_name: r.schema_name || '',
        processing_duration_ms: r.processing_duration_ms || '',
        workflow: r.workflow || '',
        created_at: r.created_at
      }

      if (stored?.results) {
        Object.entries(stored.results).forEach(([key, value]) => {
          row[key] = typeof value === 'object' ? JSON.stringify(value) : String(value)
        })
      }

      return headers.map(h => {
        const value = row[h] || ''
        return `"${String(value).replace(/"/g, '""')}"`
      }).join(',')
    })

    const csvContent = [headers.join(','), ...rows].join('\n')

    const dataBlob = new Blob([csvContent], { type: 'text/csv' })
    const url = URL.createObjectURL(dataBlob)
    const link = document.createElement('a')
    link.href = url
    link.download = `all_extraction_results_${new Date().toISOString().split('T')[0]}.csv`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  const formatDate = (dateString: string) => {
    const date = new Date(dateString)
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    )
  }

  return (
    <div className="flex flex-col min-h-screen">
      {/* Page Header */}
      <div className="px-6 lg:px-8 pt-6 pb-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-dark">Results</h1>
            <p className="text-sm text-gray-600 mt-1">View and download your extraction results</p>
          </div>
          {results && results.length > 0 && (
            <div className="flex items-center gap-2">
              <button
                onClick={downloadAllJSON}
                className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-dark bg-primary hover:bg-primary/90 rounded-lg transition-all"
              >
                <FileJson className="h-4 w-4" />
                JSON
              </button>
              <button
                onClick={downloadAllCSV}
                className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-white bg-green-600 hover:bg-green-700 rounded-lg transition-all"
              >
                <FileSpreadsheet className="h-4 w-4" />
                CSV
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Page Content */}
      <div className="flex-1 px-6 lg:px-8 pb-8">
        <div className="max-w-7xl mx-auto space-y-4">

          {/* Results List */}
          {results && results.length > 0 ? (
            <div className="space-y-8">
              {results.map((result) => {
                const isExpanded = expandedResults.has(result.id)
                const isSuccess = result.status === 'completed'
                const canDownloadSingle = isSuccess && loadedResults.has(result.id)

                return (
                  <div
                    key={result.id}
                    className="bg-white rounded-2xl border border-gray-200 hover:border-gray-300 transition-all overflow-hidden"
                  >
                    {/* Header */}
                    <div
                      className={`p-8 cursor-pointer ${isSuccess
                        ? 'bg-green-50/50 border-b border-gray-200'
                        : 'bg-red-50/50 border-b border-gray-200'
                        }`}
                      onClick={() => toggleExpanded(result.id)}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-5 flex-1">
                          <div className={`h-12 w-12 rounded-xl flex items-center justify-center ${isSuccess ? 'bg-green-100' : 'bg-red-100'
                            }`}>
                            {isSuccess ? (
                              <CheckCircle className="h-6 w-6 text-green-600" />
                            ) : (
                              <AlertCircle className="h-6 w-6 text-red-600" />
                            )}
                          </div>

                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-3 mb-2">
                              <h3 className="text-lg font-semibold text-dark truncate">
                                {result.filename}
                              </h3>
                              {result.schema_name && (
                                <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-primary/10 text-primary">
                                  {result.schema_name}
                                </span>
                              )}
                            </div>

                            <div className="flex items-center gap-4 text-sm text-gray-600">
                              <span className="flex items-center gap-1">
                                <Calendar className="h-3.5 w-3.5" />
                                {formatDate(result.created_at)}
                              </span>
                              {result.processing_duration_ms && (
                                <span className="flex items-center gap-1">
                                  <Clock className="h-3.5 w-3.5" />
                                  {result.processing_duration_ms}ms
                                </span>
                              )}
                              {result.field_count > 0 && (
                                <span className="flex items-center gap-1">
                                  <FileText className="h-3.5 w-3.5" />
                                  {result.field_count} fields
                                </span>
                              )}
                            </div>
                          </div>
                        </div>

                        <div className="flex items-center gap-3">
                          {canDownloadSingle && (
                            <>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation()
                                  downloadSingleJSON(result)
                                }}
                                className="inline-flex items-center px-3 py-1.5 text-xs font-semibold text-dark bg-primary hover:bg-primary/90 rounded-lg transition-all"
                              >
                                JSON
                              </button>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation()
                                  downloadSingleCSV(result)
                                }}
                                className="inline-flex items-center px-3 py-1.5 text-xs font-semibold text-white bg-green-600 hover:bg-green-700 rounded-lg transition-all"
                              >
                                CSV
                              </button>
                            </>
                          )}
                          {isExpanded ? (
                            <ChevronDown className="h-6 w-6 text-gray-400" />
                          ) : (
                            <ChevronRight className="h-6 w-6 text-gray-400" />
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Expanded Content */}
                    {isExpanded && isSuccess && loadedResults.has(result.id) && (
                      <div className="grid grid-cols-1 lg:grid-cols-2 divide-y lg:divide-y-0 lg:divide-x divide-gray-200">
                        {/* Raw JSON */}
                        <div className="bg-gray-50">
                          <div className="px-8 py-4 text-sm font-semibold text-gray-700 border-b bg-gray-100 flex items-center gap-2">
                            <Code className="h-5 w-5" />
                            JSON Output
                          </div>
                          <pre className="p-8 overflow-auto max-h-[500px] text-sm font-mono text-gray-800 custom-scrollbar">
                            {JSON.stringify(loadedResults.get(result.id)?.results, null, 2)}
                          </pre>
                        </div>

                        {/* Formatted Preview */}
                        <div className="p-8">
                          <h4 className="text-lg font-semibold text-dark mb-6 flex items-center gap-2">
                            <FileText className="h-6 w-6 text-primary" />
                            Extracted Data
                          </h4>
                          <dl className="space-y-5">
                            {loadedResults.get(result.id)?.results && Object.entries(loadedResults.get(result.id)!.results).map(([key, value]) => (
                              <div key={key} className="pb-5 border-b border-gray-100 last:border-0">
                                <dt className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                                  {key.replace(/_/g, ' ')}
                                </dt>
                                <dd className="text-sm text-gray-900 bg-gray-50 px-4 py-3 rounded-lg">
                                  {typeof value === 'object' ? (
                                    <pre className="font-mono text-xs">{JSON.stringify(value, null, 2)}</pre>
                                  ) : (
                                    <span className="font-mono">{String(value)}</span>
                                  )}
                                </dd>
                              </div>
                            ))}
                          </dl>
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          ) : (
            <div className="text-center py-20 bg-white rounded-2xl border border-gray-200">
              <div className="inline-flex h-20 w-20 bg-gray-50 rounded-full mb-8 items-center justify-center">
                <FileText className="h-10 w-10 text-gray-400" />
              </div>
              <h3 className="text-2xl font-semibold text-dark mb-3">No Results Yet</h3>
              <p className="text-base text-gray-600 mb-6">Process some documents to see results here</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
