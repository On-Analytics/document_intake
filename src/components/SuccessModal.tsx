import { CheckCircle, X, ArrowRight, Eye, FileCheck } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

interface ProcessedFile {
  filename: string
  fieldCount: number
  status: 'completed' | 'failed'
}

interface SuccessModalProps {
  isOpen: boolean
  onClose: () => void
  filesCount: number
  processedFiles?: ProcessedFile[]
}

export default function SuccessModal({ isOpen, onClose, filesCount, processedFiles = [] }: SuccessModalProps) {
  const navigate = useNavigate()

  if (!isOpen) return null

  const handleViewResults = () => {
    onClose()
    navigate('/history')
  }

  const showFileList = processedFiles.length > 0 && processedFiles.length <= 5

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm animate-in fade-in">
      <div className="relative w-full max-w-lg bg-white rounded-2xl shadow-2xl animate-in zoom-in-95 duration-300">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-all"
        >
          <X className="h-5 w-5" />
        </button>

        <div className="p-8 text-center">
          <div className="mb-6 relative inline-flex">
            <div className="absolute inset-0 bg-green-400/30 rounded-full blur-2xl animate-pulse"></div>
            <div className="relative bg-gradient-to-br from-green-400 to-emerald-500 p-4 rounded-full shadow-lg">
              <CheckCircle className="h-16 w-16 text-white animate-in zoom-in-50 duration-500" />
            </div>
          </div>

          <h2 className="text-3xl font-bold text-gray-900 mb-3">Extraction Complete!</h2>
          <p className="text-gray-600 mb-6">
            Successfully processed {filesCount} {filesCount === 1 ? 'document' : 'documents'}
          </p>

          {showFileList && (
            <div className="mb-6 text-left bg-gray-50 rounded-xl p-4 space-y-2 max-h-64 overflow-y-auto">
              {processedFiles.map((file, idx) => (
                <div key={idx} className="flex items-center justify-between p-3 bg-white rounded-lg border border-gray-200">
                  <div className="flex items-center gap-3 flex-1 min-w-0">
                    <FileCheck className="h-5 w-5 text-green-600 shrink-0" />
                    <span className="font-medium text-gray-900 text-sm truncate">
                      {file.filename}
                    </span>
                  </div>
                  <span className="text-xs font-medium text-gray-600 bg-gray-100 px-2 py-1 rounded-full shrink-0">
                    {file.fieldCount} fields
                  </span>
                </div>
              ))}
            </div>
          )}

          <div className="space-y-3">
            <button
              onClick={handleViewResults}
              className="w-full flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-green-500 to-emerald-500 px-6 py-3.5 text-base font-semibold text-white shadow-lg hover:shadow-xl hover:scale-[1.02] transition-all"
            >
              <Eye className="h-5 w-5" />
              View All Results
              <ArrowRight className="h-5 w-5" />
            </button>

            <button
              onClick={onClose}
              className="w-full rounded-xl bg-gray-100 px-6 py-3 text-base font-medium text-gray-700 hover:bg-gray-200 transition-all"
            >
              Process More Files
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
