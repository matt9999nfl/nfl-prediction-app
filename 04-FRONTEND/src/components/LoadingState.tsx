import { Skeleton } from '@/components/ui/skeleton'

interface LoadingStateProps {
  rows?: number
  className?: string
}

export function LoadingState({ rows = 4, className }: LoadingStateProps) {
  return (
    <div className={className} aria-busy="true" aria-label="Loading…">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="mb-3 h-16 w-full" />
      ))}
    </div>
  )
}

export function LoadingCards({ count = 3 }: { count?: number }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="rounded-lg border p-6 space-y-3">
          <Skeleton className="h-5 w-2/3" />
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="h-4 w-3/4" />
        </div>
      ))}
    </div>
  )
}

export function LoadingRow() {
  return <Skeleton className="h-12 w-full mb-2" />
}
