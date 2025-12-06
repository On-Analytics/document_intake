import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { supabase } from '../lib/supabase'
import { FileText, Zap, TrendingUp, CheckCircle2, ChevronRight, Clock, AlertCircle, Sparkles } from 'lucide-react'

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
      <div className="px-6 lg:px-8 pt-6 pb-4">
        <h1 className="text-2xl font-bold text-dark">Overview</h1>
        <p className="text-sm text-gray-600 mt-1">Track your document extraction activity and performance</p>
      </div>

      {/* Page Content */}
      <div className="flex-1 px-6 lg:px-8 pb-8">
        <div className="max-w-7xl mx-auto space-y-6">

          {stats && stats.totalExtractions > 0 ? (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
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

              {stats.failed > 0 && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                  <div className="flex items-center gap-3">
                    <div className="h-8 w-8 bg-red-100 rounded-lg flex items-center justify-center flex-shrink-0">
                      <AlertCircle className="h-4 w-4 text-red-600" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-red-900">
                        {stats.failed} extraction{stats.failed > 1 ? 's' : ''} failed. <span className="font-normal text-red-700">Check your results for details.</span>
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {recentExtractions && recentExtractions.length > 0 && (
                <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
                  <div className="px-5 py-3 border-b border-gray-200">
                    <div className="flex items-center justify-between">
                      <h3 className="text-sm font-semibold text-dark flex items-center gap-2">
                        <Clock className="h-4 w-4 text-gray-500" />
                        Recent Extractions
                      </h3>
                      <button
                        onClick={() => navigate('/history')}
                        className="text-xs font-medium text-primary hover:text-primary/80 flex items-center gap-1"
                      >
                        View All
                        <ChevronRight className="h-3 w-3" />
                      </button>
                    </div>
                  </div>
                  <div className="divide-y divide-gray-100">
                    {recentExtractions.map((extraction) => (
                      <div
                        key={extraction.id}
                        className="flex items-center justify-between px-5 py-3 hover:bg-gray-50 transition-colors cursor-pointer"
                        onClick={() => navigate('/history')}
                      >
                        <div className="flex items-center gap-3 flex-1 min-w-0">
                          {extraction.status === 'completed' ? (
                            <CheckCircle2 className="h-4 w-4 text-green-600 shrink-0" />
                          ) : (
                            <AlertCircle className="h-4 w-4 text-red-600 shrink-0" />
                          )}
                          <div className="flex-1 min-w-0">
                            <p className="font-medium text-dark text-sm truncate">
                              {extraction.filename}
                            </p>
                            <p className="text-xs text-gray-500">
                              {extraction.schema_name || 'Auto-detected'} • {new Date(extraction.created_at).toLocaleDateString()}
                            </p>
                          </div>
                        </div>
                        <ChevronRight className="h-4 w-4 text-gray-400 shrink-0" />
                      </div>
                    ))}
                  </div>
                </div>
              )}

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
