/**
 * Wires GameCard's main-driver chip to GET /api/v1/predictions/{game_id}/explanation.
 *
 * Split out from GameCard itself so GameCard stays a pure, fetch-free
 * component — its existing tests render it with renderToStaticMarkup and no
 * QueryClientProvider, which a hook call inside GameCard would break.
 */
import { useGameExplanation } from '@/api/queries'
import { GameCard } from './GameCard'
import type { Game, Prediction } from '@/api/types'

interface GameCardWithExplanationProps {
  game: Game
  prediction?: Prediction
}

export function GameCardWithExplanation({ game, prediction }: GameCardWithExplanationProps) {
  // Only fetch when there's a prediction to explain — no point querying an
  // explanation for a game with no pick.
  const { data } = useGameExplanation(prediction ? game.game_id : '')
  const top = data?.top_drivers[0]
  const mainDriver = top ? { family: top.family, side: top.side } : null

  return <GameCard game={game} prediction={prediction} mainDriver={mainDriver} />
}
