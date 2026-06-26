import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getQuestions, postQuestionnaire } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { QuestionDefinition } from '@/types/api'

const CATEGORY_META: Record<string, { label: string; icon: string; color: string }> = {
  goals:      { label: 'Investment Goals',   icon: '🎯', color: 'jade' },
  risk:       { label: 'Risk Profile',       icon: '⚖️', color: 'loss' },
  behavioral: { label: 'Investor Profile',   icon: '🧠', color: 'info' },
  capital:    { label: 'Capital',            icon: '💰', color: 'jade' },
  preferences:{ label: 'Asset Preferences', icon: '📊', color: 'info' },
  general:    { label: 'General',            icon: '📊', color: 'ink-soft' },
}

const NUMERIC_QUESTION_IDS = new Set(['initial_capital', 'monthly_contribution'])

export default function Questionnaire() {
  const navigate = useNavigate()

  const [questions, setQuestions] = useState<QuestionDefinition[]>([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Core questions (non-preferences category)
  const coreQuestions = questions.filter((q) => q.category !== 'preferences')
  // Preferences questions (optional screen at the end)
  const prefQuestions = questions.filter((q) => q.category === 'preferences')

  const [step, setStep] = useState(0)
  const [showPrefs, setShowPrefs] = useState(false)

  // Answers for core questions
  const [answers, setAnswers] = useState<Record<string, string | string[]>>({})
  // Numeric fields extracted as separate state for cleaner UX
  const [initialCapital, setInitialCapital] = useState('')
  const [monthlyContribution, setMonthlyContribution] = useState('0')
  // Preferences answers
  const [prefAnswers, setPrefAnswers] = useState<Record<string, string[]>>({})

  useEffect(() => {
    getQuestions()
      .then(setQuestions)
      .catch(() => setError('Could not load questions. Please refresh.'))
      .finally(() => setLoading(false))
  }, [])

  const current = coreQuestions[step]
  const total = coreQuestions.length
  const catMeta = CATEGORY_META[current?.category ?? 'general'] ?? CATEGORY_META.general

  const isNumeric = current ? NUMERIC_QUESTION_IDS.has(current.id) : false

  // Determine whether the current step has a valid answer
  const hasAnswer = (() => {
    if (!current) return false
    if (current.id === 'initial_capital') return initialCapital.trim().length > 0 && Number(initialCapital) > 0
    if (current.id === 'monthly_contribution') return monthlyContribution.trim().length > 0 && Number(monthlyContribution) >= 0
    const ans = answers[current.id]
    if (current.multiple) return Array.isArray(ans) && ans.length > 0
    return !!ans
  })()

  // Visible preferences questions (considering conditional_on)
  const selectedAssetClasses = prefAnswers['asset_classes'] ?? []
  const visiblePrefQuestions = prefQuestions.filter((q) => {
    if (!q.conditional_on) return true
    const [condKey, condVal] = Object.entries(q.conditional_on)[0]
    if (condKey === 'asset_classes') return selectedAssetClasses.includes(condVal)
    return true
  })

  // ── Handlers ────────────────────────────────────────────────────────────────

  const toggleSingle = (value: string) => {
    setAnswers((a) => ({ ...a, [current.id]: value }))
  }

  const toggleMulti = (qId: string, value: string, setter: any) => {
    setter((prev: any) => {
      const key = qId
      const old = (prev[key] as string[] | undefined) ?? []
      return {
        ...prev,
        [key]: old.includes(value) ? old.filter((v) => v !== value) : [...old, value],
      }
    })
  }

  const handleCoreNext = () => {
    if (step < total - 1) {
      setStep((s) => s + 1)
    } else if (prefQuestions.length === 0) {
      handleSubmit()
    } else {
      setShowPrefs(true)
    }
  }

  const handleSubmit = async () => {
    setSubmitting(true)
    setError(null)
    try {
      // Build answer list (exclude numeric questions — those go as top-level fields)
      const answerList = Object.entries(answers)
        .filter(([id]) => !NUMERIC_QUESTION_IDS.has(id))
        .map(([question_id, answer]) => ({ question_id, answer }))

      // Build investment_preferences from prefs screen
      const assetClasses = prefAnswers['asset_classes'] ?? []
      const shariah = assetClasses.includes('shariah')
      const classes = assetClasses.filter((c) => c !== 'shariah')

      const investmentPreferences = assetClasses.length > 0 ? {
        shariah,
        asset_classes: classes,
        psx_sectors: prefAnswers['psx_sectors'] ?? [],
        crypto_assets: prefAnswers['crypto_assets'] ?? [],
        fixed_income_products: prefAnswers['fixed_income_products'] ?? [],
      } : undefined

      const investmentFrequency = (answers['investment_frequency'] as string) || 'one_time'

      const result = await postQuestionnaire(
        answerList,
        initialCapital,
        monthlyContribution,
        investmentFrequency,
        investmentPreferences,
      )
      console.log('submit result', result)
      console.log('navigating to holdings')
      navigate('/onboarding/holdings', { replace: true })
    } catch (err) {
      if ((err as { status?: number }).status === 401) {
        navigate('/login', { replace: true })
        return
      }
      setError(err instanceof Error ? err.message : 'Submission failed. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  // ── Loading state ────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="min-h-screen bg-paper flex items-center justify-center">
        <span className="w-6 h-6 rounded-full border-2 border-jade border-t-transparent animate-spin" />
      </div>
    )
  }

  // ── Error / empty state ──────────────────────────────────────────────────────

  if (!questions.length) {
    return (
      <div className="min-h-screen bg-paper flex flex-col items-center justify-center px-4 gap-4">
        <p className="font-sans text-[15px] text-ink text-center">
          {error ?? 'Could not load questions. Please refresh.'}
        </p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="font-sans text-[14px] text-jade hover:underline focus-visible:outline-2 focus-visible:outline-jade rounded"
        >
          Refresh
        </button>
      </div>
    )
  }

  // ── Preferences screen ───────────────────────────────────────────────────────

  if (showPrefs) {
    return (
      <div className="min-h-screen bg-paper flex flex-col items-center justify-center px-4 py-12">
        <div className="w-full max-w-md">
          <div className="text-center mb-6">
            <span className="font-display text-[28px] font-semibold text-ink">اثاثہ</span>
            <p className="font-sans text-[13px] text-ink-faint mt-1">Asset Preferences</p>
          </div>

          <div className="w-full h-1.5 bg-jade rounded-full mb-6" />

          <div className="bg-card border border-line rounded-[14px] shadow-sm p-6 flex flex-col gap-6">
            {visiblePrefQuestions.length === 0 && prefQuestions.length > 0 && (
              <p className="font-sans text-[14px] text-ink-soft text-center">
                Select asset classes below to see sub-options.
              </p>
            )}

            {prefQuestions.map((q) => {
              // Only show asset_classes question or visible conditionals
              const isVisible = !q.conditional_on || visiblePrefQuestions.includes(q)
              if (!isVisible) return null

              const currentSel = prefAnswers[q.id] ?? []
              return (
                <div key={q.id}>
                  <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-faint mb-2">
                    {q.question}
                  </p>
                  <div className="flex flex-col gap-2">
                    {q.options.map((opt) => {
                      const selected = currentSel.includes(opt.value)
                      return (
                        <button
                          key={opt.value}
                          type="button"
                          onClick={() => toggleMulti(q.id, opt.value, setPrefAnswers as Parameters<typeof toggleMulti>[2])}
                          className={cn(
                            'flex items-center gap-3 w-full text-left px-4 py-3 rounded-[8px] border transition-all duration-150 min-h-[44px]',
                            'focus-visible:outline-2 focus-visible:outline-jade focus-visible:outline-offset-2 btn-press',
                            selected
                              ? 'bg-jade text-white border-jade shadow-sm'
                              : 'bg-card text-ink border-line hover:border-jade-soft hover:bg-jade-soft/30',
                          )}
                        >
                          <span
                            className={cn(
                              'w-4 h-4 rounded border-2 flex items-center justify-center shrink-0 transition-colors',
                              selected ? 'bg-white border-white' : 'border-current',
                            )}
                            aria-hidden
                          >
                            {selected && (
                              <svg viewBox="0 0 10 8" fill="none" className="w-2.5 h-2.5">
                                <path d="M1 4l3 3 5-6" stroke="#0F6E56" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                              </svg>
                            )}
                          </span>
                          <span className="font-sans text-[14px]">{opt.label}</span>
                        </button>
                      )
                    })}
                  </div>
                </div>
              )
            })}

            {error && (
              <div className="bg-loss-soft border border-loss/20 rounded-[8px] px-3 py-2.5">
                <p className="font-sans text-[13px] text-loss" role="alert">{error}</p>
              </div>
            )}

            <div className="flex gap-3">
              <Button variant="ghost" onClick={() => setShowPrefs(false)} className="flex-1 btn-press">
                Back
              </Button>
              <Button
                variant="primary"
                onClick={handleSubmit}
                disabled={submitting}
                className="flex-1 btn-press"
              >
                {submitting ? 'Saving…' : 'Complete Profile'}
              </Button>
            </div>

            <p className="font-sans text-[12px] text-ink-faint text-center">
              Asset preferences are optional — you can skip and complete your profile now.
            </p>
          </div>
        </div>
      </div>
    )
  }

  // ── Core questionnaire ───────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-paper flex flex-col items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">
        <div className="text-center mb-6">
          <span className="font-display text-[28px] font-semibold text-ink">اثاثہ</span>
          <p className="font-sans text-[13px] text-ink-faint mt-1">Investor Profiling</p>
        </div>

        {total > 0 && (
          <div className="w-full h-1.5 bg-line rounded-full mb-6 overflow-hidden">
            <div
              className="h-full bg-jade rounded-full transition-[width] duration-300"
              style={{ width: `${((step + 1) / (total + 1)) * 100}%` }}
              role="progressbar"
              aria-valuenow={step + 1}
              aria-valuemin={1}
              aria-valuemax={total + 1}
            />
          </div>
        )}

        {current && (
          <div className="bg-card border border-line rounded-[14px] shadow-sm p-6">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[18px]">{catMeta.icon}</span>
              <span className={cn(
                'font-mono text-[10px] uppercase tracking-[0.18em] font-semibold',
                catMeta.color === 'jade'     ? 'text-jade' :
                catMeta.color === 'loss'     ? 'text-loss' :
                'text-ink-faint'
              )}>
                {catMeta.label}
              </span>
            </div>
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-faint mb-3">
              Question {step + 1} of {total}
            </p>

            <h2 className="font-display text-[18px] font-semibold text-ink mb-5 leading-[1.3]">
              {current.question}
            </h2>

            {/* ── Numeric input ── */}
            {isNumeric ? (
              <div className="flex flex-col gap-2">
                <div className="flex items-center border border-line rounded-[8px] bg-card overflow-hidden focus-within:border-jade focus-within:outline focus-within:outline-2 focus-within:outline-jade focus-within:outline-offset-2 transition-colors">
                  <span className="px-3 py-2.5 font-mono text-[18px] text-ink-soft border-r border-line select-none">
                    ₨
                  </span>
                  <input
                    type="number"
                    inputMode="numeric"
                    min={current.id === 'monthly_contribution' ? 0 : 1}
                    value={current.id === 'initial_capital' ? initialCapital : monthlyContribution}
                    onChange={(e) =>
                      current.id === 'initial_capital'
                        ? setInitialCapital(e.target.value)
                        : setMonthlyContribution(e.target.value)
                    }
                    className="flex-1 bg-transparent px-3 py-2.5 text-[18px] font-mono text-ink tabular-nums min-h-[48px] focus:outline-none"
                    placeholder={current.id === 'initial_capital' ? 'e.g. 1,000,000' : '0'}
                  />
                </div>
                {current.id === 'initial_capital' && (
                  <p className="font-sans text-[12px] text-ink-faint">
                    Your investable capital — money you can put to work long-term.
                  </p>
                )}
                {current.id === 'monthly_contribution' && (
                  <p className="font-sans text-[12px] text-ink-faint">
                    Enter 0 if you plan to invest once and not add monthly contributions.
                  </p>
                )}
              </div>

            /* ── Multi-select ── */
            ) : current.multiple ? (
              <div className="flex flex-col gap-2">
                {current.options.map((opt) => {
                  const sel = (Array.isArray(answers[current.id]) ? answers[current.id] as string[] : []).includes(opt.value)
                  return (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => toggleMulti(current.id, opt.value, setAnswers as Parameters<typeof toggleMulti>[2])}
                      className={cn(
                        'flex items-center gap-3 w-full text-left px-4 py-3 rounded-[8px] border transition-all duration-150 min-h-[44px]',
                        'focus-visible:outline-2 focus-visible:outline-jade focus-visible:outline-offset-2 btn-press',
                        sel
                          ? 'bg-jade text-white border-jade shadow-sm'
                          : 'bg-card text-ink border-line hover:border-jade-soft hover:bg-jade-soft/30',
                      )}
                    >
                      <span className={cn('w-4 h-4 rounded border-2 flex items-center justify-center shrink-0 transition-colors', sel ? 'bg-white border-white' : 'border-current')} aria-hidden>
                        {sel && (
                          <svg viewBox="0 0 10 8" fill="none" className="w-2.5 h-2.5">
                            <path d="M1 4l3 3 5-6" stroke="#0F6E56" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                        )}
                      </span>
                      <span className="font-sans text-[14px]">{opt.label}</span>
                    </button>
                  )
                })}
              </div>

            /* ── Single select ── */
            ) : (
              <div className="flex flex-col gap-2">
                {current.options.map((opt) => {
                  const sel = answers[current.id] === opt.value
                  return (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => toggleSingle(opt.value)}
                      className={cn(
                        'w-full text-left px-4 py-3 rounded-[8px] border font-sans text-[14px] transition-all duration-150 min-h-[44px]',
                        'focus-visible:outline-2 focus-visible:outline-jade focus-visible:outline-offset-2 btn-press',
                        sel
                          ? 'bg-jade text-white border-jade shadow-sm'
                          : 'bg-card text-ink border-line hover:border-jade-soft hover:bg-jade-soft/30',
                      )}
                    >
                      {opt.label}
                    </button>
                  )
                })}
              </div>
            )}

            {error && (
              <div className="bg-loss-soft border border-loss/20 rounded-[8px] px-3 py-2.5 mt-4">
                <p className="font-sans text-[13px] text-loss" role="alert">{error}</p>
              </div>
            )}

            <div className="flex gap-3 mt-6">
              {step > 0 && (
                <Button variant="ghost" onClick={() => setStep((s) => s - 1)} className="flex-1 btn-press">
                  Back
                </Button>
              )}
              <Button
                variant="primary"
                onClick={handleCoreNext}
                disabled={!hasAnswer}
                className="flex-1 btn-press"
              >
                {step < total - 1 ? 'Next' : 'Continue →'}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
