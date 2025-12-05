import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { supabase } from '../lib/supabase'
import { FileText, Zap, TrendingUp, CheckCircle2, ChevronRight, Clock, AlertCircle, Sparkles, LayoutDashboard } from 'lucide-react'

export default function Overview() {
  const navigate = useNavigate()

  const { data: stats } = useQuery({
    queryKey: ['overview-stats'],
    queryFn: async () => {
      const { data: { user } } = await supabase.auth.getUser()
      if (!user) return null

      const { data: profile } = await supabase
        .from('profiles')
        .select('tenant_id')
        .eq('id', user.id)
        .single()

      if (!profile) return null

      const { data: extractions } = await supabase
        .from('extraction_results')
        .select('id, status')
        .eq('tenant_id', profile.tenant_id)

      const { data: schemas } = await supabase
        .from('schemas')
        .select('id')
        .or(`tenant_id.eq.${profile.tenant_id},is_public.eq.true`)

      const total = extractions?.length || 0
      const successful = extractions?.filter(e => e.status === 'completed').length || 0
      const failed = extractions?.filter(e => e.status === 'failed').length || 0
      const successRate = total > 0 ? Math.round((successful / total) * 100) : 0

      return {
        totalExtractions: total,
        successful,
        failed,
        successRate,
        totalSchemas: schemas?.length || 0
      }
    }
  })

  const { data: recentExtractions } = useQuery({
    queryKey: ['recent-extractions'],
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
        .limit(5)

      if (error) throw error
      return data || []
    }
  })

  return (
    <div className="flex flex-col min-h-screen">
      {/* Page Header */}
      <div className="bg-white border-b border-gray-200 shadow-sm sticky top-0 z-10">
        <div className="px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-gradient-to-br from-blue-500 to-indigo-500 rounded-2xl shadow-lg">
              <LayoutDashboard className="h-7 w-7 text-white" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-gray-900">Overview</h1>
              <p className="text-gray-600 mt-1">Track your document extraction activity and performance</p>
            </div>
          </div>
        </div>
      </div>

      {/* Page Content */}
      <div className="flex-1 px-4 sm:px-6 lg:px-8 py-8">
        <div className="max-w-7xl mx-auto space-y-8">

      {stats && stats.totalExtractions > 0 ? (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            <div className="bg-white rounded-xl p-6 border border-gray-200 shadow-sm hover:shadow-md transition-shadow">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-blue-100 rounded-xl">
                  <FileText className="h-6 w-6 text-blue-600" />
                </div>
                <div>
                  <p className="text-3xl font-bold text-gray-900">{stats.totalExtractions}</p>
                  <p className="text-sm text-gray-600">Total Extractions</p>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-xl p-6 border border-gray-200 shadow-sm hover:shadow-md transition-shadow">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-green-100 rounded-xl">
                  <CheckCircle2 className="h-6 w-6 text-green-600" />
                </div>
                <div>
                  <p className="text-3xl font-bold text-gray-900">{stats.successful}</p>
                  <p className="text-sm text-gray-600">Successful</p>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-xl p-6 border border-gray-200 shadow-sm hover:shadow-md transition-shadow">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-amber-100 rounded-xl">
                  <TrendingUp className="h-6 w-6 text-amber-600" />
                </div>
                <div>
                  <p className="text-3xl font-bold text-gray-900">{stats.successRate}%</p>
                  <p className="text-sm text-gray-600">Success Rate</p>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-xl p-6 border border-gray-200 shadow-sm hover:shadow-md transition-shadow">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-purple-100 rounded-xl">
                  <Zap className="h-6 w-6 text-purple-600" />
                </div>
                <div>
                  <p className="text-3xl font-bold text-gray-900">{stats.totalSchemas}</p>
                  <p className="text-sm text-gray-600">Templates</p>
                </div>
              </div>
            </div>
          </div>

          {stats.failed > 0 && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-6">
              <div className="flex items-start gap-4">
                <AlertCircle className="h-6 w-6 text-red-600 shrink-0 mt-0.5" />
                <div>
                  <h3 className="font-semibold text-red-900 mb-1">Failed Extractions</h3>
                  <p className="text-sm text-red-700">
                    {stats.failed} extraction{stats.failed > 1 ? 's' : ''} failed. Check your results for more details.
                  </p>
                </div>
              </div>
            </div>
          )}

          {recentExtractions && recentExtractions.length > 0 && (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
              <div className="p-6 border-b border-gray-200 bg-gray-50">
                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                    <Clock className="h-5 w-5 text-gray-500" />
                    Recent Extractions
                  </h3>
                  <button
                    onClick={() => navigate('/history')}
                    className="text-sm font-medium text-blue-600 hover:text-blue-700 flex items-center gap-1"
                  >
                    View All
                    <ChevronRight className="h-4 w-4" />
                  </button>
                </div>
              </div>
              <div className="divide-y divide-gray-100">
                {recentExtractions.map((extraction) => (
                  <div
                    key={extraction.id}
                    className="flex items-center justify-between p-4 hover:bg-gray-50 transition-colors cursor-pointer"
                    onClick={() => navigate('/history')}
                  >
                    <div className="flex items-center gap-4 flex-1 min-w-0">
                      {extraction.status === 'completed' ? (
                        <CheckCircle2 className="h-5 w-5 text-green-600 shrink-0" />
                      ) : (
                        <AlertCircle className="h-5 w-5 text-red-600 shrink-0" />
                      )}
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-gray-900 text-sm truncate">
                          {extraction.filename}
                        </p>
                        <p className="text-xs text-gray-500">
                          {extraction.schema_name || 'Auto-detected'} • {new Date(extraction.created_at).toLocaleDateString()}
                        </p>
                      </div>
                    </div>
                    <ChevronRight className="h-5 w-5 text-gray-400 shrink-0" />
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="bg-gradient-to-br from-green-50 to-emerald-50 border border-green-200 rounded-xl p-8 text-center">
            <div className="inline-flex items-center justify-center p-4 bg-white rounded-full shadow-sm mb-4">
              <Sparkles className="h-8 w-8 text-green-600" />
            </div>
            <h3 className="text-xl font-bold text-gray-900 mb-2">Ready to extract more data?</h3>
            <p className="text-gray-600 mb-6">
              Upload your documents and let AI extract structured data in seconds
            </p>
            <button
              onClick={() => navigate('/')}
              className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-green-500 to-emerald-500 px-6 py-3 text-base font-semibold text-white shadow-lg hover:shadow-xl hover:scale-[1.02] transition-all"
            >
              <Sparkles className="h-5 w-5" />
              Start Extracting
              <ChevronRight className="h-5 w-5" />
            </button>
          </div>
        </>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-12 text-center">
          <div className="inline-flex items-center justify-center p-4 bg-gray-100 rounded-full mb-6">
            <FileText className="h-12 w-12 text-gray-400" />
          </div>
          <h3 className="text-xl font-bold text-gray-900 mb-2">No extractions yet</h3>
          <p className="text-gray-600 mb-8 max-w-md mx-auto">
            Get started by uploading your first document. AI will extract structured data automatically.
          </p>
          <button
            onClick={() => navigate('/')}
            className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-green-500 to-emerald-500 px-6 py-3 text-base font-semibold text-white shadow-lg hover:shadow-xl hover:scale-[1.02] transition-all"
          >
            <Sparkles className="h-5 w-5" />
            Start Extracting
            <ChevronRight className="h-5 w-5" />
          </button>
        </div>
      )}
        </div>
      </div>
    </div>
  )
}
