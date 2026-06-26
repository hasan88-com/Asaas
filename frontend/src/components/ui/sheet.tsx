import * as React from 'react'
import { cn } from '@/lib/utils'

interface SheetProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  children: React.ReactNode
}

interface SheetContentProps extends React.HTMLAttributes<HTMLDivElement> {
  side?: 'bottom' | 'right'
}

const SheetContext = React.createContext<{ onClose: () => void }>({ onClose: () => {} })

function Sheet({ open, onOpenChange, children }: SheetProps) {
  const onClose = React.useCallback(() => onOpenChange(false), [onOpenChange])

  if (!open) return null

  return (
    <SheetContext.Provider value={{ onClose }}>
      <div className="fixed inset-0 z-50 flex">
        {/* Backdrop */}
        <div
          className="fixed inset-0 bg-ink/30 backdrop-blur-[2px]"
          onClick={onClose}
          aria-hidden="true"
        />
        {children}
      </div>
    </SheetContext.Provider>
  )
}

function SheetContent({ side = 'bottom', className, children, ...props }: SheetContentProps) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      className={cn(
        'fixed z-50 bg-card shadow-lg focus:outline-none',
        side === 'bottom' && [
          'inset-x-0 bottom-0 rounded-t-[14px] max-h-[90vh] flex flex-col',
          'drawer-enter',
        ],
        side === 'right' && [
          'right-0 top-0 h-full w-[400px] max-w-[90vw] flex flex-col',
          'drawer-enter',
        ],
        className,
      )}
      {...props}
    >
      {children}
    </div>
  )
}

function SheetHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('flex items-center justify-between p-4 border-b border-line', className)}
      {...props}
    />
  )
}

function SheetTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h2
      className={cn('font-sans font-semibold text-[16px] text-ink', className)}
      {...props}
    />
  )
}

function SheetClose({ className, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const { onClose } = React.useContext(SheetContext)
  return (
    <button
      onClick={onClose}
      className={cn(
        'text-ink-faint hover:text-ink transition-colors rounded p-1',
        'focus-visible:outline-2 focus-visible:outline-jade focus-visible:outline-offset-2',
        'min-h-[44px] min-w-[44px] flex items-center justify-center',
        className,
      )}
      aria-label="Close"
      {...props}
    />
  )
}

export { Sheet, SheetContent, SheetHeader, SheetTitle, SheetClose }
