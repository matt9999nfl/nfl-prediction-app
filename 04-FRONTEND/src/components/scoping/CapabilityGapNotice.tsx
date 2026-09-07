/**
 * Capability gaps — the two kinds, kept apart.
 *
 * PHASE6_STATUS.md, S3: the plan's original criterion (one gap for OL weight,
 * none for weather) was wrong and the implementation was left correct. Gaps come
 * back classified in `why_unavailable`:
 *
 *   feature_catalog — the measurement does not exist at all. Closing it means
 *                     loading data.
 *   filter_schema   — it exists as a model feature, but the game universe cannot
 *                     be restricted by it. Closing it means widening a schema;
 *                     and Matt can often work around it now by changing the
 *                     slice or accepting it as an input instead.
 *
 * Those are different situations with different costs, so they are not collapsed
 * into one "not supported" message.
 */

import { Database, Filter, HelpCircle } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { CapabilityGap } from '@/api/scoping'

const KIND_FEATURE_CATALOG = 'feature_catalog'
const KIND_FILTER_SCHEMA = 'filter_schema'

interface Presentation {
  icon: typeof Database
  heading: string
  meaning: string
  cost: string
  tone: string
  badge: 'warning' | 'info' | 'muted'
}

function presentationFor(why: string): Presentation {
  if (why === KIND_FEATURE_CATALOG) {
    return {
      icon: Database,
      heading: 'Not measured anywhere',
      meaning:
        'No feature in the catalog carries this. The platform cannot express it as an input or as a slice.',
      cost: 'Closing this needs data loaded and a feature defined — it is not something to work around in this experiment.',
      tone: 'border-amber-300 bg-amber-50',
      badge: 'warning',
    }
  }
  if (why === KIND_FILTER_SCHEMA) {
    return {
      icon: Filter,
      heading: 'Exists as a feature, not as a slice',
      meaning:
        'The measurement exists and can be given to the model as an input. What it cannot do is restrict which games are trained on and evaluated.',
      cost: 'You can proceed now by choosing a different slice, or by accepting it as an input — but “X holds when Y” is not what that asks.',
      tone: 'border-blue-300 bg-blue-50',
      badge: 'info',
    }
  }
  return {
    icon: HelpCircle,
    heading: why,
    meaning: 'The API classified this gap in a way this page does not yet describe.',
    cost: 'Recorded as-is rather than flattened into a generic message.',
    tone: 'border-muted-foreground/30 bg-muted',
    badge: 'muted',
  }
}

export function CapabilityGapNotice({ gaps }: { gaps: CapabilityGap[] }) {
  if (!gaps.length) return null

  return (
    <Card data-testid="capability-gaps">
      <CardHeader>
        <CardTitle className="text-base">
          What this hypothesis asks for that the platform cannot express
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          {gaps.length === 1 ? 'One gap was' : `${gaps.length} gaps were`} recorded. They do not stop
          you running the experiment — they tell you what the run will not answer.
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        {gaps.map((gap) => {
          const p = presentationFor(gap.why_unavailable)
          const Icon = p.icon
          return (
            <div
              key={gap.gap_id}
              className={`rounded-md border p-4 ${p.tone}`}
              data-testid="capability-gap"
              data-gap-kind={gap.why_unavailable}
            >
              <div className="flex flex-wrap items-center gap-2">
                <Icon className="h-4 w-4" />
                <span className="font-semibold">{gap.requested_concept}</span>
                <Badge variant={p.badge}>{p.heading}</Badge>
                <Badge variant="outline" className="font-mono text-[10px]">
                  {gap.why_unavailable}
                </Badge>
              </div>

              <p className="mt-2 text-sm">{p.meaning}</p>

              <dl className="mt-3 space-y-2 text-sm">
                <div>
                  <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Nearest expressible
                  </dt>
                  <dd className="mt-0.5">
                    {gap.nearest_expressible ?? (
                      <span className="text-muted-foreground">
                        Nothing in the catalog comes close — none recorded.
                      </span>
                    )}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Suggested definition
                  </dt>
                  <dd className="mt-0.5">
                    {gap.suggested_definition ?? (
                      <span className="text-muted-foreground">None recorded.</span>
                    )}
                  </dd>
                </div>
              </dl>

              <p className="mt-3 text-xs text-muted-foreground">{p.cost}</p>
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}
