import { WifiOff } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { useHealth } from '@/api/queries'

export function HealthBanner() {
  const { isError, error } = useHealth()

  if (!isError) return null

  const msg =
    error instanceof Error && error.message.includes('fetch')
      ? 'Cannot reach the API — make sure the backend is running on localhost:8000.'
      : `API health check failed: ${error instanceof Error ? error.message : 'Unknown error'}`

  return (
    <Alert variant="destructive" className="mb-4">
      <WifiOff className="h-4 w-4" />
      <AlertDescription>{msg}</AlertDescription>
    </Alert>
  )
}
