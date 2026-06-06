/**
 * Team OL rating time series — /teams/:team
 *
 * Fetches GET /api/v1/teams/{team}/ol-rating.
 * Shows rush and pass OL EPA per attempt over time, with season selector.
 *
 * TODO: wire to live endpoint once deployed (BACKEND-API item 3.5)
 * Mock data is used if the endpoint returns an error or is not yet deployed.
 */

import { useState, useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useTeamOLRating } from '@/api/queries'
import { LoadingState } from '@/components/LoadingState'
import { ErrorState } from '@/components/ErrorState'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ArrowLeft } from 'lucide-react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import { teamName } from '@/lib/formatters'

// ── Constants ─────────────────────────────────────────────────────────────────

/** All 32 standard NFL team abbreviations (nflfastR codes). */
export const NFL_TEAMS = [
  'ARI', 'ATL', 'BAL', 'BUF',
  'CAR', 'CHI', 'CIN', 'CLE',
  'DAL', 'DEN', 'DET', 'GB',
  'HOU', 'IND', 'JAX', 'KC',
  'LA',  'LAC', 'LV',  'MIA',
  'MIN', 'NE',  'NO',  'NYG',
  'NYJ', 'PHI', 'PIT', 'SEA',
  'SF',  'TB',  'TEN', 'WAS',
] as const

export type NflTeam = typeof NFL_TEAMS[number]

// ── Page ──────────────────────────────────────────────────────────────────────

