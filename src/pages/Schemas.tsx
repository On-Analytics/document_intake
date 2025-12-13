import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { supabase } from '../lib/supabase'
import { Plus, Code, FileText, Edit, Eye, Trash2, Copy } from 'lucide-react'
import CreateSchemaModal, { SchemaData } from '../components/CreateSchemaModal'

export default function Schemas() {
  const queryClient = useQueryClient()
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingSchema, setEditingSchema] = useState<any | null>(null)
  const [viewingSchema, setViewingSchema] = useState<any | null>(null)

  // Fetch Schemas with content
  const { data: schemas } = useQuery({
    queryKey: ['schemas'],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('schemas')
        .select('*')
        .order('is_public', { ascending: false })
        .order('name')

      if (error) throw error
      return data
    }
  })

  // Delete Schema Mutation
  const deleteMutation = useMutation({
    mutationFn: async (schemaId: string) => {
      const { error } = await supabase
        .from('schemas')
        .delete()
        .eq('id', schemaId)

      if (error) throw error
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['schemas'] })
    },
    onError: (err: any) => alert(err.message)
  })

  const handleEdit = (schema: any) => {
    // Convert schema to SchemaData format for the modal
    const schemaData: SchemaData = {
      name: schema.name,
      description: schema.description || '',
      fields: schema.content.fields || []
    }
    setEditingSchema({ id: schema.id, data: schemaData })
    setIsModalOpen(true)
  }

  const handleClone = (schema: any) => {
    // Convert schema to SchemaData format for the modal with "(Copy)" suffix
    const schemaData: SchemaData = {
      name: schema.name + ' (Copy)',
      description: schema.description || '',
      fields: schema.content.fields || []
    }
    // Don't set editingSchema ID, so it creates a new template
    setEditingSchema({ id: null, data: schemaData })
    setIsModalOpen(true)
  }

  const handleView = (schema: any) => {
    setViewingSchema(schema)
  }

  const handleDelete = (schemaId: string, schemaName: string) => {
    if (confirm(`Are you sure you want to delete "${schemaName}"?`)) {
      deleteMutation.mutate(schemaId)
    }
  }

  const handleModalSuccess = () => {
    queryClient.invalidateQueries({ queryKey: ['schemas'] })
    setIsModalOpen(false)
    setEditingSchema(null)
  }

  const handleModalClose = () => {
    setIsModalOpen(false)
    setEditingSchema(null)
  }

  return (
    <div className="flex flex-col min-h-screen">
      {/* Page Header */}
      <div className="px-6 lg:px-8 pt-6 pb-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-dark">Templates</h1>
            <p className="text-sm text-gray-600 mt-1">Create and manage custom extraction schemas</p>
          </div>
          <button
            onClick={() => setIsModalOpen(true)}
            className="flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-dark hover:bg-primary/90 transition-all"
          >
            <Plus className="h-4 w-4" />
            New Template
          </button>
        </div>
      </div>

      {/* Page Content */}
      <div className="flex-1 px-6 lg:px-8 pb-8">
        <div className="max-w-7xl mx-auto space-y-6">

          {/* View Schema Modal */}
          {viewingSchema && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-in fade-in" onClick={() => setViewingSchema(null)}>
              <div className="bg-white rounded-2xl shadow-2xl w-full max-w-3xl max-h-[90vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
                <div className="flex items-center justify-between p-6 border-b border-gray-200">
                  <div>
                    <h2 className="text-xl font-bold text-gray-900">{viewingSchema.name}</h2>
                    <p className="text-sm text-gray-600 mt-1">{viewingSchema.description || 'No description'}</p>
                  </div>
                  <button onClick={() => setViewingSchema(null)} className="text-gray-400 hover:text-gray-600">
                    <Plus className="h-6 w-6 rotate-45" />
                  </button>
                </div>
                <div className="flex-1 overflow-y-auto p-6 custom-scrollbar">
                  <pre className="bg-gray-50 p-4 rounded-lg text-sm font-mono overflow-x-auto">
                    {JSON.stringify(viewingSchema.content, null, 2)}
                  </pre>
                </div>
                <div className="p-6 border-t border-gray-200 flex justify-end gap-3">
                  {!viewingSchema.is_public && (
                    <button
                      onClick={() => {
                        setViewingSchema(null)
                        handleEdit(viewingSchema)
                      }}
                      className="px-4 py-2 text-sm font-medium text-blue-600 bg-blue-50 rounded-lg hover:bg-blue-100 transition-all"
                    >
                      Edit Template
                    </button>
                  )}
                  <button
                    onClick={() => setViewingSchema(null)}
                    className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-all"
                  >
                    Close
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Templates Grid */}
          <div>
            {schemas && schemas.length > 0 ? (
              <div className="grid grid-cols-1 gap-8 sm:grid-cols-2 lg:grid-cols-3">
                {schemas.map((schema) => (
                  <div key={schema.id} className="group relative flex flex-col rounded-2xl border border-gray-200 bg-white p-8 hover:border-primary/30 transition-all duration-200">
                    <div className="flex items-start justify-between mb-6">
                      <div className="flex items-center gap-4">
                        <div className="h-12 w-12 bg-gray-50 rounded-xl flex items-center justify-center group-hover:bg-primary/10 transition-colors">
                          <FileText className="h-6 w-6 text-gray-400 group-hover:text-primary transition-colors" />
                        </div>
                        <h3 className="font-semibold text-dark text-lg">{schema.name}</h3>
                      </div>
                      {schema.is_public ? (
                        <span className="inline-flex items-center rounded-full bg-gray-100 px-3 py-1 text-xs font-semibold text-gray-600">
                          System
                        </span>
                      ) : (
                        <button
                          onClick={() => handleDelete(schema.id, schema.name)}
                          className="text-gray-400 hover:text-red-600 hover:bg-red-50 p-2 rounded-lg transition-colors"
                          title="Delete template"
                        >
                          <Trash2 className="h-5 w-5" />
                        </button>
                      )}
                    </div>
                    <p className="text-sm text-gray-600 flex-1 leading-relaxed mb-8">
                      {schema.description || "No description provided."}
                    </p>
                    <div className="pt-6 border-t border-gray-100">
                      <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-2 text-xs text-gray-500">
                          <Code className="h-4 w-4" />
                          <span className="font-medium">{schema.content.fields?.length || 0} fields</span>
                        </div>
                      </div>
                      <div className="flex gap-3">
                        <button
                          onClick={() => handleView(schema)}
                          className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 text-xs font-semibold text-gray-700 bg-gray-50 hover:bg-gray-100 rounded-lg transition-all"
                        >
                          <Eye className="h-4 w-4" />
                          View
                        </button>
                        <button
                          onClick={() => handleClone(schema)}
                          className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 text-xs font-semibold text-primary bg-primary/5 hover:bg-primary/10 rounded-lg transition-all"
                          title="Clone this template"
                        >
                          <Copy className="h-4 w-4" />
                          Clone
                        </button>
                        {!schema.is_public && (
                          <button
                            onClick={() => handleEdit(schema)}
                            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 text-xs font-semibold text-dark bg-gray-100 hover:bg-gray-200 rounded-lg transition-all"
                          >
                            <Edit className="h-4 w-4" />
                            Edit
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-20 bg-white rounded-2xl border border-gray-200">
                <div className="inline-flex h-20 w-20 bg-gray-50 rounded-full mb-8 items-center justify-center">
                  <FileText className="h-10 w-10 text-gray-400" />
                </div>
                <h3 className="text-2xl font-semibold text-dark mb-3">No templates yet</h3>
                <p className="text-base text-gray-600 mb-8">Create your first extraction template to get started</p>
                <button
                  onClick={() => setIsModalOpen(true)}
                  className="inline-flex items-center gap-2 rounded-xl bg-primary px-8 py-4 text-sm font-semibold text-dark hover:bg-primary/90 transition-all"
                >
                  <Plus className="h-5 w-5" />
                  Create Template
                </button>
              </div>
            )}
          </div>

          {/* Create/Edit Schema Modal */}
          <CreateSchemaModal
            isOpen={isModalOpen}
            onClose={handleModalClose}
            onSuccess={handleModalSuccess}
            initialData={editingSchema?.data || null}
            existingSchemaId={editingSchema?.id || null}
          />
        </div>
      </div>
    </div>
  )
}
