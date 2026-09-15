import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { LowDataWarning, isLowDataWeek } from './LowDataWarning'

function textOf(week: number): string {
  const html = renderToStaticMarkup(<LowDataWarning week={week} />)
  return html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
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
    expect(text).toContain('Low-information picks')
    expect(text).toContain('no 2026 games have been played yet')
  })

  it('warns about one game of 2026 data at week 2', () => {
    const text = textOf(2)
    expect(text).toContain('one game of 2026 data per team')
  })
})
