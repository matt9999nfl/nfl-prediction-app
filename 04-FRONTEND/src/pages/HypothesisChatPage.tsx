/**
 * Hypothesis Chat — /experiments/hypothesis
 *
 * A second door to the same experiment runner. /experiments/new (the wizard) is
 * untouched and stays exactly as it was.
 *
 * The three commitments from ADR-012 are the shape of this file:
 *
 *  1. THE SERVER OWNS THE CONFIG. There is no form object here. Each answer is
 *     posted on its own to POST /sessions/{id}/answers and the response — the
 *     whole session state, including what to ask next and what is still missing
 *     — replaces what this page knows. The client never assembles a config and
 *     never decides the question order.
 *
 *  2. A PRE-FILL IS NEVER AN ANSWER. /extract returns proposals. They are held
 *     here, attached to the question they belong to, and rendered as visibly
 *     unconfirmed until Matt acts. Nothing from /extract is ever posted on his
 *     behalf. (SlotPrompt.tsx does the rendering.)
 *
 *  3. THE BRIEF IS READ-ONLY, and approval is by the hash the brief carried.
 *     A 409 stale_brief re-fetches and explains; it never retries with another
 *     hash.
 *
 * Degradation is normal, not an error state: extraction can be unavailable (no
 * API key), and the governor 409s until the required slots are answered.
 * Neither can stop the session reaching a run.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  CheckCircle2,
  FlaskConical,
  Info,
  Pencil,
  PlayCircle,
  Sparkles,
} from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { LoadingState } from '@/components/LoadingState'
import { ErrorState } from '@/components/ErrorState'
import { BriefPreview } from '@/components/scoping/BriefPreview'
import { CapabilityGapNotice } from '@/components/scoping/CapabilityGapNotice'
import { GovernorPanel } from '@/components/scoping/GovernorPanel'
import { SlotPrompt } from '@/components/scoping/SlotPrompt'
import { ApiRequestError } from '@/api/client'
import {
  useAnswerSlot,
  useApprove,
  useBrief,
  useDispatch,
  useExtract,
  useReview,
  useSession,
  useStartSession,
  type CapabilityGap,
  type DispatchResult,
  type Prefill,
  type Question,
} from '@/api/scoping'

// ── helpers ──────────────────────────────────────────────────────────────────

/** A short, honest rendering of an answer for the transcript. */
function summarise(value: unknown): string {
  if (value === null || value === undefined) return 'skipped'
  if (typeof value === 'boolean') return value ? 'yes' : 'no'
  if (typeof value === 'string') return value.trim() === '' ? '(blank)' : value
  if (typeof value === 'number') return String(value)
  if (Array.isArray(value)) {
    if (value.length === 0) return 'none'
    return `${value.length} selected`
  }
  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
    if (entries.length === 0) return 'none'
    return entries.map(([k, v]) => `${k}: ${String(v)}`).join(' · ')
  }
  return String(value)
}

function messageFor(error: unknown, fallback: string): string {
  if (error instanceof ApiRequestError) {
    return `${error.message} (${error.code}, request: ${error.requestId})`
  }
  if (error instanceof Error) return error.message
  return fallback
}

const EXAMPLE = 'teams with heavier O lines perform better in poor weather'

// ── page ─────────────────────────────────────────────────────────────────────

