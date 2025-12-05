import { useState } from 'react'
import { supabase } from '../lib/supabase'
import { useNavigate } from 'react-router-dom'
import { FileText, Sparkles, Lock, Mail, CheckCircle } from 'lucide-react'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)

    const { error } = await supabase.auth.signInWithPassword({
      email,
      password,
    })

    if (error) {
      setError(error.message)
      setLoading(false)
    } else {
      // Success - redirect to dashboard
      navigate('/')
    }
  }

  const handleSignUp = async () => {
    setLoading(true)
    setError(null)
    
    // Simple signup flow
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: {
          full_name: email.split('@')[0] // Use part of email as default name
        }
      }
    })

    if (error) {
      setError(error.message)
    } else if (data.session) {
      // If email confirmation is disabled, we get a session immediately
      navigate('/')
    } else {
      setError("Account created! Please check your email to confirm your account before logging in.")
    }
    setLoading(false)
  }

  return (
    <div className="flex min-h-screen">
      {/* Left Side - Branding */}
      <div className="hidden lg:flex lg:flex-1 bg-gradient-to-br from-dark via-dark-600 to-dark-700 relative overflow-hidden">
        <div className="absolute inset-0 bg-grid-white/[0.05] bg-[size:20px_20px]" />
        <div className="relative z-10 flex flex-col justify-center px-12 text-white">
          <div className="flex items-center gap-3 mb-8">
            <div className="p-3 bg-white/10 backdrop-blur-sm rounded-xl">
              <FileText className="h-8 w-8" />
            </div>
            <h1 className="text-4xl font-bold">On-Documents</h1>
          </div>
          <h2 className="text-3xl font-semibold mb-4 leading-tight">
            Transform documents into<br />structured data instantly
          </h2>
          <p className="text-gray-300 text-lg max-w-md leading-relaxed">
            Powered by AI to extract, analyze, and organize information from any document with precision and speed.
          </p>
          <div className="mt-12 space-y-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-white/10 rounded-lg">
                <Sparkles className="h-5 w-5" />
              </div>
              <span className="text-blue-50">AI-powered extraction</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="p-2 bg-white/10 rounded-lg">
                <FileText className="h-5 w-5" />
              </div>
              <span className="text-blue-50">Custom templates</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="p-2 bg-white/10 rounded-lg">
                <Lock className="h-5 w-5" />
              </div>
              <span className="text-blue-50">Secure & compliant</span>
            </div>
          </div>
        </div>
      </div>

      {/* Right Side - Login Form */}
      <div className="flex-1 flex items-center justify-center px-4 sm:px-6 lg:px-8 bg-gray-50">
        <div className="w-full max-w-md">
          <div className="bg-white rounded-2xl shadow-xl p-8 sm:p-10 border border-gray-100">
            {/* Mobile Logo */}
            <div className="lg:hidden flex items-center justify-center gap-2 mb-8">
              <div className="p-2 bg-primary/10 rounded-lg">
                <FileText className="h-6 w-6 text-primary" />
              </div>
              <h1 className="text-2xl font-bold text-gray-900">On-Documents</h1>
            </div>

            <div className="text-center mb-8">
              <h2 className="text-2xl font-bold text-gray-900">
                Welcome back
              </h2>
              <p className="mt-2 text-sm text-gray-600">
                Sign in to continue to your workspace
              </p>
            </div>
            
            {error && (
              <div className="mb-6 rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-700 animate-in fade-in">
                {error}
              </div>
            )}

            <form className="space-y-5" onSubmit={handleLogin}>
              <div>
                <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-2">
                  Email address
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <CheckCircle className="h-5 w-5 text-primary" />
                  </div>
                  <input
                    id="email"
                    type="email"
                    required
                    className="block w-full pl-10 pr-3 py-3 border border-gray-300 rounded-lg text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
                    placeholder="you@company.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </div>
              </div>

              <div>
                <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-2">
                  Password
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <Lock className="h-5 w-5 text-gray-400" />
                  </div>
                  <input
                    id="password"
                    type="password"
                    required
                    className="block w-full pl-10 pr-3 py-3 border border-gray-300 rounded-lg text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </div>
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  type="submit"
                  disabled={loading}
                  className="w-full rounded-lg bg-primary px-4 py-3 text-sm font-semibold text-dark shadow-md hover:bg-primary-600 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                >
                  {loading ? 'Signing in...' : 'Sign in'}
                </button>
                
                <button
                  type="button"
                  onClick={handleSignUp}
                  disabled={loading}
                  className="flex-1 flex justify-center items-center px-4 py-3 rounded-lg text-sm font-semibold text-gray-700 bg-white border border-gray-300 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                >
                  Sign up
                </button>
              </div>
            </form>

            <div className="mt-6 text-center text-xs text-gray-500">
              By continuing, you agree to our Terms of Service and Privacy Policy
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
