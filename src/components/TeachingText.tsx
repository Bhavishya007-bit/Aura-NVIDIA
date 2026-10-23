import type { ReactNode } from 'react'
import './TeachingText.css'

// Small, text-only Markdown subset. Never executes HTML, images or model-written links.
function inline(text: string): ReactNode[] {
  return text.split(/(`[^`\n]+`|\*\*[^*\n]+\*\*)/g).map((part, index) => part.length > 2 && part.startsWith('`') && part.endsWith('`') ? <code key={index}>{part.slice(1, -1)}</code> : part.length > 4 && part.startsWith('**') && part.endsWith('**') ? <strong key={index}>{part.slice(2, -2)}</strong> : part)
}
export default function TeachingText({ text }: { text: string }) {
  const lines = text.replace(/\r\n/g, '\n').split('\n'), blocks: ReactNode[] = []
  let index = 0
  const special = (line: string) => /^(?:#{1,6}\s|```|\s*[-*+]\s|\s*\d+[.)]\s|>\s|\|)/.test(line) || /^(From your material|Beyond your material[^:]*):$/.test(line)
  while (index < lines.length) {
    const line = lines[index]
    if (!line.trim()) { index++; continue }
    const key = index
    if (line.startsWith('```')) {
      const language = line.slice(3).trim(); const code: string[] = []; index++
      while (index < lines.length && !lines[index].startsWith('```')) code.push(lines[index++])
      if (index < lines.length) index++
      blocks.push(<figure key={key} className="aura-teaching-code">{language && <figcaption>{language}</figcaption>}<pre tabIndex={0}><code>{code.join('\n')}</code></pre></figure>); continue
    }
    if (/^#{1,6}\s/.test(line)) { blocks.push(<h3 key={key}>{inline(line.replace(/^#{1,6}\s+/, ''))}</h3>); index++; continue }
    if (/^(From your material|Beyond your material[^:]*):$/.test(line)) { blocks.push(<h3 key={key} className={line.startsWith('Beyond') ? 'aura-teaching-provenance is-background' : 'aura-teaching-provenance'}>{line.slice(0, -1)}</h3>); index++; continue }
    if (/^\s*[-*+]\s/.test(line) || /^\s*\d+[.)]\s/.test(line)) {
      const ordered = /^\s*\d+[.)]\s/.test(line), items: ReactNode[] = []
      const pattern = ordered ? /^\s*\d+[.)]\s+/ : /^\s*[-*+]\s+/
      while (index < lines.length && pattern.test(lines[index])) items.push(<li key={index}>{inline(lines[index++].replace(pattern, ''))}</li>)
      blocks.push(ordered ? <ol key={key}>{items}</ol> : <ul key={key}>{items}</ul>); continue
    }
    if (line.startsWith('|') && /^\|?\s*:?-{3}/.test(lines[index + 1] ?? '')) {
      const cells = (row: string) => row.replace(/^\|/, '').replace(/\|$/, '').split('|').map(cell => cell.trim())
      const headings = cells(line); index += 2; const rows: string[][] = []
      while (index < lines.length && lines[index].startsWith('|')) rows.push(cells(lines[index++]))
      blocks.push(<div key={key} className="aura-teaching-table" tabIndex={0}><table><thead><tr>{headings.map((cell, n) => <th key={n}>{inline(cell)}</th>)}</tr></thead><tbody>{rows.map((row, n) => <tr key={n}>{headings.map((_, c) => <td key={c}>{inline(row[c] ?? '')}</td>)}</tr>)}</tbody></table></div>); continue
    }
    if (line.startsWith('> ')) { const quote: string[] = []; while (index < lines.length && lines[index].startsWith('> ')) quote.push(lines[index++].slice(2)); blocks.push(<blockquote key={key}>{inline(quote.join('\n'))}</blockquote>); continue }
    const paragraph = [line]; index++
    while (index < lines.length && lines[index].trim() && !special(lines[index])) paragraph.push(lines[index++])
    blocks.push(<p key={key}>{inline(paragraph.join('\n'))}</p>)
  }
  return <div className="aura-teaching-text">{blocks}</div>
}
