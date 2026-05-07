import { Link } from 'react-router-dom'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ConfidenceBadge } from '@/components/StatusBadge'
import { formatGameDate, formatSpread, formatTotal, formatConfidence, teamName } from '@/lib/formatters'
import type { Game, Prediction } from '@/api/types'
import { cn } from '@/lib/utils'

interface GameCardProps {
  game: Game
  prediction?: Prediction
}

export function GameCard({ game, prediction }: GameCardProps) {
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
            {game.home_spread_close !== null && (
              <span>Spread: {game.home_team} {formatSpread(game.home_spread_close)}</span>
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
                  {prediction.predicted_side === 'home' ? game.home_team : game.away_team}
                  {' '}({formatConfidence(prediction.predicted_home_cover_prob)})
                </span>
              </div>
              <div className="flex justify-end">
                <ConfidenceBadge tier={prediction.confidence_tier} />
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </Link>
  )
}
