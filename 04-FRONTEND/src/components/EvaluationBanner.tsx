import { FlaskConical } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'

interface EvaluationBannerProps {
  /** Hide the banner — only for views where the scoped experiment has gate_passed = true */
  hidden?: boolean
}

export function EvaluationBanner({ hidden = false }: EvaluationBannerProps) {
  if (hidden) return null
  return (
    <Alert variant="warning" className="mb-4">
      <FlaskConical className="h-4 w-4" />
      <AlertDescription>
        <strong>Model in evaluation</strong> — predictions are backtested but not yet
        production-validated. No experiment has cleared its success threshold. Treat all
        picks as exploratory, not advisory.
      </AlertDescription>
    </Alert>
  )
}
