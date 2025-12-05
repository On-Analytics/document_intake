import { CheckCircle, X, ArrowRight, Eye } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

interface SuccessModalProps {
  isOpen: boolean
  onClose: () => void
  filesCount: number
}

export default function SuccessModal({ isOpen, onClose, filesCount }: SuccessModalProps) {
  const navigate = useNavigate()

  if (!isOpen) return null

  const handleViewResults = () => {
    onClose()
    navigate('/history')
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm animate-in fade-in">
      <div className="relative w-full max-w-md bg-white rounded-2xl shadow-2xl animate-in zoom-in-95 duration-300">
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

          <h2 className="text-3xl font-bold text-gray-900 mb-3">Success!</h2>
          <p className="text-gray-600 mb-8">
            Successfully processed {filesCount} {filesCount === 1 ? 'file' : 'files'}.
            Your extracted data is ready to view.
          </p>

          <div className="space-y-3">
            <button
              onClick={handleViewResults}
              className="w-full flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-green-500 to-emerald-500 px-6 py-3.5 text-base font-semibold text-white shadow-lg hover:shadow-xl hover:scale-[1.02] transition-all"
            >
              <Eye className="h-5 w-5" />
              View Results
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

        <div className="border-t border-gray-100 bg-gray-50 px-8 py-4 rounded-b-2xl">
          <div className="flex items-center justify-center gap-6 text-sm text-gray-600">
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-green-500"></div>
              <span>Data Extracted</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-blue-500"></div>
              <span>Saved Securely</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
