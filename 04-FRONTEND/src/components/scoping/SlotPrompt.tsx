/**
 * One question from the scoping tree.
 *
 * Two things this component exists to get right:
 *
 * 1. It renders from tree metadata — `type` and `options_from` — and nothing
 *    else. There is no switch on a slot id, no hardcoded feature or filter
 *    field. `schema:` options are read from the API's own JSON Schema at
 *    ask-time, so widening GameUniverseFilter widens this form with no edit.
 *
 * 2. A PRE-FILL IS NEVER AN ANSWER (ADR-012). When one is present the question
 *    is still asked: the control arrives populated, wrapped in a visibly
 *    unconfirmed panel carrying the words from the hypothesis that produced it,
 *    and the primary action reads "Confirm" rather than "Save". Nothing is sent
 *    to /answers until Matt acts.
 */

import { useEffect, useMemo, useState } from 'react'
import { Check, Quote, Sparkles, Undo2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { Checkbox } from '@/components/ui/checkbox'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { LoadingState } from '@/components/LoadingState'
import { ErrorState } from '@/components/ErrorState'
import {
  parseOptionsFrom,
  useEndpointOptions,
  useObjectSchema,
  type EndpointOption,
  type JsonSchemaProperty,
  type Prefill,
  type Question,
} from '@/api/scoping'

// ── helpers ──────────────────────────────────────────────────────────────────

const same = (a: unknown, b: unknown) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null)

/** Identity of a selected option value, matching `toEndpointOption` in the client. */
function optionIdOf(value: unknown): string {
  if (value && typeof value === 'object') {
    const v = value as Record<string, unknown>
    if (typeof v.dataset === 'string' && typeof v.column === 'string') {
      return `${v.dataset}.${v.column}`
    }
  }
  return String(value)
}

function coerceScalar(raw: string, type: string | undefined): unknown {
  if (raw === '') return null
  if (type === 'boolean') return raw === 'true'
  if (type === 'integer') {
    const n = Number.parseInt(raw, 10)
    return Number.isNaN(n) ? null : n
  }
  if (type === 'number') {
    const n = Number.parseFloat(raw)
    return Number.isNaN(n) ? null : n
  }
  return raw
}

/**
 * Type a value the way a union of primitives permits, from what was typed.
 * Structural only — it knows nothing about which field is which.
 */
function coerceUnion(raw: string, types: string[]): unknown {
  if (raw === '') return null
  const lowered = raw.trim().toLowerCase()
  if (types.includes('boolean') && (lowered === 'true' || lowered === 'false')) {
    return lowered === 'true'
  }
  if (types.includes('integer') && /^-?\d+$/.test(raw.trim())) return Number.parseInt(raw, 10)
  if (types.includes('number') && raw.trim() !== '' && !Number.isNaN(Number(raw))) return Number(raw)
  if (types.includes('string')) return raw
  return raw
}

// ── props ────────────────────────────────────────────────────────────────────

interface SlotPromptProps {
  question: Question
  /** The unconfirmed proposal for this slot, if the extractor produced one. */
  prefill?: Prefill
  submitting: boolean
  submitError?: string | null
  onAnswer: (value: unknown) => void
  /** Present when re-answering an already-answered slot. */
  onCancelEdit?: () => void
}

