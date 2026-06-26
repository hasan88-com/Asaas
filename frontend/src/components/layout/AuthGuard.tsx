import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'

export function AuthGuard() {
  const { user, loading } = useAuth()

  // While Supabase session is resolving, render the outlet so protected pages
  // can show their own skeletons immediately. This eliminates the two-phase blink
  // (spinner → skeleton) by collapsing both loading states into one visual.
  // When auth settles with no user, the Navigate below redirects to login.
  if (!loading && !user) return <Navigate to="/login" replace />

  return <Outlet />
}
