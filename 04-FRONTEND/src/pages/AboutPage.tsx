/**
 * About — /about
 *
 * Explains what the platform is, what hypothesis is being tested,
 * what the actual backtest results show, and what gate_passed means.
 * Hardcoded — this is editorial content, not API-driven.
 */

import { Link } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Activity, FlaskConical, ShieldAlert, TrendingUp } from 'lucide-react'

export function AboutPage() {
  return (
    <div className="max-w-2xl space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">About this platform</h1>
        <p className="text-muted-foreground text-sm mt-1">
          What it does, what it's testing, and where it stands
        </p>
      </div>

      {/* What it is */}
      <Section icon={<Activity className="h-5 w-5" />} title="What this is">
        <p>
          A self-service NFL prediction experimentation platform. You upload a
          dataset, configure an experiment — pick a target outcome, select
          features, define success criteria — run a walk-forward backtest, and
          see the results.
        </p>
        <p>
          The platform is built for one use case: testing whether a specific
          signal (an edge) beats the closing spread over a large, multi-season
          sample. It is not a gambling tool. It is a structured way to ask
          whether a hypothesis is real.
        </p>
      </Section>

      <Separator />

      {/* The hypothesis */}
      <Section icon={<FlaskConical className="h-5 w-5" />} title="What's being tested">
        <p>
          The starting hypothesis is that <strong>offensive line performance
          mismatches</strong> — specifically a team with a top-quartile OL
          facing a team with a bottom-quartile pass-rush defense — produce
          exploitable edges in the ATS market.
        </p>
        <p>
          The intuition: OL quality is underweighted by the market because it's
          hard to observe directly. nflfastR provides EPA-based OL metrics
          (pass-block EPA per attempt, pressure proxy rate, sack rate, rush
          EPA per attempt) that can be computed in-season. If those metrics
          predict ATS cover at a rate above 54% over a large sample, there may
          be a real signal.
        </p>
        <p>
          The 54% threshold is not arbitrary — it represents approximately the
          break-even point against vig at standard -110 lines, with meaningful
          margin above noise.
        </p>
      </Section>

      <Separator />

      {/* Current results */}
      <Section icon={<TrendingUp className="h-5 w-5" />} title="Current results">
        <p>Two experiments have been run. Neither cleared the gate.</p>

        <div className="space-y-3 mt-2">
          <ExperimentResult
            name="ol_xgb_v1"
            description="12 OL and game-context features. XGBoost, walk-forward 2015–2024."
            record="773–784–42"
            hitRate="48.68%"
            gate={false}
            note="0.1pp lift over the always-home baseline. Feature importance flat across all 12 features — no dominant signal."
          />
          <ExperimentResult
            name="ol_xgb_v2"
            description="52 features — added QB efficiency, explosive rates, team defense, rest/travel, and form. Same methodology."
            record="773–784–42 (1,557 W+L)"
            hitRate="49.65%"
            gate={false}
            note="+0.96pp over v1. Feature importance still flat (0.018–0.022 range). Best fold: 52.5% (2022). Worst: 46.5% (2023). High variance, no consistent season-to-season signal."
          />
        </div>

        <Alert variant="warning" className="mt-4">
          <ShieldAlert className="h-4 w-4" />
          <AlertDescription>
            The OL mismatch subset specifically underperformed: the top-quartile
            home OL vs. weak away defense filter hit 43.8% on 64 games in v2
            (down from 51.6% in v1). At 64 games that's statistically
            inconclusive — but the direction suggests the v1 result was noise,
            not signal.
          </AlertDescription>
        </Alert>
      </Section>

      <Separator />

      {/* What gate_passed means */}
      <Section icon={<ShieldAlert className="h-5 w-5" />} title="What 'gate passed' means">
        <p>
          Each experiment defines its own success criteria before it runs —
          a primary metric, a threshold, and a minimum sample size. The most
          common gate is:
        </p>
        <ul className="list-disc list-inside space-y-1 text-sm text-muted-foreground ml-2">
          <li>ATS hit rate ≥ 54%</li>
          <li>On at least 250 non-push games</li>
        </ul>
        <p>
          When an experiment clears its own gate, <code className="text-xs bg-muted px-1 rounded">gate_passed = true</code> is
          set on that experiment's record. The evaluation banner at the top of
          every page disappears on that experiment's detail view. Nothing is
          flagged as production-ready until this happens.
        </p>
        <p>
          No experiment has cleared the gate yet. Predictions from completed
          experiments are backtested results — useful for understanding model
          behavior, not for betting.
        </p>

        <div className="flex gap-3 mt-4">
          <Link to="/model">
            <Button variant="outline" size="sm">
              <Activity className="mr-2 h-4 w-4" />
              View experiment log
            </Button>
          </Link>
          <Link to="/experiments/new">
            <Button variant="outline" size="sm">
              <FlaskConical className="mr-2 h-4 w-4" />
              Run a new experiment
            </Button>
          </Link>
        </div>
      </Section>
    </div>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

function Section({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode
  title: string
  children: React.ReactNode
}) {
  return (
    <section className="space-y-3">
      <h2 className="flex items-center gap-2 text-lg font-semibold">
        {icon}
        {title}
      </h2>
      <div className="space-y-3 text-sm leading-relaxed text-foreground [&_p]:text-muted-foreground [&_strong]:text-foreground">
        {children}
      </div>
    </section>
  )
}

function ExperimentResult({
  name,
  description,
  record,
  hitRate,
  gate,
  note,
}: {
  name: string
  description: string
  record: string
  hitRate: string
  gate: boolean
  note: string
}) {
  return (
    <Card>
      <CardHeader className="pb-2 pt-4">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <CardTitle className="text-sm font-mono">{name}</CardTitle>
          <Badge variant={gate ? 'success' : 'warning'}>
            {gate ? 'Gate passed ✓' : 'Gate not passed'}
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground mt-1">{description}</p>
      </CardHeader>
      <CardContent className="pb-4 space-y-2">
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-xs text-muted-foreground">ATS record</p>
            <p className="font-semibold tabular-nums">{record}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Hit rate</p>
            <p className="font-semibold tabular-nums">{hitRate}</p>
          </div>
        </div>
        <p className="text-xs text-muted-foreground border-t pt-2">{note}</p>
      </CardContent>
    </Card>
  )
}
