import { Link } from 'react-router-dom'
import { useState, useEffect, useRef } from 'react'
import { Button } from '@/components/ui/button'
import {
  Shield, TrendingUp, Bell, MessageCircle, ChevronRight,
  BarChart2, Zap, Target, Brain, RefreshCw, Lock, Eye, FileText,
  ChevronDown,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { MarketTicker } from '@/components/layout/MarketTicker'

const FAQ_ITEMS = [
  {
    q: 'What is Asaasa?',
    a: "Asaasa is Pakistan's AI-powered wealth platform. It uses modern portfolio theory, live market data, and seven specialist AI agents to optimise, monitor, and explain your portfolio in plain language.",
  },
  {
    q: 'Do I need to be an expert investor?',
    a: 'No. Asaasa handles the complexity — risk profiling, optimisation, monitoring — and presents everything in plain language. You stay in control; the agent does the heavy lifting.',
  },
  {
    q: 'How does the AI agent work?',
    a: 'Seven specialist roles (profiler, optimizer, valuation, technical, news, rate-impact, general chat) route your questions to the right expert. You just ask — in English or Urdu — and get structured, actionable answers.',
  },
  {
    q: 'Which markets do you cover?',
    a: 'PSX stocks (KSE-100 and beyond), crypto (BTC, ETH, top 20), T-bills and SBP rates, commodities (gold, oil, silver), and mutual funds — with live pricing and news matched to your holdings.',
  },
]

/* ── Typing animation hook ──────────────────────────────── */
function useTypingAnimation(text: string, speed = 30, startDelay = 500) {
  const [displayed, setDisplayed] = useState('')
  const [started, setStarted] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => setStarted(true), startDelay)
    return () => clearTimeout(timer)
  }, [startDelay])

  useEffect(() => {
    if (!started) return
    if (displayed.length >= text.length) return
    const timer = setTimeout(() => {
      setDisplayed(text.slice(0, displayed.length + 1))
    }, speed)
    return () => clearTimeout(timer)
  }, [displayed, text, speed, started])

  return displayed
}

/* ── Scroll-triggered animation hook ────────────────────── */
function useScrollReveal(threshold = 0.2) {
  const ref = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true)
          observer.disconnect()
        }
      },
      { threshold },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [threshold])

  return { ref, visible }
}

/* ── Animated donut segment ─────────────────────────────── */
function AnimatedDonut({ visible }: { visible: boolean }) {
  const segments = [
    { label: 'Stocks', pct: 32, color: '#0F6E56' },
    { label: 'T-Bills', pct: 25, color: '#2F4858' },
    { label: 'Gold', pct: 20, color: '#B8801A' },
    { label: 'Crypto', pct: 13, color: '#5A3D6B' },
    { label: 'Funds', pct: 10, color: '#3E7C8C' },
  ]

  const radius = 44
  const circumference = 2 * Math.PI * radius
  let accumulated = 0

  return (
    <div className="w-[120px] h-[120px] relative shrink-0">
      <svg viewBox="0 0 120 120" className="w-full h-full -rotate-90">
        {segments.map((seg) => {
          const offset = accumulated
          accumulated += seg.pct
          const dashArray = (seg.pct / 100) * circumference
          const dashOffset = (offset / 100) * circumference
          return (
            <circle
              key={seg.label}
              cx="60"
              cy="60"
              r={radius}
              fill="none"
              stroke={seg.color}
              strokeWidth="8"
              strokeDasharray={`${dashArray} ${circumference - dashArray}`}
              strokeDashoffset={visible ? -dashOffset : circumference}
              strokeLinecap="butt"
              style={{
                transition: `stroke-dashoffset 1.2s cubic-bezier(0.23, 1, 0.32, 1) ${offset * 20}ms`,
              }}
            />
          )
        })}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-mono text-[9px] uppercase tracking-[0.1em] text-ink-faint">Total</span>
        <span className="font-display text-[16px] font-semibold text-ink">₨1.28M</span>
      </div>
    </div>
  )
}

