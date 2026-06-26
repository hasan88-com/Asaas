import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { postSuggest, postConfirm } from '@/lib/api'
import { OptimizerCard } from '@/components/chat/cards/OptimizerCard'
import { Button } from '@/components/ui/button'
import type { PortfolioResponse } from '@/types/api'

interface LocationState {
  portfolio?: PortfolioResponse | null
  hadHoldings?: boolean
}

export default function Suggestion() {
  console.log('Suggestion mounted')
  const navigate = useNavigate()
  const location = useLocation()
  const state = location.state as LocationState | null

  const [portfolio, setPortfolio] = useState<PortfolioResponse | null>(
    state?.portfolio ?? null,
  )
  const [loading, setLoading] = useState(!state?.portfolio)
  const [error, setError] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)

  useEffect(() => {
    if (portfolio) return
    postSuggest()
      .then(setPortfolio)
      .catch((err) => {
        if ((err as { status?: number }).status === 401) {
          navigate('/login', { replace: true })
          return
        }
        setError(err instanceof Error ? err.message : 'Failed to generate suggestion.')
      })
      .finally(() => setLoading(false))
  }, [])

  const handleConfirm = async () => {
    if (!portfolio) return
    setConfirming(true)
    setError(null)
    try {
      let result = portfolio
      if (portfolio.status !== 'confirmed') {
        result = await postConfirm([])
        console.log('confirm result', result)
      }
      console.log('navigating to dashboard')
      navigate('/dashboard', { replace: true })
    } catch (err) {
      if ((err as { status?: number }).status === 401) {
        navigate('/login', { replace: true })
        return
      }
      setError(err instanceof Error ? err.message : 'Failed to confirm. Please try again.')
    } finally {
      setConfirming(false)
    }
  }

  return (
    <div className="min-h-screen bg-paper flex flex-col items-center justify-center px-4 py-12">
      <div className="w-full max-w-xl">
        <div className="text-center mb-8">
          <span className="font-display text-[28px] font-semibold text-ink block mb-1">اثاثہ</span>
          <h1 className="font-display text-[20px] font-semibold text-ink">
            Your AI-built portfolio
          </h1>
          <p className="font-sans text-[14px] text-ink-soft mt-1">
            {portfolio?.has_existing_holdings
              ? 'Optimised to complement your existing positions.'
              : state?.hadHoldings
                ? 'Building around your declared holdings…'
                : 'Generated for your risk profile from scratch.'}
          </p>
        </div>

        {loading && (
          <div className="flex flex-col items-center gap-3 py-16">
            <span className="w-7 h-7 rounded-full border-2 border-jade border-t-transparent animate-spin" />
            <p className="font-sans text-[14px] text-ink-soft">
              Building your optimal allocation…
            </p>
          </div>
        )}

        {error && (
          <div className="bg-card border border-loss-soft rounded-[10px] p-4 text-center">
            <p className="font-sans text-[14px] text-loss">{error}</p>
            <Button
              variant="ghost"
              onClick={() => {
                setError(null)
                setLoading(true)
                postSuggest()
                  .then(setPortfolio)
                  .catch((e) => setError(e instanceof Error ? e.message : 'Failed'))
                  .finally(() => setLoading(false))
              }}
              className="mt-3"
            >
              Try again
            </Button>
          </div>
        )}

        {!loading && !error && portfolio && portfolio.holdings.length === 0 && (
          <div className="bg-card border border-line rounded-[10px] p-6 text-center">
            <p className="font-sans text-[14px] text-ink-soft mb-4">
              No instruments available to build a portfolio yet.
            </p>
            <Button
              variant="ghost"
              onClick={() => {
                setError(null)
                setLoading(true)
                postSuggest()
                  .then(setPortfolio)
                  .catch((e) => setError(e instanceof Error ? e.message : 'Failed'))
                  .finally(() => setLoading(false))
              }}
            >
              Try again
            </Button>
          </div>
        )}

        {!loading && !error && portfolio && portfolio.holdings.length > 0 && (
          <>
            <div className="[&_.card-shell]:max-w-none">
              <OptimizerCard
                data={portfolio}
                mode="suggest"
                groupByClass={!state?.hadHoldings && !portfolio.has_existing_holdings}
              />
            </div>

            <div className="flex gap-3 mt-6">
              <Button
                variant="ghost"
                onClick={() => navigate('/onboarding/holdings')}
                className="flex-1"
              >
                Adjust
              </Button>
              <Button
                variant="primary"
                onClick={handleConfirm}
                disabled={confirming}
                className="flex-1 btn-press"
              >
                {confirming ? 'Confirming…' : 'Confirm & go to dashboard'}
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
