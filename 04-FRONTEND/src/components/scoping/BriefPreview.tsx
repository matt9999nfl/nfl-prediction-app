/**
 * The approval brief — read-only, by construction.
 *
 * ADR-012, commitment 3: the brief is rendered by the server from the exact
 * config that will run, and the hash it carries is what approval is recorded
 * against. So this component:
 *
 *   - renders the returned markdown and offers no way to edit it (no inputs, no
 *     contentEditable, no HTML injection — see Markdown.tsx). Editing happens by
 *     re-answering a slot;
 *   - approves with the hash from THIS fetch, never a cached one;
 *   - on 409 `stale_brief`, re-fetches and says why, rather than retrying with a
 *     different hash.
 */

import { AlertTriangle, FileCheck2, Lock, RefreshCw } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { LoadingState } from '@/components/LoadingState'
import { ErrorState } from '@/components/ErrorState'
import { Markdown } from '@/components/scoping/Markdown'
import { ApiRequestError } from '@/api/client'
import type { Brief } from '@/api/scoping'

interface BriefPreviewProps {
  brief?: Brief
  isLoading: boolean
  isFetching: boolean
  error: unknown
  onRefetch: () => void

  /** Ids of required slots still blank. Non-empty disables approve. */
  missingRequired: string[]
  approvedHash: string | null | undefined

  onApprove: (configHash: string) => void
  approving: boolean
  /** Set when the last approve failed because the brief had moved on. */
  staleMessage: string | null
  approveError: unknown
}

export function BriefPreview({
  brief,
  isLoading,
  isFetching,
  error,
  onRefetch,
  missingRequired,
  approvedHash,
  onApprove,
  approving,
  staleMessage,
  approveError,
}: BriefPreviewProps) {
  const blocked = missingRequired.length > 0

  if (blocked) {
    return (
      <Card data-testid="brief-blocked">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <FileCheck2 className="h-4 w-4" />
            The brief
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Not rendered yet. {missingRequired.length} required{' '}
            {missingRequired.length === 1 ? 'question is' : 'questions are'} still unanswered:
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {missingRequired.map((id) => (
              <Badge key={id} variant="outline" className="font-mono text-[10px]">
                {id}
              </Badge>
            ))}
          </div>
        </CardContent>
      </Card>
    )
  }

  if (isLoading) return <LoadingState rows={6} />
  if (error && !brief) {
    return <ErrorState error={error} context="the brief" onRetry={onRefetch} />
  }
  if (!brief) return null

  const alreadyApproved = Boolean(approvedHash) && approvedHash === brief.config_hash

  return (
    <Card data-testid="brief-preview">
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <FileCheck2 className="h-4 w-4" />
            The brief
          </CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant="muted" className="gap-1">
              <Lock className="h-3 w-3" />
              Read-only
            </Badge>
            <Button variant="ghost" size="sm" onClick={onRefetch} disabled={isFetching}>
              <RefreshCw className={`mr-2 h-3.5 w-3.5 ${isFetching ? 'animate-spin' : ''}`} />
              Re-render
            </Button>
          </div>
        </div>
        <p className="text-sm text-muted-foreground">
          Rendered by the server from the exact config that will run. To change anything in it, go
          back and re-answer that question — the document is not editable, because a document you can
          edit is no longer a description of what runs.
        </p>
      </CardHeader>

      <CardContent className="space-y-4">
        {staleMessage && (
          <Alert variant="warning" data-testid="stale-brief-alert">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>{staleMessage}</AlertDescription>
          </Alert>
        )}

        <div
          className="max-h-[28rem] overflow-y-auto rounded-md border bg-background p-5"
          data-testid="brief-markdown"
          aria-readonly="true"
        >
          <Markdown source={brief.brief_markdown} />
        </div>

        <Separator />

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">
              Approving this hash
            </p>
            <p
              className="break-all font-mono text-xs"
              data-testid="brief-hash"
              data-config-hash={brief.config_hash}
            >
              {brief.config_hash}
            </p>
          </div>

          <Button
            onClick={() => onApprove(brief.config_hash)}
            disabled={approving || alreadyApproved}
            data-testid="approve-button"
          >
            {alreadyApproved ? 'Approved' : approving ? 'Approving…' : 'Approve this brief'}
          </Button>
        </div>

        {Boolean(approveError) && !staleMessage && (
          <Alert variant="destructive">
            <AlertDescription>
              {approveError instanceof ApiRequestError
                ? `Approval failed — ${approveError.message} (${approveError.code}, request: ${approveError.requestId})`
                : 'Approval failed.'}
            </AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  )
}