/* ── Hero chart with hover tooltip ──────────────────────── */
function HeroChart() {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null)
  const values = [80, 70, 65, 55, 50, 40, 35, 25, 30, 20]
  const labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct']

  return (
    <div
      className="mt-4 h-[100px] relative cursor-crosshair"
      onMouseLeave={() => setHoverIdx(null)}
    >
      <svg viewBox="0 0 400 100" className="w-full h-full" preserveAspectRatio="none">
        <defs>
          <linearGradient id="heroFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#0F6E56" stopOpacity="0.15" />
            <stop offset="100%" stopColor="#0F6E56" stopOpacity="0.02" />
          </linearGradient>
        </defs>
        <path d="M0,80 Q50,70 100,65 T200,50 T300,35 T400,20 L400,100 L0,100 Z" fill="url(#heroFill)" />
        <path d="M0,80 Q50,70 100,65 T200,50 T300,35 T400,20" fill="none" stroke="#0F6E56" strokeWidth="2.5" />
        {/* Hover vertical line */}
        {hoverIdx !== null && (
          <line
            x1={hoverIdx * 44.4}
            y1="0"
            x2={hoverIdx * 44.4}
            y2="100"
            stroke="#DCD8CC"
            strokeWidth="1"
            strokeDasharray="4,4"
          />
        )}
      </svg>
      {/* Hover dots */}
      {hoverIdx !== null && (
        <div
          className="absolute pointer-events-none"
          style={{
            left: `${(hoverIdx / (values.length - 1)) * 100}%`,
            top: `${values[hoverIdx]}%`,
            transform: 'translate(-50%, -50%)',
          }}
        >
          <div className="w-3 h-3 rounded-full bg-jade border-2 border-card shadow-md" />
          <div className="absolute -top-8 left-1/2 -translate-x-1/2 bg-ink text-card font-mono text-[10px] px-2 py-0.5 rounded whitespace-nowrap">
            ₨{(1_284_500 - (100 - values[hoverIdx]) * 5000).toLocaleString()}
          </div>
        </div>
      )}
      {/* Invisible hover targets */}
      <div className="absolute inset-0 flex">
        {values.map((_, i) => (
          <div
            key={i}
            className="flex-1"
            onMouseEnter={() => setHoverIdx(i)}
          />
        ))}
      </div>
    </div>
  )
}

