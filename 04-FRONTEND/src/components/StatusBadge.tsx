import { Badge } from '@/components/ui/badge'
import type { DatasetStatus, ExperimentStatus } from '@/api/types'

type AnyStatus = DatasetStatus | ExperimentStatus | 'running' | 'complete' | 'failed' | 'scheduled' | 'final'

const config: Record<AnyStatus, { label: string; variant: 'success' | 'warning' | 'info' | 'destructive' | 'muted' | 'secondary' }> = {
  // Dataset
  uploading: { label: 'Uploading', variant: 'info' },
  mapping: { label: 'Needs mapping', variant: 'warning' },
  ready: { label: 'Ready', variant: 'success' },
  error: { label: 'Error', variant: 'destructive' },
  // Experiment
  draft: { label: 'Draft', variant: 'muted' },
  running: { label: 'Running', variant: 'info' },
  complete: { label: 'Complete', variant: 'success' },
  failed: { label: 'Failed', variant: 'destructive' },
  // Game
  scheduled: { label: 'Scheduled', variant: 'info' },
  final: { label: 'Final', variant: 'success' },
}

interface StatusBadgeProps {
  status: AnyStatus
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const { label, variant } = config[status] ?? { label: status, variant: 'secondary' }
  return <Badge variant={variant as Parameters<typeof Badge>[0]['variant']}>{label}</Badge>
}

interface GateBadgeProps {
  gatePassed: boolean | null
}

export function GateBadge({ gatePassed }: GateBadgeProps) {
  if (gatePassed === null) return <Badge variant="muted">Not evaluated</Badge>
  if (gatePassed) return <Badge variant="success">Gate passed ✓</Badge>
  return <Badge variant="warning">Gate not passed</Badge>
}

interface ConfidenceBadgeProps {
  tier: 'high' | 'medium' | 'low'
}

export function ConfidenceBadge({ tier }: ConfidenceBadgeProps) {
  const v = tier === 'high' ? 'success' : tier === 'medium' ? 'info' : 'muted'
  return (
    <Badge variant={v as Parameters<typeof Badge>[0]['variant']}>
      {tier.charAt(0).toUpperCase() + tier.slice(1)} confidence
    </Badge>
  )
}
