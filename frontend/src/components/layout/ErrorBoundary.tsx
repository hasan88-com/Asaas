import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}
interface State {
  error: Error | null
}

/**
 * App-wide error boundary. Without it, any uncaught render error unmounts the
 * whole tree → blank white page. This catches it and shows the error + a reload,
 * so a single page's bug never blanks the app.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Surface the real error (the user saw only a blank page before).
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex flex-col items-center justify-center gap-4 p-8 text-center min-h-[60vh]">
          <p className="font-display text-[22px] font-semibold text-ink">Something went wrong on this page</p>
          <p className="font-mono text-[12px] text-loss max-w-lg break-words">{this.state.error.message}</p>
          <button
            type="button"
            onClick={() => { this.setState({ error: null }); window.location.reload() }}
            className="px-4 py-2 rounded-[8px] bg-jade text-white font-sans text-[13px] font-medium hover:bg-jade-dark transition-colors"
          >
            Reload page
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
