import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'

export function GuestGuard() {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-paper">
        <span className="w-3 h-3 rounded-full bg-jade animate-dot-pulse" aria-label="Loading…" />
      </div>
    )
  }

  if (user) return <Navigate to="/dashboard" replace />

  return <Outlet />
}
