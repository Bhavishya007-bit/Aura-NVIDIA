import { useEffect, useRef, useState } from 'react'
import { explainFigure } from '../services/sourceViewerApi'
import type { FigureExplanation } from '../services/sourceViewerApi'

export default function FigurePanel({ sourceId, position }: { sourceId: number; position: number }) {
  const [question, setQuestion] = useState('Explain the figure or diagram on this page. Describe its labels and relationships.')
  const [result, setResult] = useState<FigureExplanation | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const pending = useRef<AbortController | null>(null)
  useEffect(() => () => pending.current?.abort(), [])
  async function explain() {
    if (pending.current || !question.trim()) return
    const controller = new AbortController()
    pending.current = controller
    setBusy(true); setError(''); setResult(null)
    try {
      const value = await explainFigure(sourceId, position, question.trim(), controller.signal)
      if (!controller.signal.aborted) setResult(value)
    } catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Could not interpret this figure.')
    } finally {
      if (!controller.signal.aborted) { setBusy(false); pending.current = null }
    }
  }
  return <details className="aura-source-excerpt"><summary>Explain this figure or diagram</summary>
    <label>Question about this page<textarea rows={2} maxLength={2000} value={question} disabled={busy} onChange={event => setQuestion(event.target.value)} /></label>
    <button type="button" disabled={busy || question.trim().length < 3} onClick={() => void explain()}>{busy ? 'Inspecting the image…' : 'Explain this figure'}</button>
    {busy && <p role="status">Reading the displayed page with the vision model. This can take longer on CPU.</p>}
    {error && <p className="sw-error" role="alert">{error}</p>}
    {result && <section aria-live="polite"><strong>{result.answerable ? 'Visual interpretation' : 'Visual evidence is insufficient'}</strong><p>{result.explanation}</p>
      {result.observations.length > 0 && <><h3>Visible observations</h3><ul>{result.observations.map((text, index) => <li key={index}>{text}</li>)}</ul></>}
      {result.limitations.length > 0 && <><h3>Limitations</h3><ul>{result.limitations.map((text, index) => <li key={index}>{text}</li>)}</ul></>}
      <small>{result.notice}</small></section>}
  </details>
}
