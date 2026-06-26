import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { supabase } from '@/lib/supabase'
import { postSession, getProfile } from '@/lib/api'

export default function AuthCallback() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  useEffect(() => {
    const handleCallback = async () => {
      const tokenHash = searchParams.get('token_hash')
      const type = searchParams.get('type')

      if (tokenHash && type) {
        const { error } = await supabase.auth.verifyOtp({
          token_hash: tokenHash,
          type: type as 'signup' | 'magiclink' | 'recovery',
        })
        if (error) {
          navigate('/login', { replace: true })
          return
        }
      }

      const { data } = await supabase.auth.getSession()
      if (data.session) {
        try {
          await postSession()
          const profile = await getProfile().catch(() => null)
          navigate(profile?.risk_tolerance ? '/dashboard' : '/onboarding', { replace: true })
        } catch {
          navigate('/login', { replace: true })
        }
      } else {
        navigate('/login', { replace: true })
      }
    }

    handleCallback()
  }, [navigate, searchParams])

  return (
    <div className="min-h-screen bg-paper flex items-center justify-center">
      <span className="w-3 h-3 rounded-full bg-jade animate-dot-pulse" aria-label="Loading…" />
    </div>
  )
}
