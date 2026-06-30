import { useState } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { supabase } from '@/lib/supabase'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface LocationState {
  guestData?: unknown
}

export default function Register() {
  const navigate = useNavigate()
  const location = useLocation()
  const state = location.state as LocationState | null

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [confirmEmail, setConfirmEmail] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (password !== confirm) {
      setError("Passwords don't match.")
      return
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }
    setLoading(true)
    try {
      const { data, error: authErr } = await supabase.auth.signUp({
        email,
        password,
        options: { emailRedirectTo: `${import.meta.env.VITE_SITE_URL || window.location.origin}/auth/callback` },
      })
      if (authErr) throw authErr

      if (!data.session) {
        setConfirmEmail(true)
        return
      }

      navigate('/onboarding', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign up failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-paper flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="flex items-center justify-center gap-2 mb-8">
          <img src="/logo.png" alt="Asaasa" className="h-10 w-auto" />
          <span className="font-display text-[24px] font-semibold text-ink">اثاثہ</span>
        </div>

        <div className="bg-card border border-line rounded-[14px] shadow-sm p-6">
          {confirmEmail ? (
            <div className="text-center py-4">
              <h2 className="font-display text-[20px] font-semibold text-ink mb-2">Check your email</h2>
              <p className="font-sans text-[14px] text-ink-soft">
                We sent a confirmation link to <strong>{email}</strong>.
              </p>
              <Button variant="ghost" className="mt-4" onClick={() => navigate('/login')}>
                Back to login
              </Button>
            </div>
          ) : (
            <>
              <h1 className="font-display text-[24px] font-semibold text-ink mb-1">Create account</h1>
              <p className="font-sans text-[14px] text-ink-soft mb-6">Start building your portfolio</p>

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
                    autoComplete="new-password"
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

                <div className="flex flex-col gap-1.5">
                  <label htmlFor="confirm" className="font-sans text-[13px] font-medium text-ink">Confirm password</label>
                  <input
                    id="confirm"
                    type="password"
                    autoComplete="new-password"
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
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
                  disabled={loading || !email || !password || !confirm}
                  className="w-full mt-1 btn-press"
                >
                  {loading ? 'Creating account…' : 'Sign up'}
                </Button>
              </form>
            </>
          )}
        </div>

        <p className="text-center font-sans text-[14px] text-ink-soft mt-5">
          Already have an account?{' '}
          <Link to="/login" className="text-jade font-medium hover:underline focus-visible:outline-2 focus-visible:outline-jade rounded">
            Log in
          </Link>
        </p>
      </div>
    </div>
  )
}
