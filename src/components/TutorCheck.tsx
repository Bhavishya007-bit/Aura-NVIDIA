import { useEffect, useState } from 'react'
import { generateTool, listArtifacts, submitAssessment } from '../services/studyToolsApi'
import type { Artifact, ToolCitation } from '../services/studyToolsApi'
import './LearningPanel.css'
import { groupToolCitations } from '../services/citationDisplay'

export default function TutorCheck({ courseId, sourceId, disabled, onUpdated, onOpen }: {
  courseId: string; sourceId: string; disabled: boolean
  onUpdated: () => void; onOpen: (citation: ToolCitation) => void
}) {
  const [check, setCheck] = useState<Artifact | null>(null)
  const [answer, setAnswer] = useState('')
  const [focus, setFocus] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    let cancelled = false
    setCheck(null); setAnswer(''); setFocus(''); setError('')
    if (!sourceId) return
    listArtifacts(courseId, sourceId).then(items => {
      if (!cancelled) setCheck(items.find(item => item.payload.learning?.mode === 'conversation') ?? null)
    }).catch(cause => { if (!cancelled) setError(cause instanceof Error ? cause.message : 'Could not restore your understanding check.') })
    return () => { cancelled = true }
  }, [courseId, sourceId])
  const blocked = disabled || busy
  async function start() {
    if (blocked) return
    setBusy(true); setError('')
    try {
      const value = await generateTool(courseId, sourceId, 'assessment', { count: 1, focus, difficulty: 'beginner', questionType: 'short_answer', learningMode: 'conversation' })
      setCheck(value); setAnswer('')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not create an understanding check.') }
    finally { setBusy(false) }
  }
  async function submit() {
    if (!check || !answer.trim() || blocked) return
    setBusy(true); setError('')
    try {
      const result = await submitAssessment(check.id, { [check.payload.items[0].id]: answer })
      setCheck({ ...check, result }); onUpdated()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not check your reply.') }
    finally { setBusy(false) }
  }
  if (!sourceId) return null
  const item = check?.payload.items[0]
  const feedback = check?.result?.feedback[0]
  return <details className="sw-understanding">
    <summary>Check my understanding</summary><p>Answer a short source-based question. Your checked reply helps Aura choose your next practice.</p>
    {error && <p className="sw-error" role="alert">{error}</p>}
    {busy && <p role="status">{check && !check.result ? 'Checking your reply…' : 'Creating and verifying a question…'}</p>}
    {item && !check?.result ? <form onSubmit={event => { event.preventDefault(); void submit() }}>
      <p><strong>{item.prompt}</strong></p><label>Your explanation<textarea required rows={3} maxLength={3000} value={answer} disabled={blocked} onChange={event => setAnswer(event.target.value)} /></label>
      <button className="sw-primary" type="submit" disabled={blocked || !answer.trim()}>Check my reply</button>
    </form> : <>
      {feedback && <div className="sw-check-feedback"><strong>{feedback.correct ? 'Correct' : 'Review this concept'}</strong><p>{feedback.explanation}</p><p><strong>Expected answer:</strong> {feedback.expected_answer}</p><div className="sw-citations">{groupToolCitations(feedback.citation_ids, check?.payload.citations ?? []).map(citation => <button key={citation.id} type="button" onClick={() => onOpen(citation)}>[{citation.referenceIds?.join(', ')}] {citation.location}</button>)}</div><small>Your mastery estimate was updated from this checked reply.</small></div>}
      <label>Topic to check <span>(optional)</span><input value={focus} maxLength={180} disabled={blocked} onChange={event => setFocus(event.target.value)} placeholder="Leave blank for Aura to choose" /></label>
      <button type="button" disabled={blocked} onClick={() => void start()}>{feedback ? 'Ask another check question' : 'Ask a check question'}</button>
    </>}
  </details>
}
