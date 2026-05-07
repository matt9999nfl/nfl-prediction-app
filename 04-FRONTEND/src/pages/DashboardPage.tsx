/**
 * Dashboard — /
 *
 * Shows this week's games with spread, prediction confidence (if a completed
 * experiment exists), and a summary of the current model state.
 */

import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useGames, useExperiments } from '@/api/queries'
import { GameCard } from '@/components/GameCard'
import { LoadingCards } from '@/components/LoadingState'
import { ErrorState } from '@/components/ErrorState'
import { EmptyState } from '@/components/EmptyState'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Calendar, FlaskConical, Plus } from 'lucide-react'

// Current NFL season — adjust as the calendar advances
const CURRENT_SEASON = new Date().getFullYear()

export function DashboardPage() {
  // Load upcoming/scheduled games for the current season
  const {
    data: gamesData,
    isLoading: gamesLoading,
    isError: gamesError,
    error: gamesErr,
    refetch: refetchGames,
  } = useGames({ season: CURRENT_SEASON, status: 'scheduled', limit: 50 })

  // Load experiments to find any completed ones for confidence overlays
  const { data: experimentsData } = useExperiments({
    status: 'complete',
    limit: 5,
  })

  const games = gamesData?.data ?? []
  const completedExperiments = experimentsData?.data ?? []
  const hasPassedGate = completedExperiments.some((e) => e.gate_passed === true)

  // Group games by week
  const gamesByWeek = useMemo(() => {
    const map = new Map<number, typeof games>()
    for (const g of games) {
      const bucket = map.get(g.week) ?? []
      bucket.push(g)
      map.set(g.week, bucket)
    }
    return [...map.entries()].sort(([a], [b]) => a - b)
  }, [games])

  return (
    <div className="space-y-8">
      {/* Page header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{CURRENT_SEASON} Season</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Upcoming games with model predictions
          </p>
        </div>
        <Link to="/experiments/new">
          <Button size="sm">
            <Plus className="mr-2 h-4 w-4" />
            New experiment
          </Button>
        </Link>
      </div>

      {/* Quick-stats strip */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <StatCard
          label="Scheduled games"
          value={games.length}
          icon={<Calendar className="h-4 w-4 text-muted-foreground" />}
        />
        <StatCard
          label="Completed experiments"
          value={completedExperiments.length}
          icon={<FlaskConical className="h-4 w-4 text-muted-foreground" />}
        />
        <StatCard
          label="Gate passed"
          value={hasPassedGate ? 'Yes' : 'None yet'}
          icon={<Badge variant={hasPassedGate ? 'success' : 'muted'}>{hasPassedGate ? '✓' : '—'}</Badge>}
        />
      </div>

      {/* Games list */}
      {gamesLoading && <LoadingCards count={6} />}

      {gamesError && (
        <ErrorState
          error={gamesErr}
          context="Week games"
          onRetry={() => void refetchGames()}
        />
      )}

      {!gamesLoading && !gamesError && games.length === 0 && (
        <EmptyState
          icon={Calendar}
          title="No upcoming games"
          description={`No scheduled games found for the ${CURRENT_SEASON} season. The data pipeline may not have ingested the schedule yet.`}
          action={
            <Link to="/datasets">
              <Button variant="outline" size="sm">Check datasets</Button>
            </Link>
          }
        />
      )}

      {!gamesLoading && !gamesError && gamesByWeek.map(([week, weekGames]) => (
        <section key={week}>
          <h2 className="text-base font-semibold mb-3">Week {week}</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {weekGames.map((game) => (
              <GameCard key={game.game_id} game={game} />
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}

function StatCard({
  label,
  value,
  icon,
}: {
  label: string
  value: string | number
  icon?: React.ReactNode
}) {
  return (
    <Card>
      <CardHeader className="pb-2 pt-4 px-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
          {icon}
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-4 pt-0">
        <div className="text-2xl font-bold">{value}</div>
      </CardContent>
    </Card>
  )
}
