import { describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { StaticRouter } from 'react-router-dom/server'
import type { Game, GameExplanationResponse, Prediction } from '@/api/types'
import { GameCardWithExplanation } from './GameCardWithExplanation'

// Mock the hook, not react-query itself — GameCardWithExplanation's only job
// is to translate useGameExplanation's data into GameCard's mainDriver prop,
// so the fetch layer itself doesn't need to be real here. vi.mock calls are
// hoisted above imports by vitest, so declaration order here doesn't matter.
const mockUseGameExplanation = vi.fn()
vi.mock('@/api/queries', () => ({
  useGameExplanation: (gameId: string) => mockUseGameExplanation(gameId),
}))

function textOf(game: Game, prediction?: Prediction): string {
  const html = renderToStaticMarkup(
    <StaticRouter location="/">
      <GameCardWithExplanation game={game} prediction={prediction} />
    </StaticRouter>,
  )
  return html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
}

function game(overrides: Partial<Game> = {}): Game {
  return {
    game_id: '2026_02_IND_KC',
    season: 2026,
    week: 2,
    game_date: '2026-09-20',
    home_team: 'KC',
    away_team: 'IND',
    home_score: null,
    away_score: null,
    status: 'scheduled',
    home_spread_close: 6.5,
    total_close: 47.5,
    home_covered: null,
    div_game: false,
    roof: 'outdoors',
    temp: null,
    wind: null,
    ...overrides,
  }
}

function prediction(overrides: Partial<Prediction> = {}): Prediction {
  return {
    game_id: '2026_02_IND_KC',
    season: 2026,
    week: 2,
    fold: null,
    home_team: 'KC',
    away_team: 'IND',
    predicted_home_cover_prob: 0.55,
    predicted_side: 'home',
    actual_home_covered: null,
    correct: null,
    confidence_tier: 'medium',
    ...overrides,
  }
}

function explanation(overrides: Partial<GameExplanationResponse> = {}): GameExplanationResponse {
  return {
    game_id: '2026_02_IND_KC',
    experiment_id: 'exp',
    run_id: 'run',
    model_name: 'ol_xgb_v2',
    predicted_side: 'home',
    predicted_home_cover_prob: 0.55,
    bias_logodds: -0.1,
    clean_forward: true,
    is_approximate: false,
    reproduction_max_diff: null,
    top_drivers: [
      {
        feature: 'home_ol_sack_rate_blend', side: 'home', family: 'OL pass protection',
        raw_value: 0.04, league_pctile: 70, was_imputed: false,
        contribution_logodds: 0.2, pick_direction_contribution: 0.2, abs_rank: 1,
      },
    ],
    family_matchup: [],
    all_features: [],
    ...overrides,
  }
}

describe('GameCardWithExplanation', () => {
  it('shows the top driver as a chip once the explanation resolves', () => {
    mockUseGameExplanation.mockReturnValue({ data: explanation(), isLoading: false, isError: false })
    const text = textOf(game(), prediction())
    expect(text).toContain('OL pass protection')
    expect(text).toContain('KC')
  })

  it('shows no chip while loading', () => {
    mockUseGameExplanation.mockReturnValue({ data: undefined, isLoading: true, isError: false })
    expect(textOf(game(), prediction())).not.toContain('OL pass protection')
  })

  it('shows no chip when the explanation 404s (older pick, none stored)', () => {
    mockUseGameExplanation.mockReturnValue({ data: undefined, isLoading: false, isError: true })
    expect(textOf(game(), prediction())).not.toContain('OL pass protection')
  })

  it('does not fetch when there is no prediction', () => {
    mockUseGameExplanation.mockClear()
    mockUseGameExplanation.mockReturnValue({ data: undefined, isLoading: false, isError: false })
    textOf(game(), undefined)
    expect(mockUseGameExplanation).toHaveBeenCalledWith('')
  })
})
