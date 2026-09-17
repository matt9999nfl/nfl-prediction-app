import { Link } from 'react-router-dom'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ConfidenceBadge } from '@/components/StatusBadge'
import { formatGameDate, formatHomeSpread, formatTotal, formatConfidence, teamName } from '@/lib/formatters'
import type { Game, Prediction } from '@/api/types'
import { pickedSideProb, pickedTeam } from '@/lib/predictions'
import { cn } from '@/lib/utils'

interface MainDriver {
  family: string
  side: 'home' | 'away' | 'game'
}

interface GameCardProps {
  game: Game
  prediction?: Prediction
  /**
   * Compact chip naming the top-contributing family behind the pick (Stage 1
   * "Why this pick"). Purely presentational — the caller (GameCardWithExplanation)
   * owns the fetch, so this component and its tests stay fetch-free.
   */
  mainDriver?: MainDriver | null
}

export function GameCard({ game, prediction, mainDriver }: GameCardProps) {
  const isScheduled = game.status === 'scheduled'

  return (
    <Link to={`/games/${game.game_id}`} className="block group">
      <Card className="transition-shadow group-hover:shadow-md">
        <CardContent className="p-4 space-y-3">
          {/* Header row: week + date */}
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Week {game.week}</span>
            <span>{formatGameDate(game.game_date)}</span>
          </div>

          {/* Matchup */}
          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2">
            <div className="text-right">
              <div className="font-semibold">{game.away_team}</div>
              <div className="text-xs text-muted-foreground">{teamName(game.away_team)}</div>
              {!isScheduled && (
                <div className={cn(
                  'text-lg font-bold tabular-nums',
                  game.away_score !== null && game.home_score !== null &&
                    game.away_score > game.home_score ? 'text-foreground' : 'text-muted-foreground'
                )}>
                  {game.away_score ?? '—'}
                </div>
              )}
            </div>
            <span className="text-muted-foreground font-medium">@</span>
            <div>
              <div className="font-semibold">{game.home_team}</div>
              <div className="text-xs text-muted-foreground">{teamName(game.home_team)}</div>
              {!isScheduled && (
                <div className={cn(
                  'text-lg font-bold tabular-nums',
                  game.home_score !== null && game.away_score !== null &&
                    game.home_score > game.away_score ? 'text-foreground' : 'text-muted-foreground'
                )}>
                  {game.home_score ?? '—'}
                </div>
              )}
            </div>
          </div>

          {/* Lines */}
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            {/* formatHomeSpread, not formatSpread — home_spread_close is positive
                when the home team is favoured, which is the opposite of betting
                notation. See the comment on formatHomeSpread. */}
            {game.home_spread_close !== null && (
              <span>Spread: {game.home_team} {formatHomeSpread(game.home_spread_close)}</span>
            )}
            {game.total_close !== null && (
              <span>O/U {formatTotal(game.total_close)}</span>
            )}
            {game.div_game && <Badge variant="outline" className="text-xs py-0">DIV</Badge>}
          </div>

          {/* Prediction */}
          {prediction && (
            <div className="border-t pt-2 space-y-1">
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">Model pick:</span>
                <span className="text-sm font-medium">
                  {pickedTeam(game, prediction)}
                  {' '}(
                  {/* pickedSideProb, not predicted_home_cover_prob: that field is always
                      the HOME team's number. See src/lib/predictions.ts (DEFECT-1). */}
                  {formatConfidence(pickedSideProb(prediction))}
                  )
                </span>
              </div>
              <div className="flex items-center justify-end gap-1.5">
                {mainDriver && (
                  <Badge variant="outline" className="text-xs py-0">
                    {mainDriver.family}
                    {mainDriver.side !== 'game' &&
                      ` · ${mainDriver.side === 'home' ? game.home_team : game.away_team}`}
                  </Badge>
                )}
                <ConfidenceBadge tier={prediction.confidence_tier} />
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </Link>
  )
}
