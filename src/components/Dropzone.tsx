import { useState, useCallback } from 'react'
import { UploadCloud, FileText, X, CheckCircle } from 'lucide-react'

interface DropzoneProps {
  onFilesSelect: (files: File[]) => void
  selectedFiles: File[]
}

export default function Dropzone({ onFilesSelect, selectedFiles }: DropzoneProps) {
  const [isDragging, setIsDragging] = useState(false)

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setIsDragging(true)
    } else if (e.type === 'dragleave') {
      setIsDragging(false)
    }
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const newFiles = Array.from(e.dataTransfer.files)
      onFilesSelect([...selectedFiles, ...newFiles])
    }
  }, [onFilesSelect, selectedFiles])

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const newFiles = Array.from(e.target.files)
      onFilesSelect([...selectedFiles, ...newFiles])
    }
    // Reset input so same file can be selected again
    e.target.value = ''
  }

  const removeFile = (index: number) => {
    const newFiles = selectedFiles.filter((_, i) => i !== index)
    onFilesSelect(newFiles)
  }

  if (selectedFiles.length > 0) {
    return (
      <div className="space-y-3">
        {selectedFiles.map((file, index) => (
          <div key={`${file.name}-${index}`} className="flex items-center justify-between p-4 bg-gradient-to-r from-blue-50 to-indigo-50 border-2 border-blue-200 rounded-xl shadow-sm animate-in fade-in">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-white rounded-lg shadow-sm">
                <FileText className="h-6 w-6 text-blue-600" />
              </div>
              <div>
                <div className="flex items-center gap-2 mb-0.5">
                  <p className="font-semibold text-gray-900 text-sm">{file.name}</p>
                  <CheckCircle className="h-3.5 w-3.5 text-green-600" />
                </div>
                <p className="text-xs text-gray-600">
                  {(file.size / 1024).toFixed(1)} KB
                </p>
              </div>
            </div>
            <button
              onClick={() => removeFile(index)}
              className="p-1.5 hover:bg-white rounded-lg text-gray-500 hover:text-red-600 transition-all"
              title="Remove file"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        ))}
        <div className="text-center py-2 text-sm text-gray-600">
          {selectedFiles.length} file{selectedFiles.length > 1 ? 's' : ''} ready • Click or drag to add more
        </div>
      </div>
    )
  }

  return (
    <div
      onDragEnter={handleDrag}
      onDragLeave={handleDrag}
      onDragOver={handleDrag}
      onDrop={handleDrop}
      className={`
        relative flex flex-col items-center justify-center w-full h-64 
        rounded-xl border-2 border-dashed transition-all duration-300 cursor-pointer
        ${isDragging 
          ? 'border-blue-500 bg-blue-50 scale-[1.02]' 
          : 'border-gray-300 bg-gray-50 hover:bg-white hover:border-blue-400 hover:shadow-sm'
        }
      `}
    >
      <input
        type="file"
        multiple
        className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
        onChange={handleFileInput}
        accept=".pdf,.png,.jpg,.jpeg"
      />
      <div className="flex flex-col items-center text-center p-6 pointer-events-none">
        <div className={`p-4 rounded-2xl mb-4 transition-all ${isDragging ? 'bg-blue-200 scale-110' : 'bg-blue-100'}`}>
          <UploadCloud className={`h-10 w-10 text-blue-600 transition-transform ${isDragging ? 'scale-110' : ''}`} />
        </div>
        <p className="text-lg font-semibold text-gray-900 mb-1">
          {isDragging ? 'Drop your files here' : 'Click to upload or drag and drop'}
        </p>
        <p className="text-sm text-gray-600 mt-1">
          PDF, PNG, JPG, JPEG (Max 10MB each) • Multiple files supported
        </p>
        <div className="mt-4 flex items-center gap-2 text-xs text-gray-500">
          <div className="h-1 w-1 rounded-full bg-gray-400"></div>
          <span>Secure upload</span>
          <div className="h-1 w-1 rounded-full bg-gray-400"></div>
          <span>AI-powered processing</span>
        </div>
      </div>
    </div>
  )
}
