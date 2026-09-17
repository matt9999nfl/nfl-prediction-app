/**
 * "Why this pick" panel — the game detail page's per-game explanation
 * (PROMPT-PICK-EXPLANATIONS-AND-EDGE-LAB.md STAGE 1.8).
 *
 * Top 5 drivers as a signed bar chart (toward pick / against pick, each with
 * raw value and league percentile, imputed values marked), the family
 * matchup view underneath. Renders nothing while loading or on any error —
 * an older pick with no stored explanation yet is a normal state, not a
 * failure the user needs to see.
 */
import { useGameExplanation } from '@/api/queries'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { ExplanationFeature } from '@/api/types'

interface WhyThisPickProps {
  gameId: string
  homeTeam: string
  awayTeam: string
}

export function WhyThisPick({ gameId, homeTeam, awayTeam }: WhyThisPickProps) {
  const { data, isLoading, isError } = useGameExplanation(gameId)

  if (isLoading || isError || !data) return null

  const maxAbs = Math.max(
    1e-9,
    ...data.top_drivers.map((d) => Math.abs(d.pick_direction_contribution)),
  )
  // The heading always names the live pick, never this explanation's own
  // (possibly wrong) model lean — see side_matches_live_pick below.
  const pickedTeam = data.live_predicted_side === 'home' ? homeTeam : awayTeam
  const explanationLeansTeam = data.predicted_side === 'home' ? homeTeam : awayTeam

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <CardTitle className="text-base">Why this pick — {pickedTeam}</CardTitle>
          {data.is_approximate && (
            <Badge variant="warning" className="text-xs">Approximate</Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {data.is_approximate && (
          <p className="text-xs text-muted-foreground">
            This model could not be reproduced exactly for this pick
            {data.reproduction_max_diff !== null &&
              ` (max diff ${data.reproduction_max_diff.toFixed(3)})`}
            . These drivers are an approximation, not the model that made the live pick.
          </p>
        )}
        {!data.side_matches_live_pick && (
          <p className="text-xs text-red-600 dark:text-red-400 font-medium">
            The approximate model leans toward {explanationLeansTeam}. These drivers
            don't explain this pick.
          </p>
        )}

        {/* Top 5 drivers */}
        <div className="space-y-2.5">
          {data.top_drivers.map((driver) => (
            <DriverBar key={driver.feature} driver={driver} maxAbs={maxAbs} />
          ))}
        </div>

        {/* Family matchup */}
        {data.family_matchup.length > 0 && (
          <div>
            <p className="text-xs font-medium text-muted-foreground mb-2">Family matchup</p>
            <div className="space-y-1.5">
              {data.family_matchup
                .slice()
                .sort((a, b) => Math.abs(b.net) - Math.abs(a.net))
                .map((m) => (
                  <div key={m.family} className="flex items-center justify-between text-xs gap-2">
                    <span className="text-muted-foreground">{m.family}</span>
                    <span className="tabular-nums text-right">
                      {awayTeam} {m.away_contribution >= 0 ? '+' : ''}
                      {m.away_contribution.toFixed(2)}
                      {'  ·  '}
                      {homeTeam} {m.home_contribution >= 0 ? '+' : ''}
                      {m.home_contribution.toFixed(2)}
                    </span>
                  </div>
                ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function DriverBar({ driver, maxAbs }: { driver: ExplanationFeature; maxAbs: number }) {
  const toward = driver.pick_direction_contribution >= 0
  const widthPct = Math.min(100, (Math.abs(driver.pick_direction_contribution) / maxAbs) * 100)
  return (
    <div className="text-xs">
      <div className="flex items-center justify-between mb-1 gap-2">
        <span className="font-medium">
          {driver.family}
          <span className="text-muted-foreground font-normal"> · {driver.feature}</span>
          {driver.side !== 'game' && (
            <span className="text-muted-foreground font-normal"> ({driver.side})</span>
          )}
          {driver.was_imputed && (
            <span
              className="ml-1 text-muted-foreground"
              title="Value was imputed — missing input data"
            >
              *
            </span>
          )}
        </span>
        <span className="text-muted-foreground tabular-nums shrink-0">
          {driver.raw_value !== null ? driver.raw_value.toFixed(3) : '—'}
          {driver.league_pctile !== null && ` (${Math.round(driver.league_pctile)}th pctile)`}
        </span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
        <div
          className={cn('h-full rounded-full', toward ? 'bg-emerald-500' : 'bg-red-500')}
          style={{ width: `${widthPct}%` }}
        />
      </div>
    </div>
  )
}
