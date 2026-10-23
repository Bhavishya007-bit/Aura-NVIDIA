import TeachingText from './TeachingText'
import type { AgentRun, ResearchSource } from '../services/agentApi'

/** Only server-observed sources become links; model-written URLs stay plain text. */
export function safeWebLink(value?: string): string | undefined {
  try {
    if (!value || /[\s\u0000-\u001f]/.test(value)) return
    const url = new URL(value)
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) return
    return url.href
  } catch { return }
}
function SourceChip({ source }: { source: ResearchSource }) {
  if (source.kind === 'web') {
    const href = safeWebLink(source.url)
    return href ? <a href={href} target="_blank" rel="noopener noreferrer">{source.title || new URL(href).hostname}<span aria-hidden="true"> ↗</span></a> : null
  }
  return <span>{source.slide ? `Slide ${source.slide}` : source.page ? `Page ${source.page}` : source.title}</span>
}
export default function ResearchResult({ run }: { run: AgentRun }) {
  const result = run.result
  if (!result?.research_sections) return null
  const sources = result.sources ?? []
  const used = new Set(result.research_sections.flatMap(section => section.references))
  const renderReference = (reference: string) => {
    const source = sources.find(s => s.reference === reference && used.has(s.reference))
    return source ? <span className="research-inline-source"><SourceChip source={source} /></span> : undefined
  }
  return <div className="research-result">
    <p className="plan-caption">Research draft. Source links show where findings came from; claims have not been independently verified.</p>
    {result.research_sections.map(section => <section key={section.kind} className={`research-section research-section--${section.kind}`} aria-label={section.kind === 'material' ? 'From your material' : 'From the web'}>
      <h3>{section.kind === 'material' ? 'From your material' : 'From the web'}</h3>
      <TeachingText text={section.text} renderReference={renderReference} />
      <div className="plan-citations" aria-label={section.kind === 'material' ? 'Material sources' : 'Web sources'}>{sources.filter(source => source.kind === section.kind && section.references.includes(source.reference)).map(source => <SourceChip key={source.reference} source={source} />)}</div>
    </section>)}
    {(result.limitations ?? []).length > 0 && <aside className="research-limitations"><h3>Research limitations</h3><ul>{result.limitations!.map((text, i) => <li key={i}>{text}</li>)}</ul></aside>}
    {!result.research_sections.length && <p className="plan-no-content">No source-backed findings were returned. Try a more specific topic.</p>}
  </div>
}
