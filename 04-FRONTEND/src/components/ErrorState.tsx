import { AlertTriangle, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ApiRequestError } from '@/api/client'

interface ErrorStateProps {
  error: unknown
  context?: string
  onRetry?: () => void
}

function humanise(error: unknown, context?: string): string {
  if (error instanceof ApiRequestError) {
    const where = context ? ` loading ${context}` : ''
    return `Couldn't${where} — ${error.message} (${error.status}, request: ${error.requestId})`
  }
  if (error instanceof TypeError && error.message.includes('fetch')) {
    return `Network error${context ? ` loading ${context}` : ''} — check that the API is running.`
  }
  if (error instanceof Error) {
    return error.message
  }
  return `An unexpected error occurred${context ? ` loading ${context}` : ''}.`
}

export function ErrorState({ error, context, onRetry }: ErrorStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-12 text-center">
      <AlertTriangle className="h-10 w-10 text-destructive" />
      <p className="max-w-md text-sm text-muted-foreground">{humanise(error, context)}</p>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Try again
        </Button>
      )}
    </div>
  )
}
