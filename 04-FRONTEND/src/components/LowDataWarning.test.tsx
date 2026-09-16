import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { LowDataWarning, isLowDataWeek } from './LowDataWarning'

function textOf(week: number): string {
  const html = renderToStaticMarkup(<LowDataWarning week={week} />)
  return html
    .replace(/<!-- -->/g, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, '&')
    .replace(/\s+/g, ' ')
    .trim()
}

describe('isLowDataWeek', () => {
  it('is true for week 1 and week 2', () => {
    expect(isLowDataWeek(1)).toBe(true)
    expect(isLowDataWeek(2)).toBe(true)
  })

  it('is false from week 3 onward', () => {
    expect(isLowDataWeek(3)).toBe(false)
    expect(isLowDataWeek(10)).toBe(false)
  })
})

describe('LowDataWarning', () => {
  it('renders nothing from week 3 onward', () => {
    expect(textOf(3)).toBe('')
  })

  it('warns about zero 2026 games at week 1', () => {
    const text = textOf(1)
    expect(text).toContain('Early-season picks')
    expect(text).toContain('no 2026 games have been played yet')
  })

  it('describes the blend at week 2, not a single-game figure', () => {
    const text = textOf(2)
    expect(text).toContain('one game of 2026 data')
    expect(text).toContain("blended with last season's numbers")
  })

  it('does not claim the blend is validated', () => {
    expect(textOf(1)).toContain('not the same as validation')
    expect(textOf(2)).toContain('not the same as validation')
  })
})
