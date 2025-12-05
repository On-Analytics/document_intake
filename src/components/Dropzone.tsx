import { useState, useCallback } from 'react'
import { UploadCloud, FileText, X, CheckCircle, Image, FileImage } from 'lucide-react'

interface DropzoneProps {
  onFilesSelect: (files: File[]) => void
  selectedFiles: File[]
}

export default function Dropzone({ onFilesSelect, selectedFiles }: DropzoneProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [pulseAnimation, setPulseAnimation] = useState(false)

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
      setPulseAnimation(true)
      setTimeout(() => setPulseAnimation(false), 600)
    }
  }, [onFilesSelect, selectedFiles])

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const newFiles = Array.from(e.target.files)
      onFilesSelect([...selectedFiles, ...newFiles])
      setPulseAnimation(true)
      setTimeout(() => setPulseAnimation(false), 600)
    }
    // Reset input so same file can be selected again
    e.target.value = ''
  }

  const removeFile = (index: number) => {
    const newFiles = selectedFiles.filter((_, i) => i !== index)
    onFilesSelect(newFiles)
  }

  const getFileIcon = (fileName: string) => {
    const ext = fileName.split('.').pop()?.toLowerCase()
    if (ext === 'pdf') return <FileText className="h-6 w-6 text-red-600" />
    if (['png', 'jpg', 'jpeg'].includes(ext || '')) return <FileImage className="h-6 w-6 text-green-600" />
    return <FileText className="h-6 w-6 text-blue-600" />
  }

  if (selectedFiles.length > 0) {
    return (
      <div className="space-y-3">
        {selectedFiles.map((file, index) => (
          <div
            key={`${file.name}-${index}`}
            className={`flex items-center justify-between p-4 bg-gradient-to-r from-green-50 to-emerald-50 border-2 border-green-300 rounded-xl shadow-sm ${pulseAnimation ? 'animate-pulse' : 'animate-in fade-in slide-in-from-top-2'}`}
          >
            <div className="flex items-center gap-3">
              <div className="p-2 bg-white rounded-lg shadow-sm">
                {getFileIcon(file.name)}
              </div>
              <div>
                <div className="flex items-center gap-2 mb-0.5">
                  <p className="font-semibold text-gray-900 text-sm">{file.name}</p>
                  <CheckCircle className="h-4 w-4 text-green-600" />
                </div>
                <p className="text-xs text-gray-600">
                  {(file.size / 1024 / 1024).toFixed(2)} MB
                </p>
              </div>
            </div>
            <button
              onClick={() => removeFile(index)}
              className="p-1.5 hover:bg-white rounded-lg text-gray-500 hover:text-red-600 transition-all"
              title="Remove file"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        ))}
        <label className="block cursor-pointer">
          <input
            type="file"
            multiple
            className="hidden"
            onChange={handleFileInput}
            accept=".pdf,.png,.jpg,.jpeg"
          />
          <div className="text-center py-4 border-2 border-dashed border-gray-300 rounded-xl bg-gray-50 hover:bg-white hover:border-green-400 transition-all">
            <p className="text-sm font-medium text-gray-700">
              + Add more files
            </p>
            <p className="text-xs text-gray-500 mt-1">
              {selectedFiles.length} file{selectedFiles.length > 1 ? 's' : ''} ready to process
            </p>
          </div>
        </label>
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
        relative flex flex-col items-center justify-center w-full min-h-[320px]
        rounded-2xl border-3 border-dashed transition-all duration-300 cursor-pointer overflow-hidden
        ${isDragging
          ? 'border-green-500 bg-gradient-to-br from-green-50 via-emerald-50 to-teal-50 scale-[1.01] shadow-2xl'
          : 'border-gray-300 bg-gradient-to-br from-gray-50 via-white to-gray-50 hover:border-green-400 hover:shadow-lg hover:scale-[1.005]'
        }
      `}
    >
      <input
        type="file"
        multiple
        className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
        onChange={handleFileInput}
        accept=".pdf,.png,.jpg,.jpeg"
      />

      <div className="flex flex-col items-center text-center p-8 pointer-events-none relative z-0">
        <div className={`relative mb-6 transition-all duration-300 ${isDragging ? 'scale-110' : 'scale-100'}`}>
          <div className={`absolute inset-0 rounded-full blur-xl transition-all ${isDragging ? 'bg-green-400/50 scale-150' : 'bg-blue-300/30'}`}></div>
          <div className={`relative p-6 rounded-3xl transition-all ${isDragging ? 'bg-gradient-to-br from-green-400 to-emerald-500 shadow-xl' : 'bg-gradient-to-br from-blue-400 to-blue-600 shadow-lg'}`}>
            <UploadCloud className={`h-16 w-16 text-white transition-transform ${isDragging ? 'animate-bounce' : ''}`} />
          </div>
        </div>

        <p className="text-2xl font-bold text-gray-900 mb-2">
          {isDragging ? 'Drop your files here!' : 'Drag & Drop Files'}
        </p>
        <p className="text-base text-gray-600 mb-1">
          or click to browse
        </p>
        <p className="text-sm text-gray-500 mt-3 mb-6">
          PDF, PNG, JPG, JPEG • Max 10MB per file • Multiple files supported
        </p>

        <div className="flex items-center gap-6 mt-2">
          <div className="flex flex-col items-center gap-2">
            <div className="p-3 bg-blue-100 rounded-xl">
              <FileText className="h-6 w-6 text-blue-600" />
            </div>
            <span className="text-xs font-medium text-gray-600">Documents</span>
          </div>
          <div className="flex flex-col items-center gap-2">
            <div className="p-3 bg-green-100 rounded-xl">
              <Image className="h-6 w-6 text-green-600" />
            </div>
            <span className="text-xs font-medium text-gray-600">Images</span>
          </div>
        </div>

        <div className="mt-8 flex items-center gap-3 text-xs text-gray-500 bg-white/50 px-4 py-2 rounded-full">
          <div className="h-1.5 w-1.5 rounded-full bg-green-500 animate-pulse"></div>
          <span>Secure & Encrypted</span>
          <div className="h-1 w-1 rounded-full bg-gray-400"></div>
          <span>AI-Powered</span>
          <div className="h-1 w-1 rounded-full bg-gray-400"></div>
          <span>Lightning Fast</span>
        </div>
      </div>
    </div>
  )
}
