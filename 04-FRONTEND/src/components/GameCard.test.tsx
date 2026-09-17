import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { StaticRouter } from 'react-router-dom/server'
import { GameCard } from './GameCard'
import type { Game, Prediction } from '@/api/types'

// Renders the real card to a string and checks the text a user would read.
// Testing the formatters alone would not have caught DEFECT-2: formatSpread
// was correct, the card just called the wrong function. So this checks what
// the card actually prints.

function textOf(
  game: Game,
  prediction?: Prediction,
  mainDriver?: { family: string; side: 'home' | 'away' | 'game' } | null,
): string {
  const html = renderToStaticMarkup(
    <StaticRouter location="/">
      <GameCard game={game} prediction={prediction} mainDriver={mainDriver} />
    </StaticRouter>,
  )
  return html
    .replace(/<!-- -->/g, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, '&')
    .replace(/\s+/g, ' ')
    .trim()
}

function game(overrides: Partial<Game>): Game {
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

function prediction(overrides: Partial<Prediction>): Prediction {
  return {
    game_id: '2026_02_IND_KC',
    season: 2026,
    week: 2,
    fold: null,
    home_team: 'KC',
    away_team: 'IND',
    predicted_home_cover_prob: 0.5,
    predicted_side: 'home',
    actual_home_covered: null,
    correct: null,
    confidence_tier: 'low',
    ...overrides,
  }
}

describe('GameCard spread', () => {
  it('shows a favoured home team as minus (DEFECT-2)', () => {
    // KC favoured by 6.5 is stored as +6.5
    const text = textOf(game({ home_spread_close: 6.5 }))
    expect(text).toContain('Spread: KC -6.5')
    expect(text).not.toContain('KC +6.5')
  })

  it('shows a home underdog as plus', () => {
    // 2026_01_BAL_IND: BAL (away) favoured by 3 is stored as -3.0
    const text = textOf(
      game({ game_id: '2026_01_BAL_IND', home_team: 'IND', away_team: 'BAL', home_spread_close: -3 }),
    )
    expect(text).toContain('Spread: IND +3.0')
  })

  it('omits the spread when there is no line', () => {
    expect(textOf(game({ home_spread_close: null }))).not.toContain('Spread:')
  })
})

describe('GameCard model pick', () => {
  const WAS_AT_PHI = game({
    game_id: '2026_01_WAS_PHI',
    week: 1,
    home_team: 'PHI',
    away_team: 'WAS',
    home_spread_close: 6,
  })

  it("shows an away pick with the away side's probability (DEFECT-1)", () => {
    const text = textOf(
      WAS_AT_PHI,
      prediction({ predicted_side: 'away', predicted_home_cover_prob: 0.329, confidence_tier: 'high' }),
    )
    expect(text).toContain('Model pick: WAS (67%)')
    expect(text).not.toContain('WAS (33%)')
  })

  it("shows a home pick with the home side's probability", () => {
    const text = textOf(
      WAS_AT_PHI,
      prediction({ predicted_side: 'home', predicted_home_cover_prob: 0.61, confidence_tier: 'medium' }),
    )
    expect(text).toContain('Model pick: PHI (61%)')
  })

  it('renders no pick section without a prediction', () => {
    expect(textOf(WAS_AT_PHI)).not.toContain('Model pick')
  })
})

describe('GameCard main driver chip', () => {
  const WAS_AT_PHI = game({
    game_id: '2026_01_WAS_PHI',
    week: 1,
    home_team: 'PHI',
    away_team: 'WAS',
    home_spread_close: 6,
  })
  const pick = prediction({ predicted_side: 'away', predicted_home_cover_prob: 0.33 })

  it('shows the family and team for a home/away driver', () => {
    const text = textOf(WAS_AT_PHI, pick, { family: 'OL pass protection', side: 'home' })
    expect(text).toContain('OL pass protection')
    expect(text).toContain('PHI')
  })

  it('shows the family alone for a game-level driver (no team suffix)', () => {
    const text = textOf(WAS_AT_PHI, pick, { family: 'weather', side: 'game' })
    expect(text).toContain('weather')
  })

  it('renders no chip when mainDriver is absent', () => {
    expect(textOf(WAS_AT_PHI, pick, null)).not.toContain('OL pass protection')
  })

  it('renders no chip without a prediction, even if mainDriver were somehow passed', () => {
    expect(textOf(WAS_AT_PHI, undefined, { family: 'QB', side: 'away' })).not.toContain('QB')
  })
})