export function HypothesisChatPage() {
  const [hypothesis, setHypothesis] = useState('')
  const [sessionId, setSessionId] = useState<string | null>(null)

  const [prefills, setPrefills] = useState<Prefill[]>([])
  const [gaps, setGaps] = useState<CapabilityGap[]>([])
  const [extractionUnavailable, setExtractionUnavailable] = useState(false)
  const [extractRan, setExtractRan] = useState(false)

  const [editingSlot, setEditingSlot] = useState<string | null>(null)
  const [answerError, setAnswerError] = useState<string | null>(null)
  const [staleMessage, setStaleMessage] = useState<string | null>(null)
  const [dispatchResult, setDispatchResult] = useState<DispatchResult | null>(null)
  const [dispatchError, setDispatchError] = useState<string | null>(null)

  /**
   * Question metadata seen so far, so an answered slot can be re-asked exactly
   * as the tree declared it. The server only ever hands back the NEXT question,
   * so this is a cache of what it has already said — not a second source of
   * truth about answers.
   */
  const asked = useRef(new Map<string, Question>())

  const start = useStartSession()
  const session = useSession(sessionId)
  const extract = useExtract(sessionId)
  const answer = useAnswerSlot(sessionId)
  const approve = useApprove(sessionId)
  const dispatch = useDispatch(sessionId)

  const state = session.data
  const missingRequired = state?.missing_required ?? []
  const complete = Boolean(state) && missingRequired.length === 0

  const brief = useBrief(sessionId, complete)
  const review = useReview(sessionId, complete)

  useEffect(() => {
    if (state?.next_question) {
      asked.current.set(state.next_question.slot_id, state.next_question)
    }
  }, [state?.next_question])

  // Extraction is fired once per session, after it exists. It is additive: if
  // it fails, the session is unaffected and every question simply gets asked.
  useEffect(() => {
    if (!sessionId || extractRan) return
    setExtractRan(true)
    extract.mutate(undefined, {
      onSuccess: (result) => {
        setPrefills(result.prefills ?? [])
        setGaps(result.gaps ?? [])
        setExtractionUnavailable(Boolean(result.extraction_unavailable))
      },
      onError: () => {
        setExtractionUnavailable(true)
      },
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, extractRan])

  const answers = useMemo(
    () => (state?.answers ?? {}) as Record<string, unknown>,
    [state?.answers],
  )

  const currentQuestion: Question | null = editingSlot
    ? (asked.current.get(editingSlot) ?? null)
    : (state?.next_question ?? null)

  // A pre-fill only ever attaches to a slot that has NOT been answered. Once an
  // answer exists, the proposal has served its purpose and is gone.
  const currentPrefill =
    currentQuestion && !(currentQuestion.slot_id in answers)
      ? prefills.find((p) => p.slot_id === currentQuestion.slot_id)
      : undefined

  function startSession() {
    const text = hypothesis.trim()
    if (!text) return
    start.mutate(text, {
      onSuccess: (created) => {
        asked.current = new Map()
        if (created.next_question) asked.current.set(created.next_question.slot_id, created.next_question)
        setPrefills([])
        setGaps([])
        setExtractionUnavailable(false)
        setExtractRan(false)
        setDispatchResult(null)
        setDispatchError(null)
        setStaleMessage(null)
        setSessionId(created.session_id)
      },
    })
  }

  function submitAnswer(slotId: string, value: unknown) {
    setAnswerError(null)
    setStaleMessage(null)
    answer.mutate(
      { slot_id: slotId, value },
      {
        onSuccess: () => setEditingSlot(null),
        onError: (err) => setAnswerError(messageFor(err, 'Could not save that answer.')),
      },
    )
  }

  function submitApproval(configHash: string) {
    setStaleMessage(null)
    approve.mutate(configHash, {
      onError: (err) => {
        if (err instanceof ApiRequestError && err.code === 'stale_brief') {
          // An answer changed since this brief was rendered. Re-read, do not
          // retry with a different hash.
          void brief.refetch()
          setStaleMessage(
            'An answer changed after that brief was rendered, so approval was refused. ' +
              'The current brief is below — read it and approve again.',
          )
        }
      },
    })
  }

  function runIt() {
    setDispatchError(null)
    dispatch.mutate(undefined, {
      onSuccess: (result) => setDispatchResult(result),
      onError: (err) => {
        setDispatchError(messageFor(err, 'Could not start the run.'))
        if (err instanceof ApiRequestError && err.code === 'approval_mismatch') {
          void brief.refetch()
        }
      },
    })
  }

  // ── start screen ───────────────────────────────────────────────────────────

  if (!sessionId) {
    return (
      <div className="mx-auto max-w-3xl space-y-6">
        <header>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
            <Sparkles className="h-6 w-6" />
            Hypothesis chat
          </h1>
          <p className="mt-1 text-muted-foreground">
            State an idea in plain English. You will be asked a fixed sequence of scoping questions,
            shown a brief rendered from the exact config that will run, and asked to approve it. It
            produces an ordinary experiment — the same tables, the same runner as the{' '}
            <Link to="/experiments/new" className="underline underline-offset-4">
              wizard
            </Link>
            .
          </p>
        </header>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">What do you think is true?</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Label htmlFor="hypothesis" className="sr-only">
              Hypothesis
            </Label>
            <Textarea
              id="hypothesis"
              rows={3}
              value={hypothesis}
              onChange={(e) => setHypothesis(e.target.value)}
              placeholder={`e.g. ${EXAMPLE}`}
              data-testid="hypothesis-input"
            />
            <div className="flex flex-wrap items-center gap-2">
              <Button
                onClick={startSession}
                disabled={!hypothesis.trim() || start.isPending}
                data-testid="start-session"
              >
                {start.isPending ? 'Starting…' : 'Start scoping'}
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
              <Button variant="ghost" onClick={() => setHypothesis(EXAMPLE)} type="button">
                Use the example
              </Button>
            </div>
            {start.isError && (
              <Alert variant="destructive">
                <AlertDescription>
                  {messageFor(start.error, 'Could not start a scoping session.')}
                </AlertDescription>
              </Alert>
            )}
          </CardContent>
        </Card>
      </div>
    )
  }

  // ── session ────────────────────────────────────────────────────────────────

  if (session.isLoading && !state) return <LoadingState rows={6} />
  if (session.isError && !state) {
    return (
      <ErrorState
        error={session.error}
        context="this scoping session"
        onRetry={() => void session.refetch()}
      />
    )
  }
  if (!state) return null

  const answeredIds = Object.keys(answers)
  const dispatched = state.status === 'dispatched' || Boolean(dispatchResult)

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
            <Sparkles className="h-6 w-6" />
            Hypothesis chat
          </h1>
          <div className="flex items-center gap-2">
            <Badge variant="outline">{state.status}</Badge>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setSessionId(null)
                setHypothesis('')
              }}
            >
              New hypothesis
            </Button>
          </div>
        </div>
        <blockquote className="rounded-md border-l-4 bg-muted/50 p-3 text-sm italic">
          “{state.hypothesis_text}”
        </blockquote>
      </header>

      {extractionUnavailable && (
        <Alert variant="info" data-testid="extraction-unavailable">
          <Info className="h-4 w-4" />
          <AlertDescription>
            No suggestions were read from your hypothesis — the extractor is unavailable. This is not
            an error: every question is simply asked normally, and the session completes the same way.
          </AlertDescription>
        </Alert>
      )}

      <CapabilityGapNotice gaps={gaps} />

      {/* Answered so far — the transcript. Editing is re-answering the slot. */}
      {answeredIds.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Answered ({answeredIds.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="divide-y">
            {answeredIds.map((slotId) => {
              const meta = asked.current.get(slotId)
              return (
                <div
                  key={slotId}
                  className="flex flex-wrap items-start justify-between gap-2 py-2 first:pt-0 last:pb-0"
                  data-testid="answered-slot"
                  data-slot-id={slotId}
                >
                  <div className="min-w-0 flex-1">
                    <p className="flex items-center gap-1.5 text-sm font-medium">
                      <CheckCircle2 className="h-3.5 w-3.5 text-green-600" />
                      {meta?.question ?? slotId}
                    </p>
                    <p className="mt-0.5 truncate text-sm text-muted-foreground">
                      {summarise(answers[slotId])}
                    </p>
                  </div>
                  {meta && !dispatched && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setEditingSlot(slotId)}
                      disabled={editingSlot === slotId}
                    >
                      <Pencil className="mr-2 h-3.5 w-3.5" />
                      Re-answer
                    </Button>
                  )}
                </div>
              )
            })}
          </CardContent>
        </Card>
      )}

      {/* The question on the table. */}
      {currentQuestion && !dispatched && (
        <SlotPrompt
          key={`${currentQuestion.slot_id}-${editingSlot ? 'edit' : 'ask'}`}
          question={currentQuestion}
          prefill={currentPrefill}
          submitting={answer.isPending}
          submitError={answerError}
          onAnswer={(value) => submitAnswer(currentQuestion.slot_id, value)}
          onCancelEdit={editingSlot ? () => setEditingSlot(null) : undefined}
        />
      )}

      {!currentQuestion && !complete && (
        <Alert variant="warning">
          <AlertDescription>
            Every question has been put to you, but{' '}
            {missingRequired.length === 1 ? 'one required answer is' : 'some required answers are'}{' '}
            still blank: {missingRequired.join(', ')}. Re-answer{' '}
            {missingRequired.length === 1 ? 'it' : 'them'} above.
          </AlertDescription>
        </Alert>
      )}

      {/* Advisory. Never gates the buttons below. */}
      {complete && (
        <GovernorPanel review={review.data} isLoading={review.isLoading} error={review.error} />
      )}

      <BriefPreview
        brief={brief.data}
        isLoading={brief.isLoading}
        isFetching={brief.isFetching}
        error={brief.error}
        onRefetch={() => void brief.refetch()}
        missingRequired={missingRequired}
        approvedHash={state.approved_hash}
        onApprove={submitApproval}
        approving={approve.isPending}
        staleMessage={staleMessage}
        approveError={approve.error}
      />

      {/* Run it. */}
      {complete && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <PlayCircle className="h-4 w-4" />
              Run it
            </CardTitle>
            <p className="text-sm text-muted-foreground">
              Dispatch recomputes the hash from your answers and refuses anything that does not match
              what you approved. The governor is not consulted here — a{' '}
              <span className="font-medium">reconsider</span> verdict does not stop you.
            </p>
          </CardHeader>
          <CardContent className="space-y-3">
            {dispatchResult ? (
              <Alert variant="success" data-testid="dispatch-success">
                <CheckCircle2 className="h-4 w-4" />
                <AlertDescription className="space-y-2">
                  <p>
                    Running. Experiment{' '}
                    <code className="font-mono text-xs">{dispatchResult.experiment_id}</code>, run{' '}
                    <code className="font-mono text-xs">{dispatchResult.run_id}</code>.
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <Button asChild size="sm">
                      <Link to={`/experiments/${dispatchResult.experiment_id}`}>
                        <FlaskConical className="mr-2 h-4 w-4" />
                        Open the experiment
                      </Link>
                    </Button>
                    <Button asChild size="sm" variant="outline">
                      <Link to="/experiments">See it in the list</Link>
                    </Button>
                  </div>
                </AlertDescription>
              </Alert>
            ) : (
              <>
                <Button
                  onClick={runIt}
                  disabled={dispatch.isPending || !state.approved_hash}
                  data-testid="dispatch-button"
                >
                  {dispatch.isPending ? 'Starting…' : 'Create the experiment and run it'}
                </Button>
                {!state.approved_hash && (
                  <p className="text-sm text-muted-foreground">
                    Approve the brief first — the server refuses a dispatch it has no approval for.
                  </p>
                )}
              </>
            )}

            {dispatchError && (
              <Alert variant="destructive">
                <AlertDescription>{dispatchError}</AlertDescription>
              </Alert>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
