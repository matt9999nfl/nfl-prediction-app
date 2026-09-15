import { describe, expect, it } from 'vitest'
import { pickedSideProb, pickedTeam } from './predictions'

// predicted_home_cover_prob is ALWAYS the home team's probability, whichever
// side was picked. DEFECT-1 (2026-09-10) displayed it beside away picks.

const WAS_AT_PHI = { home_team: 'PHI', away_team: 'WAS' }

describe('pickedTeam', () => {
  it('returns the home team for a home pick', () => {
    expect(pickedTeam(WAS_AT_PHI, { predicted_side: 'home' })).toBe('PHI')
  })

  it('returns the away team for an away pick', () => {
    expect(pickedTeam(WAS_AT_PHI, { predicted_side: 'away' })).toBe('WAS')
  })
})

describe('pickedSideProb', () => {
  it('returns the stored probability unchanged for a home pick', () => {
    // 2026_01_CLE_JAX: home pick, home prob 0.534
    expect(pickedSideProb({ predicted_side: 'home', predicted_home_cover_prob: 0.534 })).toBeCloseTo(0.534)
  })

  it('returns the complement for an away pick', () => {
    // 2026_01_WAS_PHI: away pick, home prob 0.329 -> WAS 0.671
    expect(pickedSideProb({ predicted_side: 'away', predicted_home_cover_prob: 0.329 })).toBeCloseTo(0.671)
  })

  it('never shows a picked side below 50% when the pick is consistent', () => {
    // The model picks home when p_home > 0.5 and away otherwise, so the
    // picked side's probability can never be under a coin flip.
    for (const p of [0.05, 0.329, 0.46, 0.4999, 0.5001, 0.534, 0.95]) {
      const side = p > 0.5 ? 'home' : 'away'
      expect(pickedSideProb({ predicted_side: side, predicted_home_cover_prob: p })).toBeGreaterThanOrEqual(0.5)
    }
  })
})