/* ── Typing agent chat ──────────────────────────────────── */
function TypingAgentChat() {
  const userMsg = useTypingAnimation(
    'My portfolio is mostly in banking stocks. Is that too concentrated?',
    25,
    800,
  )
  const agentMsg = useTypingAnimation(
    "Yes — your portfolio is 70% concentrated in banking. I'd suggest rebalancing: moving 10% to commodities and 5% to T-bills would improve your Sharpe ratio from 0.82 to 1.14.",
    15,
    userMsg.length > 0 ? 800 + userMsg.length * 25 + 500 : 99999,
  )

  return (
    <div className="bg-ink rounded-[14px] shadow-lg p-6">
      <div className="flex items-center gap-2 mb-4">
        <span className="w-2 h-2 rounded-full bg-gain" />
        <span className="font-mono text-[10px] uppercase tracking-[0.15em] text-ink-faint">Agent</span>
      </div>

      {/* User message */}
      <div className="flex justify-end mb-3">
        <div className="bg-jade-soft rounded-[10px] px-4 py-3 max-w-[85%]">
          <p className="font-sans text-[13px] text-ink leading-[1.5]">
            {userMsg}
            {userMsg.length < 'My portfolio is mostly in banking stocks. Is that too concentrated?'.length && (
              <span className="inline-block w-[2px] h-[14px] bg-ink ml-0.5 animate-pulse" />
            )}
          </p>
        </div>
      </div>

      {/* Agent response */}
      {userMsg.length >= 'My portfolio is mostly in banking stocks. Is that too concentrated?'.length && (
        <div className="flex justify-start">
          <div className="bg-ink-soft rounded-[10px] px-4 py-3 max-w-[85%]">
            <p className="font-sans text-[13px] text-paper leading-[1.5]">
              {agentMsg}
              {agentMsg.length < "Yes — your portfolio is 70% concentrated in banking. I'd suggest rebalancing: moving 10% to commodities and 5% to T-bills would improve your Sharpe ratio from 0.82 to 1.14.".length && (
                <span className="inline-block w-[2px] h-[14px] bg-paper ml-0.5 animate-pulse" />
              )}
            </p>
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-1.5 mt-4">
        {['Optimise my portfolio', 'Value HBL.KA', 'Explain risk score'].map((chip) => (
          <span key={chip} className="font-mono text-[9px] px-2 py-1 rounded-full bg-ink-soft text-paper border border-line-soft">
            {chip}
          </span>
        ))}
      </div>
    </div>
  )
}

export default function Landing() {
  const [openFaq, setOpenFaq] = useState<number | null>(null)
  const donutReveal = useScrollReveal(0.3)

  return (
    <div className="min-h-screen bg-paper flex flex-col">

      {/* ── Sticky band: ticker + nav ──────────────────── */}
      <div className="sticky top-0 z-30">
        <header className="flex items-center justify-between px-6 h-14 border-b border-line bg-card/90 backdrop-blur-sm z-40 relative">
          <div className="flex items-center gap-4">
            <Link to="/" className="flex items-center gap-2">
              <img src="/logo.png" alt="Asaasa" className="h-8 w-auto" />
              <span className="font-display text-[18px] font-semibold text-ink hidden sm:block">اثاثہ</span>
            </Link>
            <nav className="hidden md:flex items-center gap-5 ml-4">
              <a href="#features" className="font-mono text-[12px] uppercase tracking-[0.08em] text-ink-soft hover:text-ink transition-colors focus-visible:outline-2 focus-visible:outline-jade focus-visible:outline-offset-2 rounded">Features</a>
              <a href="#how" className="font-mono text-[12px] uppercase tracking-[0.08em] text-ink-soft hover:text-ink transition-colors focus-visible:outline-2 focus-visible:outline-jade focus-visible:outline-offset-2 rounded">How it works</a>
              <a href="#faq" className="font-mono text-[12px] uppercase tracking-[0.08em] text-ink-soft hover:text-ink transition-colors focus-visible:outline-2 focus-visible:outline-jade focus-visible:outline-offset-2 rounded">FAQ</a>
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <Link
              to="/login"
              className="font-mono text-[12px] uppercase tracking-[0.08em] text-ink-soft hover:text-ink transition-colors focus-visible:outline-2 focus-visible:outline-jade focus-visible:outline-offset-2 rounded"
            >
              Log in
            </Link>
            <Link to="/register">
              <Button variant="primary" size="sm" className="px-4 font-mono text-[12px] uppercase tracking-[0.06em]">
                Get started
              </Button>
            </Link>
          </div>
        </header>
        <MarketTicker />
      </div>

      {/* ── Hero ───────────────────────────────────────────── */}
      <section className="px-6 pt-16 pb-20 border-b border-line overflow-hidden">
        <div className="max-w-6xl mx-auto flex flex-col lg:flex-row items-center gap-12">
          <div className="flex-1 flex flex-col gap-6">
            <div className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-jade shrink-0" />
              <span className="font-mono text-[11px] uppercase tracking-[0.2em] text-jade font-semibold">
                AI-Powered Wealth Platform
              </span>
            </div>
            <h1 className="font-display font-semibold text-ink leading-[1.05]">
              <span className="block text-[48px] md:text-[64px]">Build a Smarter</span>
              <span className="block text-[48px] md:text-[64px]">Portfolio with</span>
              <span className="block text-[48px] md:text-[64px] text-jade">Asaasa.</span>
            </h1>
            <p className="font-sans text-[17px] leading-[1.6] text-ink-soft max-w-xl">
              Pakistan's only agentic wealth platform — MPT optimisation, live PSX data,
              SBP rate tracking, and seven specialist AI agents analysing your portfolio 24/7.
            </p>
            <div className="flex flex-wrap gap-3">
              <Link to="/try">
                <Button variant="primary" size="md" className="px-7 gap-2 font-mono uppercase tracking-[0.06em] text-[13px]">
                  Try it free <ChevronRight size={14} />
                </Button>
              </Link>
              <Link to="/register">
                <Button variant="outline" size="md" className="px-7 gap-2 font-mono uppercase tracking-[0.06em] text-[13px]">
                  Get started <ChevronRight size={14} />
                </Button>
              </Link>
            </div>
            <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-faint">
              No card required · Built for Pakistan
            </p>
          </div>

          <div className="flex-1 w-full max-w-[520px]">
            <div className="bg-card border border-line rounded-[14px] shadow-lg overflow-hidden">
              <div className="flex items-center gap-2 px-4 py-2.5 border-b border-line bg-paper">
                <span className="w-2.5 h-2.5 rounded-full bg-loss/60" />
                <span className="w-2.5 h-2.5 rounded-full bg-gold/60" />
                <span className="w-2.5 h-2.5 rounded-full bg-gain/60" />
                <span className="flex-1" />
                <span className="font-mono text-[10px] text-ink-faint">dashboard</span>
              </div>
              <div className="p-5">
                <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-faint">Portfolio value</p>
                <div className="flex items-baseline gap-2 mt-1">
                  <span className="font-display text-[36px] leading-[1] font-semibold text-ink tabular-nums">₨1,284,500</span>
                  <span className="font-mono text-[12px] tabular-nums text-gain font-medium">▲ +2.76%</span>
                </div>
                <HeroChart />
                <div className="flex flex-wrap gap-1.5 mt-4">
                  {['HBL.KA +2.4%', 'OGDC.KA −0.8%', 'Gold +0.9%', 'BTC +3.1%', 'MTB 20.1%'].map((chip) => (
                    <span key={chip} className="font-mono text-[9px] px-2 py-1 rounded-full bg-paper border border-line-soft text-ink-faint">
                      {chip}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Stats strip ────────────────────────────────────── */}
      <section className="px-6 py-8 border-b border-line bg-card">
        <div className="max-w-6xl mx-auto flex flex-wrap items-center justify-center gap-8 md:gap-16">
          {[
            { value: '₨4.2T', label: 'PSX Market Cap' },
            { value: '580+', label: 'Listed Companies' },
            { value: '7', label: 'AI Agent Roles' },
            { value: '15', label: 'Analysis Tools' },
            { value: '4', label: 'LLM Providers' },
          ].map(({ value, label }) => (
            <div key={label} className="flex flex-col items-center gap-1">
              <span className="font-mono text-[22px] font-semibold text-ink tabular-nums">{value}</span>
              <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-ink-faint">{label}</span>
            </div>
          ))}
        </div>
      </section>

      {/* ── Feature 1: Manage your portfolio + animated donut ─ */}
      <section className="px-6 py-16 border-b border-line">
        <div className="max-w-6xl mx-auto flex flex-col lg:flex-row items-center gap-12">
          <div className="flex-1 flex flex-col gap-4">
            <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-jade font-semibold">Manage your portfolio</span>
            <h2 className="font-display text-[32px] md:text-[40px] font-semibold text-ink leading-[1.1]">
              Automated Investing<br />Made Scalable
            </h2>
            <p className="font-sans text-[16px] leading-[1.6] text-ink-soft max-w-lg">
              Modern investors demand smart, low-touch tools for goal-based planning, portfolio rebalancing,
              and risk analysis. Asaasa automates investment guidance and asset allocation without the complexity.
            </p>
            <Link to="/try" className="mt-2">
              <Button variant="primary" size="md" className="px-6 gap-2 font-mono uppercase tracking-[0.06em] text-[13px]">
                Try it free <ChevronRight size={14} />
              </Button>
            </Link>
          </div>
          <div className="flex-1 w-full max-w-[480px]" ref={donutReveal.ref}>
            <div className="bg-card border border-line rounded-[14px] shadow-md p-6">
              <div className="flex items-center justify-between mb-4">
                <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-faint">Allocation</span>
                <span className="font-mono text-[10px] text-jade">Optimised</span>
              </div>
              <div className="flex items-center gap-6">
                <AnimatedDonut visible={donutReveal.visible} />
                <div className="flex flex-col gap-2">
                  {[
                    { label: 'Stocks', pct: '32%', color: 'bg-jade' },
                    { label: 'T-Bills', pct: '25%', color: 'bg-info' },
                    { label: 'Gold', pct: '20%', color: 'bg-gold' },
                    { label: 'Crypto', pct: '13%', color: 'bg-plum' },
                    { label: 'Funds', pct: '10%', color: 'bg-ac-fund' },
                  ].map(({ label, pct, color }, i) => (
                    <div
                      key={label}
                      className={cn(
                        'flex items-center gap-2 transition-all duration-500',
                        donutReveal.visible ? 'opacity-100 translate-x-0' : 'opacity-0 translate-x-4',
                      )}
                      style={{ transitionDelay: `${600 + i * 100}ms` }}
                    >
                      <span className={`w-2 h-2 rounded-sm ${color}`} />
                      <span className="font-mono text-[11px] text-ink-soft">{label}</span>
                      <span className="font-mono text-[11px] text-ink font-semibold tabular-nums">{pct}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Feature 2: Smarter advice + typing agent ──────── */}
      <section className="px-6 py-16 border-b border-line bg-card">
        <div className="max-w-6xl mx-auto flex flex-col lg:flex-row-reverse items-center gap-12">
          <div className="flex-1 flex flex-col gap-4">
            <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-gold font-semibold">Smarter advice</span>
            <h2 className="font-display text-[32px] md:text-[40px] font-semibold text-ink leading-[1.1]">
              AI Agents That<br />Understand Your Money
            </h2>
            <p className="font-sans text-[16px] leading-[1.6] text-ink-soft max-w-lg">
              Seven specialist roles — profiler, optimizer, valuation, technical, news, rate-impact, and general chat —
              route your questions to the right expert. Ask in English or Urdu; get structured, actionable answers.
            </p>
            <Link to="/try" className="mt-2">
              <Button variant="outline" size="md" className="px-6 gap-2 font-mono uppercase tracking-[0.06em] text-[13px]">
                Talk to your portfolio <ChevronRight size={14} />
              </Button>
            </Link>
          </div>
          <div className="flex-1 w-full max-w-[480px]">
            <TypingAgentChat />
          </div>
        </div>
      </section>

      {/* ── Key Features grid ─────────────────────────────── */}
      <section id="features" className="px-6 py-16 border-b border-line">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-12">
            <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-jade font-semibold">Platform capabilities</span>
            <h2 className="font-display text-[32px] md:text-[40px] font-semibold text-ink leading-[1.1] mt-3">
              Key Features
            </h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {[
              { icon: Target, accent: 'text-gain', bg: 'bg-jade-soft', title: 'Goal Tracking', desc: 'Define financial goals and visualise progress with AI-powered projections and asset recommendations.' },
              { icon: RefreshCw, accent: 'text-info', bg: 'bg-info-soft', title: 'Automated Allocation', desc: 'MPT optimisation auto-allocates funds across asset types based on your risk profile and investment horizon.' },
              { icon: Brain, accent: 'text-plum', bg: 'bg-plum-soft', title: 'Risk Profiling', desc: 'Dynamic questionnaires assess your risk appetite and adjust portfolio recommendations instantly.' },
              { icon: Eye, accent: 'text-gold', bg: 'bg-gold-soft', title: 'Real-Time Sync', desc: 'Live PSX, crypto, commodity, and T-bill pricing — your portfolio performance updates as markets move.' },
              { icon: MessageCircle, accent: 'text-rose', bg: 'bg-rose-soft', title: 'Advisor Agent', desc: 'Seven specialist AI roles monitor, explain, and suggest — always one tap away in the dashboard.' },
              { icon: FileText, accent: 'text-ac-fund', bg: 'bg-info-soft', title: 'Comprehensive Reporting', desc: 'Downloadable reports showing returns, historical trends, and asset exposure — instantly and securely.' },
            ].map(({ icon: Icon, title, desc, accent, bg }) => (
              <div key={title} className="bg-card border border-line rounded-[10px] p-6 flex flex-col gap-4 group hover:border-jade/40 transition-colors">
                <div className={cn('w-11 h-11 rounded-[10px] flex items-center justify-center', bg)}>
                  <Icon size={20} className={accent} />
                </div>
                <div>
                  <p className="font-mono text-[13px] font-semibold text-ink uppercase tracking-[0.06em] mb-1.5">{title}</p>
                  <p className="font-sans text-[14px] leading-[1.55] text-ink-soft">{desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── How it works ──────────────────────────────────── */}
      <section id="how" className="px-6 py-16 border-b border-line bg-card">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-12">
            <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-jade font-semibold">Simple process</span>
            <h2 className="font-display text-[32px] md:text-[40px] font-semibold text-ink leading-[1.1] mt-3">
              How Asaasa Works
            </h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            {[
              { step: '01', title: 'Sign up free', desc: 'Create an account in seconds. No card required.' },
              { step: '02', title: 'Tell us about you', desc: 'A quick risk-profiling questionnaire shapes your investor profile.' },
              { step: '03', title: 'Declare holdings', desc: 'Add your existing investments or start fresh with a suggested portfolio.' },
              { step: '04', title: 'AI takes over', desc: 'Seven agents optimise, monitor, and explain — you stay in control.' },
            ].map(({ step, title, desc }) => (
              <div key={step} className="flex flex-col gap-3">
                <span className="font-mono text-[32px] font-semibold text-jade/20 tabular-nums">{step}</span>
                <p className="font-mono text-[13px] font-semibold text-ink uppercase tracking-[0.06em]">{title}</p>
                <p className="font-sans text-[14px] leading-[1.55] text-ink-soft">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Benefits ──────────────────────────────────────── */}
      <section className="px-6 py-16 border-b border-line">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-12">
            <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-gold font-semibold">Why Asaasa</span>
            <h2 className="font-display text-[32px] md:text-[40px] font-semibold text-ink leading-[1.1] mt-3">
              Built for Pakistan
            </h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
            {[
              { icon: Zap, accent: 'text-gain', bg: 'bg-jade-soft', title: 'Start free', desc: "Full platform access without a credit card. Upgrade when you're ready." },
              { icon: TrendingUp, accent: 'text-info', bg: 'bg-info-soft', title: 'PSX-native', desc: 'Built for KSE-100, SBP rates, and PKR — not a generic global tool.' },
              { icon: Lock, accent: 'text-gold', bg: 'bg-gold-soft', title: 'Security-first', desc: 'Encrypted storage, row-level access, no PII to AI models. Your data stays yours.' },
              { icon: MessageCircle, accent: 'text-plum', bg: 'bg-plum-soft', title: 'Agentic, not passive', desc: 'Seven AI agents actively monitor and explain — not just a static dashboard.' },
            ].map(({ icon: Icon, title, desc, accent, bg }) => (
              <div key={title} className="bg-card border border-line rounded-[10px] p-6 flex flex-col gap-3">
                <div className={cn('w-10 h-10 rounded-[8px] flex items-center justify-center', bg)}>
                  <Icon size={18} className={accent} />
                </div>
                <p className="font-mono text-[13px] font-semibold text-ink uppercase tracking-[0.06em]">{title}</p>
                <p className="font-sans text-[14px] leading-[1.55] text-ink-soft">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── FAQ ───────────────────────────────────────────── */}
      <section id="faq" className="px-6 py-16 border-b border-line bg-card">
        <div className="max-w-3xl mx-auto">
          <div className="text-center mb-12">
            <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint font-semibold">FAQ</span>
            <h2 className="font-display text-[32px] md:text-[40px] font-semibold text-ink leading-[1.1] mt-3">
              Frequently Asked Questions
            </h2>
          </div>
          <div className="flex flex-col gap-3">
            {FAQ_ITEMS.map((item, i) => (
              <div key={i} className="bg-paper border border-line rounded-[10px] overflow-hidden">
                <button
                  type="button"
                  onClick={() => setOpenFaq(openFaq === i ? null : i)}
                  className="w-full px-5 py-4 flex items-center justify-between text-left hover:bg-line-soft/40 transition-colors"
                >
                  <span className="font-mono text-[13px] font-semibold text-ink pr-4">{item.q}</span>
                  <ChevronDown
                    size={16}
                    className={cn(
                      'text-ink-faint shrink-0 transition-transform duration-200',
                      openFaq === i && 'rotate-180',
                    )}
                  />
                </button>
                {openFaq === i && (
                  <div className="px-5 pb-4">
                    <p className="font-sans text-[14px] leading-[1.6] text-ink-soft">{item.a}</p>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Final CTA ─────────────────────────────────────── */}
      <section className="px-6 py-16 border-b border-line">
        <div className="max-w-4xl mx-auto text-center flex flex-col items-center gap-6">
          <h2 className="font-display text-[36px] md:text-[48px] font-semibold text-ink leading-[1.1]">
            Launch Your <span className="text-jade">Wealth Platform</span> Today
          </h2>
          <p className="font-sans text-[16px] text-ink-soft max-w-md">
            Secure, compliant, production-ready. Start building your portfolio intelligence in minutes.
          </p>
          <div className="flex flex-wrap gap-3 justify-center">
            <Link to="/register">
              <Button variant="primary" size="md" className="px-8 gap-2 font-mono uppercase tracking-[0.06em] text-[13px]">
                Start building <ChevronRight size={14} />
              </Button>
            </Link>
            <Link to="/try">
              <Button variant="outline" size="md" className="px-8 font-mono uppercase tracking-[0.06em] text-[13px]">
                Try it free
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* ── Footer ─────────────────────────────────────────── */}
      <footer className="border-t border-line px-6 py-6">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <img src="/logo.png" alt="Asaasa" className="h-6 w-auto" />
            <span className="font-display text-[14px] font-semibold text-ink">اثاثہ</span>
            <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-ink-faint">Pakistan Capital Markets</span>
          </div>
          <p className="font-mono text-[10px] text-ink-faint uppercase tracking-[0.1em]">
            Suggestions, not financial advice
          </p>
        </div>
      </footer>
    </div>
  )
}