export function SlotPrompt({
  question,
  prefill,
  submitting,
  submitError,
  onAnswer,
  onCancelEdit,
}: SlotPromptProps) {
  const source = useMemo(() => parseOptionsFrom(question.options_from), [question.options_from])

  const endpointQuery = useEndpointOptions(source?.kind === 'endpoint' ? source.path : null)
  const schemaQuery = useObjectSchema(source?.kind === 'schema' ? source.name : null)

  const seed = prefill ? prefill.value : (question.default ?? null)
  const [draft, setDraft] = useState<unknown>(seed)
  const [search, setSearch] = useState('')
  const [objectText, setObjectText] = useState(() =>
    seed && typeof seed === 'object' ? JSON.stringify(seed, null, 2) : '{}',
  )
  const [objectError, setObjectError] = useState<string | null>(null)

  // Reset when the server moves us to a different question.
  useEffect(() => {
    const next = prefill ? prefill.value : (question.default ?? null)
    setDraft(next)
    setSearch('')
    setObjectText(next && typeof next === 'object' ? JSON.stringify(next, null, 2) : '{}')
    setObjectError(null)
  }, [question.slot_id, prefill])

  const hasPrefill = Boolean(prefill)
  const untouched = hasPrefill && same(draft, prefill?.value)
  const confidence =
    typeof prefill?.confidence === 'number' ? Math.round(prefill.confidence * 100) : null

  function submit() {
    if (question.type === 'object') {
      try {
        const parsed = objectText.trim() === '' ? {} : (JSON.parse(objectText) as unknown)
        setObjectError(null)
        onAnswer(parsed)
      } catch {
        setObjectError('That is not valid JSON.')
      }
      return
    }
    onAnswer(draft)
  }

  // ── controls, driven by question.type ──────────────────────────────────────

  function renderControl() {
    switch (question.type) {
      case 'text':
        return (
          <Textarea
            id={`slot-${question.slot_id}`}
            rows={3}
            value={typeof draft === 'string' ? draft : ''}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Your answer…"
          />
        )

      case 'integer':
      case 'float':
        return (
          <Input
            id={`slot-${question.slot_id}`}
            type="number"
            step={question.type === 'integer' ? 1 : 'any'}
            value={typeof draft === 'number' || typeof draft === 'string' ? String(draft) : ''}
            onChange={(e) =>
              setDraft(coerceScalar(e.target.value, question.type === 'integer' ? 'integer' : 'number'))
            }
          />
        )

      case 'enum': {
        if (source?.kind !== 'literal') {
          return <p className="text-sm text-destructive">This question declares no options.</p>
        }
        return (
          <Select
            id={`slot-${question.slot_id}`}
            value={typeof draft === 'string' ? draft : ''}
            onChange={(e) => setDraft(e.target.value || null)}
          >
            <option value="">{question.required ? 'Choose…' : 'No preference'}</option>
            {source.values.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </Select>
        )
      }

      case 'multi_select':
        return renderMultiSelect()

      case 'filter':
        return renderFilter()

      case 'object':
        return (
          <div className="space-y-2">
            <Textarea
              id={`slot-${question.slot_id}`}
              rows={4}
              className="font-mono text-xs"
              value={objectText}
              onChange={(e) => setObjectText(e.target.value)}
              spellCheck={false}
            />
            {objectError && <p className="text-sm text-destructive">{objectError}</p>}
          </div>
        )

      default:
        // A tree that grows a new slot type should say so, not fail silently.
        return (
          <Alert variant="warning">
            <AlertDescription>
              This question is of type <code className="font-mono">{question.type}</code>, which this
              page does not yet render. Answer it in the wizard, or ask PROJECT-LEAD to extend the
              chat.
            </AlertDescription>
          </Alert>
        )
    }
  }

  function renderMultiSelect() {
    if (source?.kind !== 'endpoint') {
      return <p className="text-sm text-destructive">This question declares no options source.</p>
    }
    if (endpointQuery.isLoading) return <LoadingState rows={3} />
    if (endpointQuery.isError) {
      return <ErrorState error={endpointQuery.error} context="the options for this question" onRetry={() => void endpointQuery.refetch()} />
    }

    const options = endpointQuery.data ?? []
    const selectedValues = Array.isArray(draft) ? (draft as unknown[]) : []
    const selectedIds = new Set(selectedValues.map(optionIdOf))

    const needle = search.trim().toLowerCase()
    const visible = needle
      ? options.filter(
          (o) =>
            o.label.toLowerCase().includes(needle) ||
            (o.description ?? '').toLowerCase().includes(needle),
        )
      : options

    const groups = new Map<string, EndpointOption[]>()
    for (const o of visible) {
      const g = o.group ?? ''
      groups.set(g, [...(groups.get(g) ?? []), o])
    }

    function toggle(option: EndpointOption) {
      const id = option.id
      const next = selectedIds.has(id)
        ? selectedValues.filter((v) => optionIdOf(v) !== id)
        : [...selectedValues, option.value]
      setDraft(next)
    }

    return (
      <div className="space-y-3">
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={`Search ${options.length} options…`}
        />
        <div className="max-h-72 space-y-4 overflow-y-auto rounded-md border p-3">
          {[...groups.entries()].map(([group, items]) => (
            <div key={group || 'ungrouped'} className="space-y-1.5">
              {group && (
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {group}
                </p>
              )}
              {items.map((o) => (
                <label
                  key={o.id}
                  className="flex cursor-pointer items-start gap-2 rounded px-1 py-1 hover:bg-accent"
                >
                  <Checkbox
                    checked={selectedIds.has(o.id)}
                    onCheckedChange={() => toggle(o)}
                    className="mt-0.5"
                  />
                  <span className="min-w-0">
                    <span className="block text-sm font-medium">{o.label}</span>
                    {o.description && (
                      <span className="block text-xs text-muted-foreground">{o.description}</span>
                    )}
                  </span>
                </label>
              ))}
            </div>
          ))}
          {visible.length === 0 && (
            <p className="py-4 text-center text-sm text-muted-foreground">Nothing matches “{search}”.</p>
          )}
        </div>
        {/* P5-08: mirroring is a property of the platform, so say it here too. */}
        <p className="text-sm text-muted-foreground">
          <span className="font-medium text-foreground">{selectedValues.length} selected</span> ·{' '}
          {selectedValues.length * 2} features in the model — each selection is mirrored home/away.
        </p>
      </div>
    )
  }

  function renderFilter() {
    if (source?.kind !== 'schema') {
      return <p className="text-sm text-destructive">This question declares no schema source.</p>
    }
    if (schemaQuery.isLoading) return <LoadingState rows={2} />
    if (schemaQuery.isError) {
      return (
        <ErrorState
          error={schemaQuery.error}
          context={`the ${source.name} schema`}
          onRetry={() => void schemaQuery.refetch()}
        />
      )
    }

    const schema = schemaQuery.data
    if (!schema) return null

    const active = draft !== null && typeof draft === 'object'
    const current = (active ? draft : {}) as Record<string, unknown>

    function setField(key: string, value: unknown) {
      setDraft({ ...current, [key]: value })
    }

    function renderProperty(key: string, prop: JsonSchemaProperty) {
      const value = current[key]
      const label = prop.title ?? key

      if (prop.enum && prop.enum.length) {
        return (
          <div key={key} className="space-y-1">
            <Label htmlFor={`f-${key}`}>{label}</Label>
            <Select
              id={`f-${key}`}
              value={typeof value === 'string' ? value : ''}
              onChange={(e) => setField(key, e.target.value || null)}
            >
              <option value="">Choose…</option>
              {prop.enum.map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </Select>
          </div>
        )
      }

      // A union of primitives (e.g. boolean | integer). Which type belongs with
      // which field is a rule in a Pydantic validator, not in the schema, so this
      // does not guess a field-to-type mapping: it takes what is typed and gives
      // it the JSON type the schema permits — "true" becomes a boolean, "15"
      // becomes an integer — and leaves the server to reject anything invalid.
      const types = prop.anyOfTypes ?? (prop.type ? [prop.type] : ['string'])

      if (types.length === 1) {
        const only = types[0]
        if (only === 'boolean') {
          return (
            <div key={key} className="space-y-1">
              <Label htmlFor={`f-${key}`}>{label}</Label>
              <Select
                id={`f-${key}`}
                value={value === true ? 'true' : value === false ? 'false' : ''}
                onChange={(e) => setField(key, coerceScalar(e.target.value, 'boolean'))}
              >
                <option value="">Choose…</option>
                <option value="true">true</option>
                <option value="false">false</option>
              </Select>
            </div>
          )
        }
        return (
          <div key={key} className="space-y-1">
            <Label htmlFor={`f-${key}`}>{label}</Label>
            <Input
              id={`f-${key}`}
              type={only === 'integer' || only === 'number' ? 'number' : 'text'}
              step={only === 'integer' ? 1 : 'any'}
              value={value === null || value === undefined ? '' : String(value)}
              onChange={(e) => setField(key, coerceScalar(e.target.value, only))}
            />
          </div>
        )
      }

      return (
        <div key={key} className="space-y-1">
          <Label htmlFor={`f-${key}`}>{label}</Label>
          <Input
            id={`f-${key}`}
            value={value === null || value === undefined ? '' : String(value)}
            onChange={(e) => setField(key, coerceUnion(e.target.value, types))}
            placeholder={types.join(' or ')}
          />
          <p className="text-xs text-muted-foreground">
            Accepts {types.join(' or ')} — typed as you enter it.
          </p>
        </div>
      )
    }

    return (
      <div className="space-y-3">
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            variant={active ? 'outline' : 'default'}
            onClick={() => setDraft(null)}
          >
            No restriction
          </Button>
          <Button
            type="button"
            size="sm"
            variant={active ? 'default' : 'outline'}
            onClick={() => setDraft(current)}
          >
            Restrict the game universe
          </Button>
        </div>
        {active && (
          <div className="grid gap-3 rounded-md border p-3 sm:grid-cols-3">
            {schema.properties.map((p) => renderProperty(p.key, p.schema))}
          </div>
        )}
        {active && (
          <p className="text-xs text-muted-foreground">
            Fields come from the API’s {schema.name} schema. When that schema is widened, the
            choices here widen with it.
          </p>
        )}
      </div>
    )
  }

  // ── frame ──────────────────────────────────────────────────────────────────

  const canSubmit =
    !submitting &&
    (!question.required ||
      question.type === 'object' ||
      (draft !== null &&
        draft !== undefined &&
        draft !== '' &&
        !(Array.isArray(draft) && draft.length === 0)))

  return (
    <div
      className={
        hasPrefill
          ? 'rounded-lg border-2 border-dashed border-blue-400 bg-blue-50/40 p-5'
          : 'rounded-lg border bg-card p-5'
      }
      data-testid="slot-prompt"
      data-slot-id={question.slot_id}
      data-prefilled={hasPrefill ? 'true' : 'false'}
      data-prefill-untouched={untouched ? 'true' : 'false'}
    >
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <Label htmlFor={`slot-${question.slot_id}`} className="text-base font-semibold">
            {question.question}
          </Label>
          {question.help && (
            <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{question.help}</p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {!question.required && <Badge variant="muted">Optional</Badge>}
          <Badge variant="outline" className="font-mono text-[10px]">
            {question.slot_id}
          </Badge>
        </div>
      </div>

      {hasPrefill && (
        <div
          className="mb-4 rounded-md border border-blue-300 bg-blue-100/60 p-3"
          data-testid="prefill-notice"
        >
          <div className="flex flex-wrap items-center gap-2">
            <Sparkles className="h-4 w-4 text-blue-700" />
            <span className="text-sm font-semibold text-blue-900">
              {untouched ? 'Suggested — not yet your answer' : 'Edited from a suggestion'}
            </span>
            {confidence !== null && (
              <Badge variant="info" className="text-[10px]">
                {confidence}% confidence
              </Badge>
            )}
          </div>
          {prefill?.evidence_quote && (
            <p className="mt-2 flex items-start gap-1.5 text-sm italic text-blue-900">
              <Quote className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>“{prefill.evidence_quote}”</span>
            </p>
          )}
          <p className="mt-2 text-xs text-blue-900/80">
            Read from your hypothesis. It is not recorded until you confirm it, and you can change it
            first.
          </p>
        </div>
      )}

      {renderControl()}

      {submitError && (
        <Alert variant="destructive" className="mt-4">
          <AlertDescription>{submitError}</AlertDescription>
        </Alert>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button type="button" onClick={submit} disabled={!canSubmit}>
          <Check className="mr-2 h-4 w-4" />
          {untouched ? 'Confirm this answer' : 'Save answer'}
        </Button>

        {hasPrefill && untouched && (
          <Button
            type="button"
            variant="outline"
            onClick={() => setDraft(question.default ?? null)}
            disabled={submitting}
          >
            <Undo2 className="mr-2 h-4 w-4" />
            Clear and answer myself
          </Button>
        )}

        {!question.required && (
          <Button
            type="button"
            variant="ghost"
            onClick={() => onAnswer(null)}
            disabled={submitting}
          >
            Skip
          </Button>
        )}

        {onCancelEdit && (
          <Button type="button" variant="ghost" onClick={onCancelEdit} disabled={submitting}>
            Cancel
          </Button>
        )}
      </div>
    </div>
  )
}
