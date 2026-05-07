/**
 * Frameworks list — /frameworks
 *
 * Lists saved frameworks, each linking to its detail view.
 */

import { Link } from 'react-router-dom'
import { useFrameworks } from '@/api/queries'
import { LoadingState } from '@/components/LoadingState'
import { ErrorState } from '@/components/ErrorState'
import { EmptyState } from '@/components/EmptyState'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { formatRelativeDate, targetLabel } from '@/lib/formatters'
import { Layers } from 'lucide-react'

export function FrameworksPage() {
  const { data, isLoading, isError, error, refetch } = useFrameworks()

  const frameworks = data?.data ?? []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Frameworks</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Saved experiment configs you can reuse and iterate on
        </p>
      </div>

      {isLoading && <LoadingState rows={4} />}

      {isError && (
        <ErrorState
          error={error}
          context="frameworks"
          onRetry={() => void refetch()}
        />
      )}

      {!isLoading && !isError && frameworks.length === 0 && (
        <EmptyState
          icon={Layers}
          title="No frameworks saved yet"
          description="Run an experiment and click 'Save as framework' to create a named, reusable config."
        />
      )}

      {!isLoading && !isError && frameworks.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {frameworks.map((fw) => (
            <Link key={fw.framework_id} to={`/frameworks/${fw.framework_id}`} className="block group">
              <Card className="h-full transition-shadow group-hover:shadow-md">
                <CardHeader className="pb-2">
                  <CardTitle className="text-base leading-tight">{fw.name}</CardTitle>
                  <CardDescription className="line-clamp-2">
                    {fw.description || '—'}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-2">
                  <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                    <Badge variant="secondary">
                      {targetLabel(fw.config.target)}
                    </Badge>
                    <Badge variant="outline">{fw.config.model.type}</Badge>
                    <Badge variant="outline">
                      {fw.config.features.length} features
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Updated {formatRelativeDate(fw.updated_at)}
                  </p>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
