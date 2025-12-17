import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { supabase } from '../lib/supabase'
import { BookOpen, FileText, Files, Zap, TrendingUp, CheckCircle2, ChevronRight, Sparkles } from 'lucide-react'

export default function Overview() {
  const navigate = useNavigate()
  const [timeRange, setTimeRange] = useState<'month' | 'lifetime'>('month')

  const { data: stats } = useQuery({
    queryKey: ['overview-stats', timeRange],
    queryFn: async () => {
      const { data: { user } } = await supabase.auth.getUser()
      if (!user) return null

      const { data: profile } = await supabase
        .from('profiles')
        .select('tenant_id')
        .eq('id', user.id)
        .single()

      if (!profile) return null

      const periodStart = new Date()
      periodStart.setUTCDate(1)
      periodStart.setUTCHours(0, 0, 0, 0)

      const createdAtFilterIso = periodStart.toISOString()

      const extractionsQuery = supabase
        .from('extraction_results')
        .select('id, status')
        .eq('tenant_id', profile.tenant_id)

      const { data: extractions } = timeRange === 'month'
        ? await extractionsQuery.gte('created_at', createdAtFilterIso)
        : await extractionsQuery

      const { data: schemas } = await supabase
        .from('schemas')
        .select('id')
        .or(`tenant_id.eq.${profile.tenant_id},is_public.eq.true`)

      const documentsCountQuery = supabase
        .from('documents')
        .select('id', { count: 'exact', head: true })
        .eq('tenant_id', profile.tenant_id)

      const { count: documentsCount } = timeRange === 'month'
        ? await documentsCountQuery.gte('created_at', createdAtFilterIso)
        : await documentsCountQuery

      const documentsPagesQuery = supabase
        .from('documents')
        .select('page_count')
        .eq('tenant_id', profile.tenant_id)

      const { data: documentPagesInRange } = timeRange === 'month'
        ? await documentsPagesQuery.gte('created_at', createdAtFilterIso)
        : await documentsPagesQuery

      const total = extractions?.length || 0
      const successful = extractions?.filter(e => e.status === 'completed').length || 0
      const failed = extractions?.filter(e => e.status === 'failed').length || 0
      const successRate = total > 0 ? Math.round((successful / total) * 100) : 0

      return {
        totalExtractions: total,
        totalDocuments: documentsCount || 0,
        totalPages: documentPagesInRange?.reduce((acc, d) => acc + (d.page_count || 0), 0) || 0,
        successful,
        failed,
        successRate,
        totalSchemas: schemas?.length || 0
      }
    }
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

          {stats && (stats.totalExtractions > 0 || stats.totalDocuments > 0 || stats.totalPages > 0) ? (
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
          ) : (
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
          )}
        </div>
      </div>
    </div>
  )
}
