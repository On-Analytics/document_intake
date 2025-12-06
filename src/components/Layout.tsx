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
      <div className="flex h-screen items-center justify-center bg-white">
        <div className="flex flex-col items-center gap-4">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-gray-100 border-t-primary"></div>
          <p className="text-sm text-gray-500">Loading...</p>
        </div>
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return (
    <div className="min-h-screen bg-white">
      {/* Mobile Header */}
      <div className="lg:hidden sticky top-0 z-40 flex items-center justify-between bg-white px-6 py-4 border-b border-gray-200">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-lg bg-primary flex items-center justify-center">
            <FileText className="h-5 w-5 text-dark" />
          </div>
          <span className="font-bold text-lg text-dark">On-Documents</span>
        </div>
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="p-2 rounded-lg hover:bg-gray-50 transition-colors"
        >
          {sidebarOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
        </button>
      </div>

      {/* Mobile Sidebar Overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/20 backdrop-blur-sm lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <div className={classNames(
        "fixed inset-y-0 left-0 z-50 w-64 transform bg-white transition-transform duration-300 ease-in-out lg:translate-x-0 flex flex-col border-r border-gray-200",
        sidebarOpen ? "translate-x-0" : "-translate-x-full"
      )}>
        {/* Logo */}
        <div className="flex h-14 shrink-0 items-center px-5 border-b border-gray-200">
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-lg bg-primary flex items-center justify-center">
              <FileText className="h-4 w-4 text-dark" />
            </div>
            <h1 className="text-base font-bold text-dark">
              On-Documents
            </h1>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1 custom-scrollbar">
          {navigation.map((item) => {
            const isActive = location.pathname === item.href
            return (
              <Link
                key={item.name}
                to={item.href}
                onClick={() => setSidebarOpen(false)}
                className={classNames(
                  isActive
                    ? 'bg-primary/10 text-primary font-medium'
                    : 'text-gray-600 hover:bg-gray-50',
                  'group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-all'
                )}
              >
                <item.icon className={classNames(
                  isActive ? 'text-primary' : 'text-gray-400 group-hover:text-primary',
                  'h-4 w-4 shrink-0'
                )} aria-hidden="true" />
                {item.name}
              </Link>
            )
          })}
        </nav>

        {/* User Section */}
        <div className="border-t border-gray-200 p-3">
          <div className="flex items-center gap-2 mb-2 px-2">
            <div className="h-8 w-8 rounded-full bg-primary flex items-center justify-center text-dark text-sm font-semibold">
              {user.email?.[0].toUpperCase()}
            </div>
            <div className="flex-1 overflow-hidden">
              <p className="truncate text-xs font-medium text-gray-900">{user.email}</p>
            </div>
          </div>
          <button
            onClick={() => signOut()}
            className="flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs font-medium text-gray-700 bg-white border border-gray-200 hover:bg-gray-50 transition-all"
          >
            <LogOut className="h-3.5 w-3.5" />
            Sign out
          </button>
        </div>
      </div>

      {/* Main Content */}
      <main className="lg:pl-64 min-h-screen bg-gray-50">
        <Outlet />
      </main>
    </div>
  )
}
