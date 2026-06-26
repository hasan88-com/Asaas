import { Link, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  MessageCircle,
  Newspaper,
  AlertTriangle,
  Settings,
  BarChart3,
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface NavItem {
  to: string
  label: string
  icon: React.ComponentType<{ size?: number; className?: string }>
}

const NAV_ITEMS: NavItem[] = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/chat', label: 'Chat', icon: MessageCircle },
  { to: '/news', label: 'News', icon: Newspaper },
  { to: '/debt-market', label: 'Debt', icon: BarChart3 },
  { to: '/flags', label: 'Flags', icon: AlertTriangle },
  { to: '/settings', label: 'Settings', icon: Settings },
]

interface NavBarProps {
  flagCount?: number
  variant?: 'top' | 'bottom'
}

export function NavBar({ flagCount = 0, variant = 'top' }: NavBarProps) {
  const { pathname } = useLocation()

  if (variant === 'bottom') {
    return (
      <nav
        className="fixed bottom-0 inset-x-0 z-30 bg-card border-t border-line flex md:hidden"
        aria-label="Main navigation"
      >
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => {
          const active = pathname === to || (to !== '/dashboard' && pathname.startsWith(to))
          return (
            <Link
              key={to}
              to={to}
              className={cn(
                'flex-1 flex flex-col items-center justify-center gap-0.5 min-h-[56px] text-[10px] font-mono uppercase tracking-[0.1em] transition-colors',
                'focus-visible:outline-2 focus-visible:outline-jade focus-visible:outline-offset-[-2px]',
                active ? 'text-jade' : 'text-ink-faint',
              )}
              aria-label={label}
              aria-current={active ? 'page' : undefined}
            >
              <div className="relative">
                <Icon size={20} />
                {to === '/flags' && flagCount > 0 && (
                  <span className="absolute -top-1 -right-1.5 w-4 h-4 bg-loss text-white font-mono text-[9px] rounded-full flex items-center justify-center">
                    {flagCount > 9 ? '9+' : flagCount}
                  </span>
                )}
              </div>
              <span>{label}</span>
            </Link>
          )
        })}
      </nav>
    )
  }

  // Top variant (desktop)
  return (
    <nav className="hidden md:flex items-center gap-1" aria-label="Main navigation">
      {NAV_ITEMS.map(({ to, label, icon: Icon }) => {
        const active = pathname === to || (to !== '/dashboard' && pathname.startsWith(to))
        return (
          <Link
            key={to}
            to={to}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded text-[14px] font-sans transition-colors relative',
              'focus-visible:outline-2 focus-visible:outline-jade focus-visible:outline-offset-2',
              active ? 'text-jade' : 'text-ink-soft hover:text-ink',
            )}
            aria-label={label}
            aria-current={active ? 'page' : undefined}
          >
            <Icon size={16} />
            <span>{label}</span>
            {to === '/flags' && flagCount > 0 && (
              <span className="ml-0.5 px-1 py-0.5 bg-loss text-white font-mono text-[10px] rounded-full leading-none">
                {flagCount > 9 ? '9+' : flagCount}
              </span>
            )}
            {active && (
              <span className="absolute bottom-0 inset-x-3 h-0.5 bg-jade rounded-full" aria-hidden />
            )}
          </Link>
        )
      })}
    </nav>
  )
}
