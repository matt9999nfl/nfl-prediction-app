/**
 * Game detail — /games/:gameId
 *
 * Shows the full Game shape with team_stats and (if available) the
 * prediction from the latest completed experiment.
 */

import { useParams, Link } from 'react-router-dom'
import { useGame } from '@/api/queries'
import { LoadingState } from '@/components/LoadingState'
import { ErrorState } from '@/components/ErrorState'
import { StatusBadge } from '@/components/StatusBadge'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  formatGameDate,
  formatSpread,
  formatTotal,
  formatYards,
  teamName,
} from '@/lib/formatters'
import { ArrowLeft, Thermometer, Wind } from 'lucide-react'

export function GameDetailPage() {
  const { gameId } = useParams<{ gameId: string }>()

  const {
    data: game,
    isLoading,
    isError,
    error,
    refetch,
  } = useGame(gameId ?? '')

  if (isLoading) return <LoadingState rows={6} />

  if (isError) {
    return (
      <ErrorState
        error={error}
        context={`game ${gameId ?? ''}`}
        onRetry={() => void refetch()}
      />
    )
  }

  if (!game) return null

  const home = game.team_stats?.home
  const away = game.team_stats?.away

  return (
    <div className="space-y-6">
      {/* Back button */}
      <Link to="/">
        <Button variant="ghost" size="sm" className="-ml-2">
          <ArrowLeft className="mr-2 h-4 w-4" />
          All games
        </Button>
      </Link>

      {/* Matchup header */}
      <div className="space-y-2">
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-2xl font-bold tracking-tight">
            <Link to={`/teams/${game.away_team}`} className="hover:underline">
              {game.away_team}
            </Link>
            {' @ '}
            <Link to={`/teams/${game.home_team}`} className="hover:underline">
              {game.home_team}
            </Link>
          </h1>
          <StatusBadge status={game.status} />
          {game.div_game && <Badge variant="outline">Divisional</Badge>}
        </div>
        <p className="text-muted-foreground text-sm">
          {formatGameDate(game.game_date)} · Season {game.season}, Week {game.week}
        </p>
      </div>

      {/* Score (if final) */}
      {game.status === 'final' && (
        <Card>
          <CardContent className="p-6">
            <div className="grid grid-cols-3 text-center gap-4">
              <div>
                <div className="text-4xl font-bold tabular-nums">{game.away_score ?? '—'}</div>
                <div className="text-sm mt-1">
                  <Link
                    to={`/teams/${game.away_team}`}
                    className="font-medium hover:underline text-primary"
                  >
                    {game.away_team}
                  </Link>
                </div>
                <div className="text-xs text-muted-foreground">{teamName(game.away_team)}</div>
              </div>
              <div className="flex items-center justify-center text-muted-foreground font-medium">
                FINAL
              </div>
              <div>
                <div className="text-4xl font-bold tabular-nums">{game.home_score ?? '—'}</div>
                <div className="text-sm mt-1">
                  <Link
                    to={`/teams/${game.home_team}`}
                    className="font-medium hover:underline text-primary"
                  >
                    {game.home_team}
                  </Link>
                </div>
                <div className="text-xs text-muted-foreground">{teamName(game.home_team)}</div>
              </div>
            </div>

            {/* ATS result */}
            {game.home_covered !== null && (
              <div className="mt-4 text-center text-sm text-muted-foreground">
                {game.home_covered
                  ? `${game.home_team} covered the spread`
                  : `${game.away_team} covered the spread`}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Lines */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Closing Lines</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <StatItem
              label={`${game.home_team} spread`}
              value={formatSpread(game.home_spread_close)}
            />
            <StatItem label="Total (O/U)" value={formatTotal(game.total_close)} />
          </div>
        </CardContent>
      </Card>

      {/* Team stats */}
      {home && away && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Team Stats</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-2 pr-4 font-medium text-muted-foreground">Stat</th>
                    <th className="text-right py-2 px-4 font-medium">{game.away_team}</th>
                    <th className="text-right py-2 pl-4 font-medium">{game.home_team}</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  <StatRow
                    label="Total yards"
                    away={formatYards(away.total_yards)}
                    home={formatYards(home.total_yards)}
                  />
                  <StatRow
                    label="Pass yards"
                    away={formatYards(away.pass_yards)}
                    home={formatYards(home.pass_yards)}
                  />
                  <StatRow
                    label="Rush yards"
                    away={formatYards(away.rush_yards)}
                    home={formatYards(home.rush_yards)}
                  />
                  <StatRow
                    label="Pass attempts"
                    away={String(away.pass_attempts ?? '—')}
                    home={String(home.pass_attempts ?? '—')}
                  />
                  <StatRow
                    label="Rush attempts"
                    away={String(away.rush_attempts ?? '—')}
                    home={String(home.rush_attempts ?? '—')}
                  />
                </tbody>
              </table>
            </div>
            <p className="text-xs text-muted-foreground mt-3">
              Play count: {game.play_count.toLocaleString()} tracked plays
            </p>
          </CardContent>
        </Card>
      )}

      {/* Game conditions */}
      {(game.temp !== null || game.wind !== null || game.roof) && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Conditions</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-4 text-sm">
              {game.temp !== null && (
                <span className="flex items-center gap-1 text-muted-foreground">
                  <Thermometer className="h-4 w-4" />
                  {game.temp}°F
                </span>
              )}
              {game.wind !== null && (
                <span className="flex items-center gap-1 text-muted-foreground">
                  <Wind className="h-4 w-4" />
                  {game.wind} mph wind
                </span>
              )}
              {game.roof && (
                <span className="text-muted-foreground">Roof: {game.roof}</span>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function StatItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-base font-semibold">{value}</p>
    </div>
  )
}

function StatRow({
  label,
  away,
  home,
}: {
  label: string
  away: string
  home: string
}) {
  return (
    <tr>
      <td className="py-2 pr-4 text-muted-foreground">{label}</td>
      <td className="py-2 px-4 text-right tabular-nums">{away}</td>
      <td className="py-2 pl-4 text-right tabular-nums">{home}</td>
    </tr>
  )
}
