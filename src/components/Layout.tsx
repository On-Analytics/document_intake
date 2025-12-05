import { useState } from 'react'
import { Outlet, Link, useLocation, Navigate } from 'react-router-dom'
import {
  Sparkles,
  FileText,
  LogOut,
  Menu,
  X,
  FolderOpen,
  LayoutDashboard
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

const navigation = [
  { name: 'Overview', href: '/overview', icon: LayoutDashboard },
  { name: 'Extract', href: '/', icon: Sparkles },
  { name: 'Templates', href: '/schemas', icon: FileText },
  { name: 'Results', href: '/history', icon: FolderOpen },
]

function classNames(...classes: string[]) {
  return classes.filter(Boolean).join(' ')
}

export default function Layout() {
  const { user, loading, signOut } = useAuth()
  const location = useLocation()
  const [sidebarOpen, setSidebarOpen] = useState(false)

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-gray-50">
        <div className="flex flex-col items-center gap-4">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-gray-200 border-t-blue-600"></div>
          <p className="text-sm text-gray-600">Loading...</p>
        </div>
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Mobile Header */}
      <div className="lg:hidden sticky top-0 z-40 flex items-center justify-between bg-white px-4 py-3 shadow-sm border-b border-gray-200">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-primary/10 rounded-lg">
            <FileText className="h-5 w-5 text-primary" />
          </div>
          <span className="font-bold text-lg text-gray-900">On-Documents</span>
        </div>
        <button 
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="p-2 rounded-lg hover:bg-gray-100 transition-colors"
        >
          {sidebarOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
        </button>
      </div>

      {/* Mobile Sidebar Overlay */}
      {sidebarOpen && (
        <div 
          className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <div className={classNames(
        "fixed inset-y-0 left-0 z-50 w-72 transform bg-white shadow-xl transition-transform duration-300 ease-in-out lg:translate-x-0 lg:static lg:inset-auto lg:flex lg:flex-col border-r border-gray-200",
        sidebarOpen ? "translate-x-0" : "-translate-x-full"
      )}>
        {/* Logo */}
        <div className="flex h-16 shrink-0 items-center px-6 border-b border-gray-200">
          <div className="flex items-center gap-2">
            <div className="p-2 bg-primary rounded-xl shadow-sm">
              <FileText className="h-5 w-5 text-dark" />
            </div>
            <h1 className="text-xl font-bold text-dark">
              On-Documents
            </h1>
          </div>
        </div>
        
        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto px-3 py-6 space-y-1 custom-scrollbar">
          <div className="px-3 mb-2">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
              Main Menu
            </p>
          </div>
          {navigation.map((item) => {
            const isActive = location.pathname === item.href
            return (
              <Link
                key={item.name}
                to={item.href}
                onClick={() => setSidebarOpen(false)}
                className={classNames(
                  'text-gray-700 hover:bg-gray-100',
                  isActive
                    ? 'bg-primary/10 text-primary font-semibold border-l-4 border-primary'
                    : 'hover:bg-gray-50',
                  'group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all'
                )}
              >
                <item.icon className={classNames(
                  isActive ? 'text-blue-600' : 'text-gray-400 group-hover:text-blue-600',
                  'h-5 w-5 shrink-0'
                )} aria-hidden="true" />
                {item.name}
                {isActive && (
                  <div className="ml-auto h-1.5 w-1.5 rounded-full bg-blue-600" />
                )}
              </Link>
            )
          })}
        </nav>

        {/* User Section */}
        <div className="border-t border-gray-200 p-4 bg-gray-50">
          <div className="flex items-center gap-3 mb-3 px-2">
            <div className="h-10 w-10 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white font-bold shadow-sm">
              {user.email?.[0].toUpperCase()}
            </div>
            <div className="flex-1 overflow-hidden">
              <p className="text-xs text-gray-500 mb-0.5">Signed in as</p>
              <p className="truncate text-sm font-medium text-gray-900">{user.email}</p>
            </div>
          </div>
          <button
            onClick={() => signOut()}
            className="flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2.5 text-sm font-medium text-gray-700 bg-white border border-gray-200 hover:bg-red-50 hover:text-red-600 hover:border-red-200 transition-all shadow-sm"
          >
            <LogOut className="h-4 w-4" />
            Sign out
          </button>
        </div>
      </div>

      {/* Main Content */}
      <main className="lg:pl-72 min-h-screen bg-gradient-to-br from-gray-50 via-gray-50 to-blue-50/30">
        <Outlet />
      </main>
    </div>
  )
}
