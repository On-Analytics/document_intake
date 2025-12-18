import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { BookOpen, FileText, Files, Zap, TrendingUp, CheckCircle2, ChevronRight, Sparkles } from 'lucide-react'
import { getOverviewStats } from '../lib/queries/overview'

export default function Overview() {
  const navigate = useNavigate()
  const [timeRange, setTimeRange] = useState<'month' | 'lifetime'>('month')
  const [pageError, setPageError] = useState<string | null>(null)

  const {
    data: stats,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['overview-stats', timeRange],
    queryFn: async () => await getOverviewStats(timeRange),
  })



  return (
    <div className="flex flex-col min-h-screen">
      {/* Page Header */}
      <div className="px-6 lg:px-8 pt-6 pb-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-dark">Overview</h1>
            <p className="text-sm text-gray-600 mt-1">Track your document extraction activity and performance</p>
          </div>

          <div className="flex items-center gap-2">
            <label className="text-xs text-gray-600">Timeframe</label>
            <select
              value={timeRange}
              onChange={(e) => setTimeRange(e.target.value as 'month' | 'lifetime')}
              className="text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white"
            >
              <option value="month">This month</option>
              <option value="lifetime">Lifetime</option>
            </select>
          </div>
        </div>
      </div>

      {/* Page Content */}
      <div className="flex-1 px-6 lg:px-8 pb-8">
        <div className="max-w-7xl mx-auto space-y-6">

          {(pageError || (isError && error)) && (
            <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="text-sm text-red-800">
                  {pageError || (error as any)?.message || 'Something went wrong.'}
                </div>
                <div className="flex items-center gap-2">
                  {isError && (
                    <button
                      type="button"
                      onClick={() => refetch()}
                      className="rounded-lg bg-white px-3 py-1.5 text-xs font-semibold text-red-700 border border-red-200 hover:bg-red-50 transition-all"
                    >
                      Retry
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => setPageError(null)}
                    className="rounded-lg px-3 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-100 transition-all"
                  >
                    Dismiss
                  </button>
                </div>
              </div>
            </div>
          )}

          {isLoading && (
            <div className="flex items-center justify-center h-64">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
            </div>
          )}

          {!isLoading && stats && (stats.totalExtractions > 0 || stats.totalDocuments > 0 || stats.totalPages > 0) ? (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-4">
                <div className="bg-white rounded-xl p-5 border border-gray-200 hover:border-primary/30 transition-all">
                  <div className="flex items-center gap-3">
                    <div className="h-10 w-10 bg-primary/10 rounded-lg flex items-center justify-center">
                      <FileText className="h-5 w-5 text-primary" />
                    </div>
                    <div>
                      <p className="text-2xl font-bold text-dark">{stats.totalExtractions}</p>
                      <p className="text-xs text-gray-600">Total Extractions</p>
                    </div>
                  </div>
                </div>

                <div className="bg-white rounded-xl p-5 border border-gray-200 hover:border-blue-300 transition-all">
                  <div className="flex items-center gap-3">
                    <div className="h-10 w-10 bg-blue-50 rounded-lg flex items-center justify-center">
                      <Files className="h-5 w-5 text-blue-600" />
                    </div>
                    <div>
                      <p className="text-2xl font-bold text-dark">{stats.totalDocuments}</p>
                      <p className="text-xs text-gray-600">Total Documents</p>
                    </div>
                  </div>
                </div>

                <div className="bg-white rounded-xl p-5 border border-gray-200 hover:border-indigo-300 transition-all">
                  <div className="flex items-center gap-3">
                    <div className="h-10 w-10 bg-indigo-50 rounded-lg flex items-center justify-center">
                      <BookOpen className="h-5 w-5 text-indigo-600" />
                    </div>
                    <div>
                      <p className="text-2xl font-bold text-dark">{stats.totalPages}</p>
                      <p className="text-xs text-gray-600">Total Pages</p>
                    </div>
                  </div>
                </div>

                <div className="bg-white rounded-xl p-5 border border-gray-200 hover:border-green-300 transition-all">
                  <div className="flex items-center gap-3">
                    <div className="h-10 w-10 bg-green-50 rounded-lg flex items-center justify-center">
                      <CheckCircle2 className="h-5 w-5 text-green-600" />
                    </div>
                    <div>
                      <p className="text-2xl font-bold text-dark">{stats.successful}</p>
                      <p className="text-xs text-gray-600">Successful</p>
                    </div>
                  </div>
                </div>

                <div className="bg-white rounded-xl p-5 border border-gray-200 hover:border-amber-300 transition-all">
                  <div className="flex items-center gap-3">
                    <div className="h-10 w-10 bg-amber-50 rounded-lg flex items-center justify-center">
                      <TrendingUp className="h-5 w-5 text-amber-600" />
                    </div>
                    <div>
                      <p className="text-2xl font-bold text-dark">{stats.successRate}%</p>
                      <p className="text-xs text-gray-600">Success Rate</p>
                    </div>
                  </div>
                </div>

                <div className="bg-white rounded-xl p-5 border border-gray-200 hover:border-primary/30 transition-all">
                  <div className="flex items-center gap-3">
                    <div className="h-10 w-10 bg-primary/10 rounded-lg flex items-center justify-center">
                      <Zap className="h-5 w-5 text-primary" />
                    </div>
                    <div>
                      <p className="text-2xl font-bold text-dark">{stats.totalSchemas}</p>
                      <p className="text-xs text-gray-600">Templates</p>
                    </div>
                  </div>
                </div>
              </div>





              <div className="bg-primary/5 border border-primary/20 rounded-xl p-6 text-center">
                <div className="inline-flex items-center justify-center h-12 w-12 bg-white rounded-full mb-3">
                  <Sparkles className="h-6 w-6 text-primary" />
                </div>
                <h3 className="text-lg font-bold text-dark mb-1">Ready to extract more data?</h3>
                <p className="text-sm text-gray-700 mb-4">
                  Upload documents and let AI extract structured data in seconds
                </p>
                <button
                  onClick={() => navigate('/')}
                  className="inline-flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-dark hover:bg-primary/90 transition-all"
                >
                  <Sparkles className="h-4 w-4" />
                  Start Extracting
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            </>
          ) : !isLoading ? (
            <div className="bg-white rounded-xl border border-gray-200 p-10 text-center">
              <div className="inline-flex items-center justify-center h-14 w-14 bg-gray-50 rounded-full mb-4">
                <FileText className="h-7 w-7 text-gray-400" />
              </div>
              <h3 className="text-xl font-bold text-dark mb-2">No extractions yet</h3>
              <p className="text-sm text-gray-600 mb-6 max-w-md mx-auto">
                Get started by uploading your first document. AI will extract structured data automatically.
              </p>
              <button
                onClick={() => navigate('/')}
                className="inline-flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-dark hover:bg-primary/90 transition-all"
              >
                <Sparkles className="h-4 w-4" />
                Start Extracting
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}
