import { describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import type { ExplanationFeature, GameExplanationResponse } from '@/api/types'
import { WhyThisPick } from './WhyThisPick'

const mockUseGameExplanation = vi.fn()
vi.mock('@/api/queries', () => ({
  useGameExplanation: (gameId: string) => mockUseGameExplanation(gameId),
}))

function textOf(gameId = '2026_01_SF_LA', homeTeam = 'LA', awayTeam = 'SF'): string {
  const html = renderToStaticMarkup(
    <WhyThisPick gameId={gameId} homeTeam={homeTeam} awayTeam={awayTeam} />,
  )
  return html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
}

function driver(overrides: Partial<ExplanationFeature> = {}): ExplanationFeature {
  return {
    feature: 'home_ol_sack_rate_blend',
    side: 'home',
    family: 'OL pass protection',
    raw_value: 0.045,
    league_pctile: 62.5,
    was_imputed: false,
    contribution_logodds: 0.12,
    pick_direction_contribution: 0.12,
    abs_rank: 1,
    ...overrides,
  }
}

function explanation(overrides: Partial<GameExplanationResponse> = {}): GameExplanationResponse {
  return {
    game_id: '2026_01_SF_LA',
    experiment_id: 'exp',
    run_id: 'run',
    model_name: 'ol_xgb_v2',
    predicted_side: 'away',
    predicted_home_cover_prob: 0.4,
    bias_logodds: -0.1,
    clean_forward: true,
    is_approximate: false,
    reproduction_max_diff: null,
    top_drivers: [driver()],
    family_matchup: [
      { family: 'OL pass protection', home_contribution: 0.12, away_contribution: -0.03, net: 0.09 },
    ],
    all_features: [driver()],
    ...overrides,
  }
}

describe('WhyThisPick', () => {
  it('renders nothing while loading', () => {
    mockUseGameExplanation.mockReturnValue({ data: undefined, isLoading: true, isError: false })
    expect(textOf()).toBe('')
  })

  it('renders nothing on error (no stored explanation yet)', () => {
    mockUseGameExplanation.mockReturnValue({ data: undefined, isLoading: false, isError: true })
    expect(textOf()).toBe('')
  })

  it('shows the picked team, top drivers, raw value and league percentile', () => {
    mockUseGameExplanation.mockReturnValue({ data: explanation(), isLoading: false, isError: false })
    const text = textOf()
    expect(text).toContain('Why this pick')
    expect(text).toContain('SF') // predicted_side is 'away', away team is SF
    expect(text).toContain('OL pass protection')
    expect(text).toContain('0.045')
    expect(text).toContain('63th pctile')
  })

  it('marks an imputed driver', () => {
    mockUseGameExplanation.mockReturnValue({
      data: explanation({ top_drivers: [driver({ was_imputed: true })] }),
      isLoading: false, isError: false,
    })
    expect(textOf()).toContain('*')
  })

  it('shows the family matchup with both team contributions', () => {
    mockUseGameExplanation.mockReturnValue({ data: explanation(), isLoading: false, isError: false })
    const text = textOf()
    expect(text).toContain('Family matchup')
    expect(text).toContain('SF')
    expect(text).toContain('LA')
  })

  it('labels an approximate reproduction and shows the max diff', () => {
    mockUseGameExplanation.mockReturnValue({
      data: explanation({ is_approximate: true, reproduction_max_diff: 0.037 }),
      isLoading: false, isError: false,
    })
    const text = textOf()
    expect(text).toContain('Approximate')
    expect(text).toContain('0.037')
  })

  it('does not label a clean reproduction as approximate', () => {
    mockUseGameExplanation.mockReturnValue({ data: explanation(), isLoading: false, isError: false })
    expect(textOf()).not.toContain('Approximate')
  })
})
