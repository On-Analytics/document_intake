import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { supabase } from '../lib/supabase'
import { FileText, Calendar, Clock, CheckCircle, AlertCircle, Code, ChevronDown, ChevronRight, FileJson, FileSpreadsheet, FolderOpen } from 'lucide-react'
import '../utils/debugStorage'

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
}

interface StoredResult {
  results: any
  operational_metadata: any
}

export default function History() {
  const [expandedResults, setExpandedResults] = useState<Set<string>>(new Set())
  const [loadedResults, setLoadedResults] = useState<Map<string, StoredResult>>(new Map())

  // Fetch extraction results
  const { data: results, isLoading } = useQuery({
    queryKey: ['extraction-results'],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('extraction_results')
        .select('*')
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

  // Load all results from localStorage when results are fetched
  useEffect(() => {
    if (results && results.length > 0) {
      console.log('Loading results from localStorage. Total results:', results.length)
      const newLoadedResults = new Map<string, StoredResult>()
      
      results.forEach(result => {
        const storageKey = `extraction_result_${result.id}`
        console.log('Looking for:', storageKey)
        const stored = localStorage.getItem(storageKey)
        if (stored) {
          try {
            const parsed = JSON.parse(stored)
            newLoadedResults.set(result.id, parsed)
            console.log('✓ Loaded:', storageKey)
          } catch (e) {
            console.error(`Failed to parse stored result for ${result.id}:`, e)
          }
        } else {
          console.warn('✗ Not found in localStorage:', storageKey)
        }
      })
      
      console.log('Total loaded from localStorage:', newLoadedResults.size)
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
    <div className="min-h-screen">
      {/* Page Header */}
      <div className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="p-3 bg-gradient-to-br from-amber-500 to-orange-500 rounded-2xl shadow-lg">
                <FolderOpen className="h-7 w-7 text-white" />
              </div>
              <div>
                <h1 className="text-3xl font-bold text-gray-900">Results</h1>
                <p className="text-gray-600 mt-1">View and download your extraction results</p>
              </div>
            </div>
            {results && results.length > 0 && (
              <div className="flex items-center gap-2">
                <button
                  onClick={downloadAllJSON}
                  className="flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-white bg-gradient-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 rounded-xl shadow-lg hover:shadow-xl transition-all"
                >
                  <FileJson className="h-4 w-4" />
                  JSON
                </button>
                <button
                  onClick={downloadAllCSV}
                  className="flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-white bg-gradient-to-r from-green-500 to-emerald-500 hover:from-green-600 hover:to-emerald-600 rounded-xl shadow-lg hover:shadow-xl transition-all"
                >
                  <FileSpreadsheet className="h-4 w-4" />
                  CSV
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Page Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="space-y-6">

      {/* Results List */}
      {results && results.length > 0 ? (
        <div className="space-y-4">
          {results.map((result) => {
            const isExpanded = expandedResults.has(result.id)
            const isSuccess = result.status === 'completed'
            
            return (
              <div 
                key={result.id} 
                className="bg-white rounded-xl border border-gray-200 shadow-sm hover:shadow-md transition-all overflow-hidden"
              >
                {/* Header */}
                <div 
                  className={`p-6 cursor-pointer ${
                    isSuccess 
                      ? 'bg-gradient-to-r from-green-50 to-emerald-50 border-b border-green-100' 
                      : 'bg-gradient-to-r from-red-50 to-rose-50 border-b border-red-100'
                  }`}
                  onClick={() => toggleExpanded(result.id)}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4 flex-1">
                      <div className={`p-2 rounded-xl ${
                        isSuccess ? 'bg-green-100' : 'bg-red-100'
                      }`}>
                        {isSuccess ? (
                          <CheckCircle className="h-6 w-6 text-green-600" />
                        ) : (
                          <AlertCircle className="h-6 w-6 text-red-600" />
                        )}
                      </div>
                      
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-3 mb-1">
                          <h3 className="font-semibold text-gray-900 truncate">
                            {result.filename}
                          </h3>
                          {result.schema_name && (
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-primary/10 text-primary">
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
                      {isExpanded ? (
                        <ChevronDown className="h-5 w-5 text-gray-400" />
                      ) : (
                        <ChevronRight className="h-5 w-5 text-gray-400" />
                      )}
                    </div>
                  </div>
                </div>

                {/* Expanded Content */}
                {isExpanded && isSuccess && loadedResults.has(result.id) && (
                  <div className="grid grid-cols-1 lg:grid-cols-2 divide-y lg:divide-y-0 lg:divide-x divide-gray-200">
                    {/* Raw JSON */}
                    <div className="bg-gray-50">
                      <div className="px-6 py-3 text-xs font-semibold text-gray-600 border-b bg-gray-100 flex items-center gap-2">
                        <Code className="h-4 w-4" />
                        JSON Output
                      </div>
                      <pre className="p-6 overflow-auto max-h-[500px] text-sm font-mono text-gray-800 custom-scrollbar">
                        {JSON.stringify(loadedResults.get(result.id)?.results, null, 2)}
                      </pre>
                    </div>

                    {/* Formatted Preview */}
                    <div className="p-6">
                      <h4 className="font-semibold text-gray-900 mb-6 flex items-center gap-2">
                        <FileText className="h-5 w-5 text-primary" />
                        Extracted Data
                      </h4>
                      <dl className="space-y-4">
                        {loadedResults.get(result.id)?.results && typeof loadedResults.get(result.id)?.results === 'object' && Object.entries(loadedResults.get(result.id)!.results).map(([key, value]) => (
                          <div key={key} className="pb-4 border-b border-gray-100 last:border-0">
                            <dt className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">
                              {key.replace(/_/g, ' ')}
                            </dt>
                            <dd className="text-sm text-gray-900 font-mono bg-gray-50 px-3 py-2 rounded-lg">
                              {typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)}
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
        <div className="text-center py-16 bg-white rounded-2xl border-2 border-dashed border-gray-300">
          <div className="inline-flex p-4 bg-gray-100 rounded-full mb-4">
            <FileText className="h-8 w-8 text-gray-400" />
          </div>
          <h3 className="text-lg font-semibold text-gray-900 mb-2">No Results Yet</h3>
          <p className="text-gray-600 mb-6">Process some documents to see results here</p>
        </div>
      )}
        </div>
      </div>
    </div>
  )
}
