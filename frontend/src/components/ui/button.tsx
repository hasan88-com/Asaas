import * as React from 'react'
import { cn } from '@/lib/utils'

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'ghost' | 'outline'
  size?: 'sm' | 'md'
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'primary', size = 'md', ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          'inline-flex items-center justify-center font-sans font-medium rounded transition-all duration-[120ms]',
          'focus-visible:outline-2 focus-visible:outline-jade focus-visible:outline-offset-2',
          'disabled:opacity-40 disabled:pointer-events-none',
          'active:scale-[0.97]',
          // min touch target
          'min-h-[44px]',
          size === 'sm' && 'text-[14px] px-3 py-2 min-h-[36px]',
          size === 'md' && 'text-[14px] px-4 py-2.5',
          variant === 'primary' && 'bg-jade text-white hover:bg-[#0d5e49]',
          variant === 'ghost' && 'bg-transparent text-jade hover:bg-jade-soft',
          variant === 'outline' && 'bg-transparent border border-line text-ink hover:bg-paper',
          className,
        )}
        {...props}
      />
    )
  },
)
Button.displayName = 'Button'

export { Button }
