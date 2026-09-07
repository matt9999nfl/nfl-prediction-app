/**
 * A minimal, read-only markdown renderer for the approval brief.
 *
 * Two constraints shaped this:
 *  - No new dependency (HYPOTHESIS-CHAT-BUILD-PLAN.md, Dependencies).
 *  - The brief is READ-ONLY (ADR-012, commitment 3). This renders React
 *    elements; there is no `dangerouslySetInnerHTML`, no contentEditable, and
 *    no input of any kind, so the document cannot be edited in place.
 *
 * It covers exactly the subset app/scoping/render.py emits: h1/h2, bullets with
 * one level of nesting, inline code, `_emphasis_`, a horizontal rule, and
 * paragraphs. Anything else falls through as plain text rather than being
 * silently dropped.
 */

import { Fragment } from 'react'

/** Split a line into text and `inline code` / _emphasis_ runs. */
function inline(text: string, keyPrefix: string) {
  const parts: React.ReactNode[] = []
  // Underscores are load-bearing in this domain — feature names look like
  // `home_ol_pass_epa_per_att`. Emphasis therefore only matches when the
  // underscores sit on word boundaries, so a name is never eaten by it.
  const pattern = /(`[^`]+`|(?<![\w])_[^_`\n]+_(?!\w))/g
  let last = 0
  let match: RegExpExecArray | null
  let i = 0

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) parts.push(text.slice(last, match.index))
    const token = match[0]
    if (token.startsWith('`')) {
      parts.push(
        <code
          key={`${keyPrefix}-c${i}`}
          className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]"
        >
          {token.slice(1, -1)}
        </code>,
      )
    } else {
      parts.push(
        <em key={`${keyPrefix}-e${i}`} className="text-muted-foreground">
          {token.slice(1, -1)}
        </em>,
      )
    }
    last = match.index + token.length
    i += 1
  }
  if (last < text.length) parts.push(text.slice(last))
  return parts.map((p, n) => <Fragment key={`${keyPrefix}-p${n}`}>{p}</Fragment>)
}

interface MarkdownProps {
  source: string
  className?: string
}

export function Markdown({ source, className }: MarkdownProps) {
  const lines = source.split('\n')
  const blocks: React.ReactNode[] = []
  let bullets: { depth: number; text: string }[] = []
  let paragraph: string[] = []

  function flushBullets(key: string) {
    if (!bullets.length) return
    const items = bullets
    bullets = []
    blocks.push(
      <ul key={key} className="my-2 space-y-1 pl-5 text-sm">
        {items.map((b, i) => (
          <li
            key={`${key}-${i}`}
            className="list-disc"
            style={{ marginLeft: `${b.depth * 1.25}rem` }}
          >
            {inline(b.text, `${key}-${i}`)}
          </li>
        ))}
      </ul>,
    )
  }

  function flushParagraph(key: string) {
    if (!paragraph.length) return
    const text = paragraph.join(' ')
    paragraph = []
    blocks.push(
      <p key={key} className="my-2 text-sm leading-relaxed">
        {inline(text, key)}
      </p>,
    )
  }

  lines.forEach((raw, index) => {
    const key = `md-${index}`
    const line = raw.trimEnd()

    if (line.trim() === '') {
      flushBullets(`${key}-ul`)
      flushParagraph(`${key}-p`)
      return
    }
    if (line.trim() === '---') {
      flushBullets(`${key}-ul`)
      flushParagraph(`${key}-p`)
      blocks.push(<hr key={key} className="my-4 border-t" />)
      return
    }
    if (line.startsWith('# ')) {
      flushBullets(`${key}-ul`)
      flushParagraph(`${key}-p`)
      blocks.push(
        <h1 key={key} className="mb-2 mt-1 text-xl font-semibold tracking-tight">
          {inline(line.slice(2), key)}
        </h1>,
      )
      return
    }
    if (line.startsWith('## ')) {
      flushBullets(`${key}-ul`)
      flushParagraph(`${key}-p`)
      blocks.push(
        <h2
          key={key}
          className="mb-1 mt-5 text-xs font-semibold uppercase tracking-wide text-muted-foreground"
        >
          {inline(line.slice(3), key)}
        </h2>,
      )
      return
    }

    const bullet = /^(\s*)-\s+(.*)$/.exec(line)
    if (bullet) {
      flushParagraph(`${key}-p`)
      bullets.push({ depth: Math.floor(bullet[1].length / 2), text: bullet[2] })
      return
    }

    flushBullets(`${key}-ul`)
    paragraph.push(line.trim())
  })

  flushBullets('md-tail-ul')
  flushParagraph('md-tail-p')

  return <div className={className}>{blocks}</div>
}
