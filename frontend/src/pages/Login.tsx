import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { supabase } from '@/lib/supabase'
import { useAuth } from '@/context/AuthContext'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export default function Login() {
  const navigate = useNavigate()
  const { user, loading: authLoading } = useAuth()

  // Redirect already-authenticated users to dashboard
  useEffect(() => {
    if (!authLoading && user) {
      navigate('/dashboard', { replace: true })
    }
  }, [authLoading, user, navigate])
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const { error: authErr } = await supabase.auth.signInWithPassword({ email, password })
      if (authErr) throw authErr
      // onAuthStateChange fires → syncSession sets user → GuestGuard redirects
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-paper flex">
      <div className="hidden lg:flex lg:w-1/2 bg-jade flex-col items-center justify-center p-12 text-center">
        <div className="flex flex-col items-center gap-4 max-w-sm">
          <img src="/logo.png" alt="Asaasa" className="h-20 w-auto" />
          <span className="font-display text-[36px] font-semibold text-white leading-[1.05]">اثاثہ</span>
          <div className="flex items-center gap-2">
            <span className="h-px w-8 bg-white/30" />
            <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-white/70 font-semibold">Asaasa</span>
            <span className="h-px w-8 bg-white/30" />
          </div>
          <p className="font-sans text-[16px] leading-[1.5] text-white/80 mt-2">
            Pakistan-focused agentic wealth management
          </p>
        </div>
      </div>

      <div className="flex-1 flex flex-col items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          <div className="flex items-center justify-center gap-2 mb-8 lg:hidden">
            <img src="/logo.png" alt="Asaasa" className="h-10 w-auto" />
            <span className="font-display text-[24px] font-semibold text-ink">اثاثہ</span>
          </div>

          <div className="bg-card border border-line rounded-[14px] shadow-sm p-6">
            <h1 className="font-display text-[24px] font-semibold text-ink mb-1">Welcome back</h1>
            <p className="font-sans text-[14px] text-ink-soft mb-6">Log in to your portfolio</p>

            <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="email" className="font-sans text-[13px] font-medium text-ink">Email</label>
                <input
                  id="email"
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className={cn(
                    'bg-card border border-line rounded-[8px] px-3 py-2.5 text-[15px] text-ink',
                    'placeholder:text-ink-faint transition-colors',
                    'hover:border-ink-faint focus:border-jade focus-visible:outline-2 focus-visible:outline-jade focus-visible:outline-offset-2',
                    'min-h-[44px]',
                  )}
                  placeholder="you@example.com"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="password" className="font-sans text-[13px] font-medium text-ink">Password</label>
                <input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className={cn(
                    'bg-card border border-line rounded-[8px] px-3 py-2.5 text-[15px] text-ink',
                    'placeholder:text-ink-faint transition-colors',
                    'hover:border-ink-faint focus:border-jade focus-visible:outline-2 focus-visible:outline-jade focus-visible:outline-offset-2',
                    'min-h-[44px]',
                  )}
                  placeholder="••••••••"
                />
              </div>

              {error && (
                <div className="bg-loss-soft border border-loss/20 rounded-[8px] px-3 py-2.5">
                  <p className="font-sans text-[13px] text-loss leading-[1.4]" role="alert">{error}</p>
                </div>
              )}

              <Button
                type="submit"
                variant="primary"
                disabled={loading || !email || !password}
                className="w-full mt-1 btn-press"
              >
                {loading ? 'Logging in…' : 'Log in'}
              </Button>
            </form>
          </div>

          <p className="text-center font-sans text-[14px] text-ink-soft mt-5">
            Don't have an account?{' '}
            <Link to="/register" className="text-jade font-medium hover:underline focus-visible:outline-2 focus-visible:outline-jade rounded">
              Sign up free
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
