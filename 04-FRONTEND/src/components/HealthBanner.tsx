import { WifiOff } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { useHealth } from '@/api/queries'

export function HealthBanner() {
  const { isError, error } = useHealth()

  if (!isError) return null

  const msg =
    error instanceof Error && error.message.includes('fetch')
      ? 'Cannot reach the API — the backend may be temporarily unavailable. Please try again shortly.'
      : `API health check failed: ${error instanceof Error ? error.message : 'Unknown error'}`

  return (
    <Alert variant="destructive" className="mb-4">
      <WifiOff className="h-4 w-4" />
      <AlertDescription>{msg}</AlertDescription>
    </Alert>
  )
}
