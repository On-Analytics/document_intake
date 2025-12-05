import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { supabase } from '../lib/supabase'
import { X, Plus, Trash2, Save, HelpCircle, Sparkles, ChevronDown, ChevronRight, GripVertical, Archive } from 'lucide-react'

interface SchemaField {
  name: string
  type: FieldType
  description: string
  required?: boolean
  nested_fields?: SchemaField[]  // For object and list[object] types
}

export interface SchemaData {
  name: string
  description: string
  fields: SchemaField[]
}

interface CreateSchemaModalProps {
  isOpen: boolean
  onClose: () => void
  onSuccess: (newSchemaId: string) => void
  initialData?: SchemaData | null
  existingSchemaId?: string | null
}

type FieldType = 'string' | 'number' | 'date' | 'boolean' | 'list[string]' | 'object' | 'list[object]'

export default function CreateSchemaModal({ isOpen, onClose, onSuccess, initialData, existingSchemaId }: CreateSchemaModalProps) {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [fields, setFields] = useState<SchemaField[]>([
    { name: 'new_field', type: 'string', description: '', required: false, nested_fields: [] }
  ])
  const [expandedFields, setExpandedFields] = useState<Set<string>>(new Set())
  const [draggedPath, setDraggedPath] = useState<string | null>(null)
  const [dragOverPath, setDragOverPath] = useState<string | null>(null)
  const [hasDraft, setHasDraft] = useState(false)

  const DRAFT_KEY = 'schema_draft'

  const loadDraft = () => {
    try {
      const draft = localStorage.getItem(DRAFT_KEY)
      if (draft) {
        const parsed = JSON.parse(draft)
        setName(parsed.name || '')
        setDescription(parsed.description || '')
        setFields(parsed.fields || [{ name: 'field_1', type: 'string', description: '', required: false, nested_fields: [] }])
        setHasDraft(true)
      }
    } catch (e) {
      console.error('Failed to load draft:', e)
    }
  }

  const clearDraft = () => {
    localStorage.removeItem(DRAFT_KEY)
    setHasDraft(false)
  }

  const saveDraft = () => {
    const draft = {
      name,
      description,
      fields,
      timestamp: Date.now()
    }
    localStorage.setItem(DRAFT_KEY, JSON.stringify(draft))
  }

  useEffect(() => {
    if (isOpen) {
      if (initialData) {
        clearDraft()
        setName(initialData.name + ' (Copy)')
        setDescription(initialData.description)
        setFields(initialData.fields)
      } else if (existingSchemaId) {
        clearDraft()
      } else {
        const draft = localStorage.getItem(DRAFT_KEY)
        if (draft) {
          setHasDraft(true)
        } else {
          setName('')
          setDescription('')
          setFields([{ name: 'field_1', type: 'string', description: '', required: false, nested_fields: [] }])
          setExpandedFields(new Set())
        }
      }
    }
  }, [isOpen, initialData, existingSchemaId])

  useEffect(() => {
    if (isOpen && !initialData && !existingSchemaId) {
      const timeoutId = setTimeout(() => {
        if (name || description || fields.some(f => f.name || f.description)) {
          saveDraft()
        }
      }, 1000)
      return () => clearTimeout(timeoutId)
    }
  }, [name, description, fields, isOpen, initialData, existingSchemaId])

  const addField = (parentPath?: string) => {
    if (!parentPath) {
      // Add top-level field
      setFields([...fields, { name: '', type: 'string', description: '', required: false, nested_fields: [] }])
    } else {
      // Add nested field
      const newFields = addNestedField(fields, parentPath)
      setFields(newFields)
    }
  }

  const addNestedField = (fieldsList: SchemaField[], path: string): SchemaField[] => {
    const pathParts = path.split('.')
    const newFields = [...fieldsList]

    let current: SchemaField[] = newFields
    for (let i = 0; i < pathParts.length - 1; i++) {
      const idx = parseInt(pathParts[i])
      if (current[idx].nested_fields) {
        current = current[idx].nested_fields!
      }
    }

    const lastIdx = parseInt(pathParts[pathParts.length - 1])
    if (!current[lastIdx].nested_fields) {
      current[lastIdx].nested_fields = []
    }
    current[lastIdx].nested_fields!.push({ name: '', type: 'string', description: '', required: false, nested_fields: [] })

    return newFields
  }

  const removeField = (path: string) => {
    const pathParts = path.split('.')
    if (pathParts.length === 1) {
      // Remove top-level field
      const idx = parseInt(pathParts[0])
      setFields(fields.filter((_, i) => i !== idx))
    } else {
      // Remove nested field
      const newFields = removeNestedField(fields, path)
      setFields(newFields)
    }
  }

  const removeNestedField = (fieldsList: SchemaField[], path: string): SchemaField[] => {
    const pathParts = path.split('.')
    const newFields = JSON.parse(JSON.stringify(fieldsList)) // Deep clone
    
    let current: SchemaField[] = newFields
    for (let i = 0; i < pathParts.length - 1; i++) {
      const idx = parseInt(pathParts[i])
      if (i === pathParts.length - 2) {
        // Parent of the field to remove
        const removeIdx = parseInt(pathParts[pathParts.length - 1])
        current[idx].nested_fields = current[idx].nested_fields!.filter((_, j) => j !== removeIdx)
        break
      } else {
        current = current[idx].nested_fields!
      }
    }
    
    return newFields
  }

  const updateField = (path: string, key: keyof SchemaField, value: string | boolean) => {
    const pathParts = path.split('.')
    const newFields = JSON.parse(JSON.stringify(fields)) // Deep clone

    let current: SchemaField[] = newFields
    for (let i = 0; i < pathParts.length - 1; i++) {
      const idx = parseInt(pathParts[i])
      current = current[idx].nested_fields!
    }

    const lastIdx = parseInt(pathParts[pathParts.length - 1])
    current[lastIdx] = { ...current[lastIdx], [key]: value }

    // When changing to/from object or list[object], initialize/clear nested_fields
    if (key === 'type') {
      if (value === 'object' || value === 'list[object]') {
        if (!current[lastIdx].nested_fields) {
          current[lastIdx].nested_fields = []
        }
      } else {
        delete current[lastIdx].nested_fields
      }
    }

    setFields(newFields)
  }

  const toggleExpanded = (path: string) => {
    const newExpanded = new Set(expandedFields)
    if (newExpanded.has(path)) {
      newExpanded.delete(path)
    } else {
      newExpanded.add(path)
    }
    setExpandedFields(newExpanded)
  }

  const moveField = (fromPath: string, toPath: string) => {
    if (fromPath === toPath) return
    
    const fromParts = fromPath.split('.')
    const toParts = toPath.split('.')
    
    // Check if they're at the same level (same parent)
    if (fromParts.length !== toParts.length) return
    if (fromParts.length > 1 && fromParts.slice(0, -1).join('.') !== toParts.slice(0, -1).join('.')) return
    
    const newFields = JSON.parse(JSON.stringify(fields)) // Deep clone
    
    // Navigate to the parent array
    let currentArray: SchemaField[] = newFields
    for (let i = 0; i < fromParts.length - 1; i++) {
      const idx = parseInt(fromParts[i])
      currentArray = currentArray[idx].nested_fields!
    }
    
    const fromIdx = parseInt(fromParts[fromParts.length - 1])
    const toIdx = parseInt(toParts[toParts.length - 1])
    
    // Remove from old position and insert at new position
    const [movedField] = currentArray.splice(fromIdx, 1)
    currentArray.splice(toIdx, 0, movedField)
    
    setFields(newFields)
  }

  const handleDragStart = (e: React.DragEvent, path: string) => {
    setDraggedPath(path)
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', path)
  }

  const handleDragEnd = () => {
    setDraggedPath(null)
    setDragOverPath(null)
  }

  const handleDragOver = (e: React.DragEvent, targetPath: string) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    if (draggedPath && draggedPath !== targetPath) {
      setDragOverPath(targetPath)
    }
  }

  const handleDrop = (e: React.DragEvent, targetPath: string) => {
    e.preventDefault()
    e.stopPropagation()

    if (draggedPath && draggedPath !== targetPath) {
      moveField(draggedPath, targetPath)
    }

    setDragOverPath(null)
  }

  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault()
  }

  const handleDragLeave = (e: React.DragEvent, targetPath: string) => {
    e.preventDefault()
    if (dragOverPath === targetPath) {
      setDragOverPath(null)
    }
  }

  const createMutation = useMutation({
    mutationFn: async () => {
      // Validation
      if (!name.trim()) throw new Error("Template name is required")
      if (fields.some(f => !f.name.trim())) throw new Error("All fields must have a name")

      const { data: { user } } = await supabase.auth.getUser()
      if (!user) throw new Error('Not authenticated')
      
      const { data: profile } = await supabase.from('profiles').select('tenant_id').eq('id', user.id).single()
      
      // Construct Schema JSON with nested fields
      const buildFieldSchema = (field: SchemaField): any => {
        const fieldSchema: any = {
          name: field.name,
          type: field.type,
          description: field.description,
          required: field.required || false
        }

        if ((field.type === 'object' || field.type === 'list[object]') && field.nested_fields && field.nested_fields.length > 0) {
          fieldSchema.nested_fields = field.nested_fields.map(buildFieldSchema)
        }

        return fieldSchema
      }
      
      const schemaContent = {
        document_type: "custom",
        description: description,
        fields: fields.map(buildFieldSchema)
      }

      // Update existing schema or create new one
      if (existingSchemaId) {
        const { data, error } = await supabase
          .from('schemas')
          .update({
            name: name,
            description: description,
            content: schemaContent
          })
          .eq('id', existingSchemaId)
          .select()
          .single()

        if (error) throw error
        return data
      } else {
        const { data, error } = await supabase.from('schemas').insert({
          tenant_id: profile?.tenant_id,
          name: name,
          description: description,
          content: schemaContent,
          is_public: false
        }).select().single()

        if (error) throw error
        return data
      }
    },
    onSuccess: (newSchema) => {
      queryClient.invalidateQueries({ queryKey: ['schemas'] })
      onSuccess(newSchema.id)
      clearDraft()
      onClose()
      // Reset form
      setName('')
      setDescription('')
      setFields([{ name: 'field_1', type: 'string', description: '', required: false, nested_fields: [] }])
      setExpandedFields(new Set())
    },
    onError: (err: any) => {
      alert(err.message)
    }
  })

  const renderFields = (fieldsList: SchemaField[], parentPath: string, level: number = 0): JSX.Element => {
    return (
      <div className="space-y-3">
        {fieldsList.map((field, index) => {
          const currentPath = parentPath ? `${parentPath}.${index}` : `${index}`
          const hasNested = field.type === 'object' || field.type === 'list[object]'
          const isExpanded = expandedFields.has(currentPath)
          const canRemove = level === 0 ? fields.length > 1 : true
          const isDragging = draggedPath === currentPath
          const isDraggedOver = dragOverPath === currentPath

          return (
            <div key={currentPath} className="space-y-2">
              <div
                className={`flex items-start gap-2 group bg-white p-4 rounded-lg border-2 transition-all cursor-move ${
                  isDragging
                    ? 'opacity-40 border-blue-400 shadow-lg scale-[0.98]'
                    : isDraggedOver
                    ? 'border-blue-500 bg-blue-50 shadow-md scale-[1.02]'
                    : 'border-gray-200 hover:border-blue-300 hover:shadow-sm'
                }`}
                style={{ marginLeft: `${level * 24}px` }}
                draggable
                onDragStart={(e) => handleDragStart(e, currentPath)}
                onDragEnd={handleDragEnd}
                onDragOver={(e) => handleDragOver(e, currentPath)}
                onDrop={(e) => handleDrop(e, currentPath)}
                onDragEnter={handleDragEnter}
                onDragLeave={(e) => handleDragLeave(e, currentPath)}
              >
                {/* Drag Handle */}
                <div className={`mt-6 p-1 rounded cursor-grab active:cursor-grabbing transition-colors ${
                  isDragging ? 'text-blue-600 bg-blue-100' : 'text-gray-400 hover:text-blue-600 hover:bg-blue-50'
                }`} title="Drag to reorder">
                  <GripVertical className="h-5 w-5" />
                </div>
                {/* Expand/Collapse button for nested types */}
                {hasNested ? (
                  <button
                    onClick={() => toggleExpanded(currentPath)}
                    className="mt-6 p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded transition-all"
                    title={isExpanded ? 'Collapse' : 'Expand'}
                  >
                    {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                  </button>
                ) : (
                  <div className="w-8" />
                )}

                <div className="flex-1 space-y-3">
                  <div className="grid grid-cols-12 gap-3">
                    {/* Field Name */}
                    <div className="col-span-4">
                      <label className="block text-xs font-medium text-gray-600 mb-1">Field Name</label>
                      <input
                        type="text"
                        className="w-full rounded-lg border border-gray-300 p-2.5 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-500 font-mono bg-gray-50 transition-all"
                        placeholder="field_name"
                        value={field.name}
                        onChange={(e) => updateField(currentPath, 'name', e.target.value)}
                      />
                    </div>
                    {/* Type */}
                    <div className="col-span-3">
                      <label className="block text-xs font-medium text-gray-600 mb-1">Type</label>
                      <select
                        className="w-full rounded-lg border border-gray-300 p-2.5 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-500 transition-all"
                        value={field.type}
                        onChange={(e) => updateField(currentPath, 'type', e.target.value as FieldType)}
                      >
                        <option value="string">Text</option>
                        <option value="number">Number</option>
                        <option value="date">Date</option>
                        <option value="boolean">Yes/No</option>
                        <option value="list[string]">List (Text)</option>
                        <option value="object">Object</option>
                        <option value="list[object]">List (Objects)</option>
                      </select>
                    </div>
                    {/* Description */}
                    <div className="col-span-5">
                      <label className="block text-xs font-medium text-gray-600 mb-1">Description</label>
                      <input
                        type="text"
                        className="w-full rounded-lg border border-gray-300 p-2.5 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-500 transition-all"
                        placeholder="e.g. Total amount at bottom"
                        value={field.description}
                        onChange={(e) => updateField(currentPath, 'description', e.target.value)}
                      />
                    </div>
                  </div>

                  {/* Required Checkbox */}
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id={`required-${currentPath}`}
                      checked={field.required || false}
                      onChange={(e) => updateField(currentPath, 'required', e.target.checked)}
                      className="w-4 h-4 text-blue-600 bg-gray-100 border-gray-300 rounded focus:ring-blue-500 focus:ring-2 cursor-pointer"
                    />
                    <label
                      htmlFor={`required-${currentPath}`}
                      className="text-sm text-gray-700 cursor-pointer select-none"
                    >
                      Required field
                    </label>
                  </div>
                </div>

                <button
                  onClick={() => removeField(currentPath)}
                  className="mt-6 p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg opacity-0 group-hover:opacity-100 transition-all"
                  disabled={!canRemove}
                  title="Remove field"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
              
              {/* Nested fields section */}
              {hasNested && isExpanded && (
                <div className="ml-6 pl-4 border-l-2 border-blue-200 space-y-2">
                  {field.nested_fields && field.nested_fields.length > 0 ? (
                    renderFields(field.nested_fields, currentPath, level + 1)
                  ) : (
                    <div className="text-sm text-gray-500 italic py-2">No nested fields yet</div>
                  )}
                  <button
                    onClick={() => addField(currentPath)}
                    className="flex items-center gap-2 px-3 py-2 text-xs font-medium text-blue-600 hover:text-blue-700 bg-blue-50 hover:bg-blue-100 border border-blue-200 rounded-lg transition-all"
                  >
                    <Plus className="h-3 w-3" />
                    Add nested field
                  </button>
                </div>
              )}
            </div>
          )
        })}
      </div>
    )
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-in fade-in">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-8 border-b border-gray-200 bg-gradient-to-r from-blue-50 to-cyan-50">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 rounded-xl">
              <Sparkles className="h-6 w-6 text-blue-600" />
            </div>
            <div>
              <h2 className="text-2xl font-bold text-gray-900">{existingSchemaId ? 'Edit' : 'Create'} Extraction Template</h2>
              <p className="text-sm text-gray-600 mt-1">{existingSchemaId ? 'Modify your template fields and settings' : 'Define what data you want to extract from your documents'}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {hasDraft && !initialData && !existingSchemaId && (
              <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                <Archive className="h-4 w-4 text-amber-600" />
                <span className="text-xs font-medium text-amber-700">Draft saved</span>
                <div className="flex gap-1">
                  <button
                    onClick={loadDraft}
                    className="text-xs font-medium text-amber-700 hover:text-amber-800 underline"
                  >
                    Restore
                  </button>
                  <span className="text-amber-400">•</span>
                  <button
                    onClick={clearDraft}
                    className="text-xs font-medium text-amber-700 hover:text-amber-800 underline"
                  >
                    Discard
                  </button>
                </div>
              </div>
            )}
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 hover:bg-white rounded-lg p-2 transition-all"
            >
              <X className="h-6 w-6" />
            </button>
          </div>
        </div>

        {/* Body (Scrollable) */}
        <div className="flex-1 overflow-y-auto p-8 space-y-6 custom-scrollbar">
          
          {/* Basic Info */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2">Template Name *</label>
              <input
                type="text"
                className="block w-full rounded-lg border border-gray-300 p-3 shadow-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-500 text-sm transition-all"
                placeholder="e.g. Vendor X Invoice"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2">Description (Optional)</label>
              <input
                type="text"
                className="block w-full rounded-lg border border-gray-300 p-3 shadow-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-500 text-sm transition-all"
                placeholder="e.g. For marketing expenses"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
          </div>

          {/* Field Editor */}
          <div className="bg-gray-50 rounded-xl p-6 border border-gray-200">
            <div className="flex items-center justify-between mb-5">
              <label className="block text-sm font-semibold text-gray-700">Data Fields *</label>
              <span className="text-xs text-gray-600 flex items-center gap-1.5 bg-blue-50 px-3 py-1.5 rounded-full">
                <HelpCircle className="h-3.5 w-3.5 text-blue-600" />
                AI uses descriptions to find values
              </span>
            </div>
            
            {renderFields(fields, '')}

            <button
              onClick={() => addField()}
              className="mt-4 flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-blue-600 hover:text-blue-700 bg-white hover:bg-blue-50 border border-blue-200 rounded-lg transition-all"
            >
              <Plus className="h-4 w-4" />
              Add field
            </button>
          </div>
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-gray-200 bg-gradient-to-r from-gray-50 to-white flex justify-between items-center rounded-b-2xl">
          <p className="text-xs text-gray-500">
            * Required fields
          </p>
          <div className="flex gap-3">
            <button
              onClick={onClose}
              className="px-5 py-2.5 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 hover:border-gray-400 transition-all"
            >
              Cancel
            </button>
            <button
              onClick={() => createMutation.mutate()}
              disabled={createMutation.isPending}
              className="flex items-center gap-2 px-6 py-2.5 text-sm font-semibold text-white bg-gradient-to-r from-blue-600 to-indigo-600 rounded-lg hover:from-blue-700 hover:to-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed shadow-sm hover:shadow-md transition-all"
            >
              <Save className="h-4 w-4" />
              {createMutation.isPending ? 'Saving...' : (existingSchemaId ? 'Update Template' : 'Save Template')}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