export function TeamPage() {
  const { team } = useParams<{ team: string }>()

  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
  } = useTeamOLRating(team ?? '')

  // Derive available seasons and select the most recent by default
  const availableSeasons = useMemo(() => {
    if (!data?.ratings?.length) return []
    const seasons = [...new Set(data.ratings.map((r) => r.season))].sort((a, b) => b - a)
    return seasons
  }, [data])

  const [selectedSeason, setSelectedSeason] = useState<number | null>(null)

  // When data loads, set selected season to the most recent
  const activeSeason = selectedSeason ?? availableSeasons[0] ?? null

  const chartData = useMemo(() => {
    if (!data?.ratings || !activeSeason) return []
    return data.ratings
      .filter((r) => r.season === activeSeason)
      .sort((a, b) => a.week - b.week)
  }, [data, activeSeason])

  const teamAbbr = team?.toUpperCase() ?? ''
  const fullName = teamName(teamAbbr)

  // Latest values for the summary header
  const latestRating = chartData[chartData.length - 1]

  if (isLoading) return <LoadingState rows={5} />

  if (isError) {
    return (
      <ErrorState
        error={error}
        context={`OL rating for team ${teamAbbr}`}
        onRetry={() => void refetch()}
      />
    )
  }

  if (!data) return null

  const hasData = chartData.length > 0

  return (
    <div className="space-y-6">
      {/* Back button */}
      <Link to="/">
        <Button variant="ghost" size="sm" className="-ml-2">
          <ArrowLeft className="mr-2 h-4 w-4" />
          Dashboard
        </Button>
      </Link>

      {/* Header */}
      <div className="space-y-2">
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-2xl font-bold tracking-tight">
            {teamAbbr}
          </h1>
          <span className="text-muted-foreground text-lg">{fullName}</span>
          <Badge variant="outline">OL Rating</Badge>
        </div>

        {/* Current-season summary */}
        {latestRating && (
          <div className="flex flex-wrap gap-4 text-sm">
            <span className="text-muted-foreground">
              {activeSeason} Season · Week {latestRating.week} (most recent)
            </span>
            <span>
              Rush EPA/att:{' '}
              <span className={`font-semibold ${latestRating.ol_rush_epa_per_att >= 0 ? 'text-green-700' : 'text-destructive'}`}>
                {latestRating.ol_rush_epa_per_att.toFixed(3)}
              </span>
            </span>
            <span>
              Pass EPA/att:{' '}
              <span className={`font-semibold ${latestRating.ol_pass_epa_per_att >= 0 ? 'text-green-700' : 'text-destructive'}`}>
                {latestRating.ol_pass_epa_per_att.toFixed(3)}
              </span>
            </span>
          </div>
        )}
      </div>

      {/* Season selector */}
      {availableSeasons.length > 1 && (
        <div className="flex gap-2 flex-wrap">
          {availableSeasons.map((season) => (
            <Button
              key={season}
              variant={season === activeSeason ? 'default' : 'outline'}
              size="sm"
              onClick={() => setSelectedSeason(season)}
            >
              {season}
            </Button>
          ))}
        </div>
      )}

      {/* OL rating chart */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">
            OL EPA per attempt — {activeSeason} season
          </CardTitle>
          <CardDescription>
            Week-by-week offensive line efficiency. Zero = league-average EPA.
            Positive values indicate above-average performance.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!hasData ? (
            <p className="text-sm text-muted-foreground py-6 text-center">
              No OL rating data available for {teamAbbr} in the {activeSeason} season.
            </p>
          ) : (
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis
                  dataKey="week"
                  label={{ value: 'Week', position: 'insideBottom', offset: -2, fontSize: 12 }}
                  tick={{ fontSize: 12 }}
                />
                <YAxis
                  tick={{ fontSize: 12 }}
                  width={52}
                  tickFormatter={(v: number) => v.toFixed(3)}
                />
                {/* Zero reference line = league average EPA */}
                <ReferenceLine
                  y={0}
                  stroke="hsl(var(--muted-foreground))"
                  strokeWidth={1.5}
                  label={{
                    value: 'League avg (0.0)',
                    position: 'insideTopLeft',
                    fontSize: 10,
                    fill: 'hsl(var(--muted-foreground))',
                  }}
                />
                <Tooltip
                  formatter={(value: number, name: string) => [
                    value.toFixed(4),
                    name === 'ol_rush_epa_per_att' ? 'Rush EPA/att' : 'Pass EPA/att',
                  ]}
                  labelFormatter={(label: number) => `Week ${label}`}
                />
                <Legend
                  formatter={(value: string) =>
                    value === 'ol_rush_epa_per_att' ? 'Rush EPA/att' : 'Pass EPA/att'
                  }
                />
                <Line
                  type="monotone"
                  dataKey="ol_rush_epa_per_att"
                  stroke="hsl(var(--primary))"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  activeDot={{ r: 5 }}
                  name="ol_rush_epa_per_att"
                />
                <Line
                  type="monotone"
                  dataKey="ol_pass_epa_per_att"
                  stroke="hsl(var(--destructive))"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  activeDot={{ r: 5 }}
                  name="ol_pass_epa_per_att"
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      {/* Week-by-week data table */}
      {hasData && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Week-by-week data</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-xs text-muted-foreground">
                    <th className="text-left py-2 pr-4">Week</th>
                    <th className="text-right py-2 px-4">Rush EPA/att</th>
                    <th className="text-right py-2 pl-4">Pass EPA/att</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {chartData.map((row) => (
                    <tr key={`${row.season}-${row.week}`}>
                      <td className="py-2 pr-4">{row.week}</td>
                      <td className={`py-2 px-4 text-right tabular-nums font-medium ${row.ol_rush_epa_per_att >= 0 ? 'text-green-700' : 'text-destructive'}`}>
                        {row.ol_rush_epa_per_att.toFixed(4)}
                      </td>
                      <td className={`py-2 pl-4 text-right tabular-nums font-medium ${row.ol_pass_epa_per_att >= 0 ? 'text-green-700' : 'text-destructive'}`}>
                        {row.ol_pass_epa_per_att.toFixed(4)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Team selector */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Browse all teams</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {NFL_TEAMS.map((t) => (
              <Link key={t} to={`/teams/${t}`}>
                <Button
                  variant={t === teamAbbr ? 'default' : 'outline'}
                  size="sm"
                >
                  {t}
                </Button>
              </Link>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
