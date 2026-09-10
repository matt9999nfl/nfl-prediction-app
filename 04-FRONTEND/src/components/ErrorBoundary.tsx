import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'

/**
 * Catches render errors so one bad value cannot blank the whole app.
 *
 * Why this exists: `ConfidenceBadge` called `tier.charAt(0)` on a field the API
 * returned as null for every prediction. That threw during render, React
 * unmounted the entire tree, and the dashboard went white a few seconds after
 * load with nothing on screen and nothing in the UI to say why. The bug was one
 * line in one badge; the blast radius was the whole application.
 *
 * React only unmounts everything when NO boundary exists above the throw. With
 * one here, the same bug shows a message and a reload button, and — more
 * usefully — the error text, so the next one takes minutes to diagnose instead
 * of a screen-share.
 *
 * This is deliberately a class component: error boundaries have no hook
 * equivalent. componentDidCatch is the only API React provides for this.
 */
interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Keep the component stack in the console — it names the component that
    // threw, which the message alone usually does not.
    console.error('Render error caught by ErrorBoundary:', error, info.componentStack)
  }

  render() {
    const { error } = this.state
    if (!error) return this.props.children

    return (
      <div className="mx-auto max-w-2xl p-8 space-y-4">
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription className="space-y-2">
            <p className="font-medium">Something broke while rendering this page.</p>
            <p className="text-sm opacity-90">
              The rest of the app is fine — this is a display bug, not lost data.
            </p>
            <pre className="mt-2 whitespace-pre-wrap rounded bg-black/10 p-2 text-xs">
              {error.message}
            </pre>
          </AlertDescription>
        </Alert>
        <div className="flex gap-2">
          <Button onClick={() => this.setState({ error: null })}>Try again</Button>
          <Button variant="outline" onClick={() => window.location.reload()}>
            Reload page
          </Button>
        </div>
      </div>
    )
  }
}
