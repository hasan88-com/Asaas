import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from '@/context/AuthContext'
import { ThemeProvider } from '@/context/ThemeContext'
import { AuthGuard } from '@/components/layout/AuthGuard'
import { GuestGuard } from '@/components/layout/GuestGuard'
import { AppShell } from '@/components/layout/AppShell'
import { ErrorBoundary } from '@/components/layout/ErrorBoundary'

// Public
const Landing = lazy(() => import('@/pages/Landing'))
const Login = lazy(() => import('@/pages/Login'))
const Register = lazy(() => import('@/pages/Register'))
const GuestAnalyze = lazy(() => import('@/pages/GuestAnalyze'))
const AuthCallback = lazy(() => import('@/pages/AuthCallback'))

// Onboarding
const Questionnaire = lazy(() => import('@/pages/onboarding/Questionnaire'))
const DeclareHoldings = lazy(() => import('@/pages/onboarding/DeclareHoldings'))
const Suggestion = lazy(() => import('@/pages/onboarding/Suggestion'))

// Core app
const Dashboard = lazy(() => import('@/pages/Dashboard'))
const News = lazy(() => import('@/pages/News'))
const Flags = lazy(() => import('@/pages/Flags'))
const HoldingDetail = lazy(() => import('@/pages/HoldingDetail'))

// Market
const DebtMarket = lazy(() => import('@/pages/DebtMarket'))
const NewsChat = lazy(() => import('@/pages/NewsChat'))

// Account
const Settings = lazy(() => import('@/pages/Settings'))
const PortfolioManagement = lazy(() => import('@/pages/PortfolioManagement'))
const Watchlist = lazy(() => import('@/pages/Watchlist'))

function PageLoader() {
  return (
    <div className="flex items-center justify-center h-screen bg-paper">
      <span className="w-3 h-3 rounded-full bg-jade animate-dot-pulse" aria-label="Loading…" />
    </div>
  )
}

export default function App() {
  return (
    <ThemeProvider>
    <AuthProvider>
      <ErrorBoundary>
       <Suspense fallback={<PageLoader />}>
        <Routes>
          {/* Auth callback — no guards, handles email verification */}
          <Route path="/auth/callback" element={<AuthCallback />} />

          {/* Public — redirect authenticated users to dashboard */}
          <Route element={<GuestGuard />}>
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/try" element={<GuestAnalyze />} />
          </Route>

          {/* Authenticated — redirect unauthenticated to login */}
          <Route element={<AuthGuard />}>
            {/* Onboarding (no app shell — full-screen flow) */}
            <Route path="/onboarding" element={<Questionnaire />} />
            <Route path="/onboarding/holdings" element={<DeclareHoldings />} />
            <Route path="/onboarding/suggest" element={<Suggestion />} />

            {/* Core app with nav shell */}
            <Route element={<AppShell />}>
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/news" element={<News />} />
              <Route path="/news-chat" element={<NewsChat />} />
              <Route path="/debt-market" element={<DebtMarket />} />
              <Route path="/flags" element={<Flags />} />
              <Route path="/holdings/:symbol" element={<HoldingDetail />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/portfolio" element={<PortfolioManagement />} />
              <Route path="/watchlist" element={<Watchlist />} />
            </Route>
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
       </Suspense>
      </ErrorBoundary>
    </AuthProvider>
    </ThemeProvider>
  )
}
