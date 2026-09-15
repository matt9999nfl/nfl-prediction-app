import { describe, expect, it } from 'vitest'
import { formatConfidence, formatHomeSpread, formatSpread, formatTotal } from './formatters'

// Sign conventions — the whole reason this file exists.
//
//   curated.games.home_spread_close (nflverse spread_line):  POSITIVE = home FAVOURED
//   betting notation shown to users ("PHI -6.0"):             NEGATIVE = favoured
//
// DEFECT-2 (2026-09-14): the UI printed the raw nflverse value, so every week-1
// game showed the favourite as the underdog. The convention is verified against
// outcomes by 01-DATA-PIPELINE/scripts/verify_label_convention.py (check C1).

describe('formatHomeSpread (nflverse value -> betting notation for the home team)', () => {
  it('shows a favoured home team with a minus sign', () => {
    // 2026_01_NO_DET: home_spread_close +7.0, DET favoured by 7
    expect(formatHomeSpread(7)).toBe('-7.0')
    // 2026_02_IND_KC: home_spread_close +6.5, KC favoured by 6.5
    expect(formatHomeSpread(6.5)).toBe('-6.5')
  })

  it('shows a home underdog with a plus sign', () => {
    // 2026_01_BAL_IND: home_spread_close -3.0, BAL (away) favoured by 3
    expect(formatHomeSpread(-3)).toBe('+3.0')
  })

  it('shows zero as a pick-em', () => {
    expect(formatHomeSpread(0)).toBe('PK')
  })

  it('never returns the raw value for a non-zero line', () => {
    for (const line of [-10.5, -3, -1.5, 1.5, 3, 6.5, 14]) {
      expect(formatHomeSpread(line)).toBe(formatSpread(-line))
      expect(formatHomeSpread(line)).not.toBe(formatSpread(line))
    }
  })
})

describe('formatSpread (value already in betting notation)', () => {
  it('prefixes positives with + and keeps one decimal', () => {
    expect(formatSpread(3)).toBe('+3.0')
    expect(formatSpread(-6.5)).toBe('-6.5')
  })

  it('treats zero and missing as PK', () => {
    expect(formatSpread(0)).toBe('PK')
    expect(formatSpread(null)).toBe('PK')
    expect(formatSpread(undefined)).toBe('PK')
  })
})

describe('formatConfidence', () => {
  it('rounds a probability to a whole percent', () => {
    expect(formatConfidence(0.6714)).toBe('67%')
    expect(formatConfidence(0.505)).toBe('51%')
    expect(formatConfidence(0.5)).toBe('50%')
  })
})

describe('formatTotal', () => {
  it('keeps one decimal and dashes a missing total', () => {
    expect(formatTotal(47.5)).toBe('47.5')
    expect(formatTotal(40)).toBe('40.0')
    expect(formatTotal(null)).toBe('—')
  })
})
