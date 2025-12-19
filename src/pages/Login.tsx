import { useState, useEffect, useRef } from 'react'
import { supabase } from '../lib/supabase'
import { useNavigate } from 'react-router-dom'
import { FileText, Sparkles, Lock, Eye, EyeOff, Loader2, Mail } from 'lucide-react'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isSignUp, setIsSignUp] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [showForgotPassword, setShowForgotPassword] = useState(false)
  const emailInputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()

  useEffect(() => {
    emailInputRef.current?.focus()
  }, [])

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

    if (password.length < 8) {
      setError('Password must be at least 8 characters long')
      setLoading(false)
      return
    }

    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: {
          full_name: email.split('@')[0]
        }
      }
    })

    if (error) {
      setError(error.message)
    } else if (data.session) {
      navigate('/')
    } else {
      setError("Account created! Please check your email to confirm your account before logging in.")
    }
    setLoading(false)
  }

  const handleForgotPassword = async () => {
    if (!email) {
      setError('Please enter your email address')
      return
    }

    setLoading(true)
    setError(null)

    const { error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/reset-password`,
    })

    if (error) {
      setError(error.message)
    } else {
      setError('Password reset email sent! Check your inbox.')
    }

    setLoading(false)
    setShowForgotPassword(false)
  }

  const handleModeSwitch = () => {
    setIsSignUp(!isSignUp)
    setError(null)
    setEmail('')
    setPassword('')
    setShowPassword(false)
    setShowForgotPassword(false)
    emailInputRef.current?.focus()
  }

  const getPasswordStrength = (pass: string) => {
    if (pass.length === 0) return { strength: 0, label: '', color: '' }
    if (pass.length < 8) return { strength: 1, label: 'Too short', color: 'bg-red-500' }

    let strength = 1
    if (pass.length >= 8) strength++
    if (pass.length >= 12) strength++
    if (/[a-z]/.test(pass) && /[A-Z]/.test(pass)) strength++
    if (/[0-9]/.test(pass)) strength++
    if (/[^a-zA-Z0-9]/.test(pass)) strength++

    if (strength <= 2) return { strength: 25, label: 'Weak', color: 'bg-red-500' }
    if (strength <= 4) return { strength: 50, label: 'Fair', color: 'bg-yellow-500' }
    if (strength <= 5) return { strength: 75, label: 'Good', color: 'bg-blue-500' }
    return { strength: 100, label: 'Strong', color: 'bg-green-500' }
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
            Powered by AI to extract data from your documents with precision
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
        <div className="w-full max-w-md space-y-8">
          <div className="bg-white rounded-2xl shadow-xl p-8 sm:p-12 border border-gray-100">
            {/* Mobile Logo */}
            <div className="lg:hidden flex items-center justify-center gap-2 mb-10">
              <div className="p-2 bg-primary/10 rounded-lg">
                <FileText className="h-6 w-6 text-primary" />
              </div>
              <h1 className="text-2xl font-bold text-gray-900">On-Documents</h1>
            </div>

            <div className="text-center mb-10">
              <h2 className="text-2xl font-bold text-gray-900">
                {isSignUp ? 'Create your account' : 'Welcome back'}
              </h2>
              <p className="mt-2 text-sm text-gray-600">
                {isSignUp ? 'Sign up to get started with On-Documents' : 'Sign in to continue to your workspace'}
              </p>
            </div>
            
            {error && (
              <div className="mb-6 rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-700 animate-in fade-in">
                {error}
              </div>
            )}

            <form className="space-y-6" onSubmit={handleLogin}>
              <div>
                <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-2">
                  Email address
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <Mail className="h-5 w-5 text-gray-400" />
                  </div>
                  <input
                    ref={emailInputRef}
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
                <div className="flex items-center justify-between mb-2">
                  <label htmlFor="password" className="block text-sm font-medium text-gray-700">
                    Password
                  </label>
                  {!isSignUp && !showForgotPassword && (
                    <button
                      type="button"
                      onClick={() => setShowForgotPassword(true)}
                      className="text-xs font-medium text-primary hover:text-primary-600 transition-colors"
                    >
                      Forgot password?
                    </button>
                  )}
                </div>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <Lock className="h-5 w-5 text-gray-400" />
                  </div>
                  <input
                    id="password"
                    type={showPassword ? 'text' : 'password'}
                    required
                    minLength={isSignUp ? 8 : undefined}
                    className="block w-full pl-10 pr-10 py-3 border border-gray-300 rounded-lg text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute inset-y-0 right-0 pr-3 flex items-center hover:text-gray-600 transition-colors"
                  >
                    {showPassword ? (
                      <EyeOff className="h-5 w-5 text-gray-400" />
                    ) : (
                      <Eye className="h-5 w-5 text-gray-400" />
                    )}
                  </button>
                </div>
                {isSignUp && password.length > 0 && (
                  <div className="mt-2">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs text-gray-600">Password strength</span>
                      <span className={`text-xs font-medium ${
                        getPasswordStrength(password).label === 'Strong' ? 'text-green-600' :
                        getPasswordStrength(password).label === 'Good' ? 'text-blue-600' :
                        getPasswordStrength(password).label === 'Fair' ? 'text-yellow-600' :
                        'text-red-600'
                      }`}>
                        {getPasswordStrength(password).label}
                      </span>
                    </div>
                    <div className="w-full bg-gray-200 rounded-full h-1.5">
                      <div
                        className={`h-1.5 rounded-full transition-all ${getPasswordStrength(password).color}`}
                        style={{ width: `${getPasswordStrength(password).strength}%` }}
                      />
                    </div>
                  </div>
                )}
                {isSignUp && (
                  <p className="mt-2 text-xs text-gray-500">
                    Must be at least 8 characters long. Use uppercase, lowercase, numbers, and symbols for a stronger password.
                  </p>
                )}
              </div>

              {showForgotPassword && (
                <div className="rounded-lg bg-blue-50 border border-blue-200 p-4">
                  <p className="text-sm text-blue-700 mb-3">
                    Enter your email address and we'll send you a link to reset your password.
                  </p>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={handleForgotPassword}
                      disabled={loading}
                      className="flex-1 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-dark hover:bg-primary-600 focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50 transition-all"
                    >
                      {loading ? 'Sending...' : 'Send reset link'}
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowForgotPassword(false)}
                      className="px-4 py-2 text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              {!showForgotPassword && (
                <div className="pt-4">
                  {isSignUp ? (
                    <button
                      type="button"
                      onClick={handleSignUp}
                      disabled={loading}
                      className="w-full flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-3.5 text-sm font-semibold text-dark shadow-md hover:bg-primary-600 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                    >
                      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
                      {loading ? 'Creating account...' : 'Create account'}
                    </button>
                  ) : (
                    <button
                      type="submit"
                      disabled={loading}
                      className="w-full flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-3.5 text-sm font-semibold text-dark shadow-md hover:bg-primary-600 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                    >
                      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
                      {loading ? 'Signing in...' : 'Sign in'}
                    </button>
                  )}
                </div>
              )}
            </form>

            <div className="mt-8 text-center">
              <button
                type="button"
                onClick={handleModeSwitch}
                className="text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors"
              >
                {isSignUp ? (
                  <>
                    Already have an account? <span className="text-primary">Sign in</span>
                  </>
                ) : (
                  <>
                    Don't have an account? <span className="text-primary">Sign up</span>
                  </>
                )}
              </button>
            </div>

            <div className="mt-8 text-center text-xs text-gray-500">
              By continuing, you agree to our{' '}
              <a
                href="/terms_of_service.pdf"
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:text-primary-600 underline transition-colors"
              >
                Terms of Service
              </a>
              {' '}and{' '}
              <a
                href="/privacy_policy.pdf"
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:text-primary-600 underline transition-colors"
              >
                Privacy Policy
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
