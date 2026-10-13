import { useEffect, useState } from 'react'
import { getLearningProfile } from '../services/studyToolsApi'
import type { LearningMode, LearningProfile } from '../services/studyToolsApi'
import './LearningPanel.css'

export default function LearningPanel({ courseId, sourceId, refreshKey, disabled, onPractice }: {
  courseId: string; sourceId: string; refreshKey: number; disabled: boolean
  onPractice: (mode: LearningMode, focus?: string) => void
}) {
  const [profile, setProfile] = useState<LearningProfile | null>(null)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let cancelled = false
    setProfile(null); setError('')
    if (!courseId || !sourceId) return
    getLearningProfile(courseId, sourceId).then(value => { if (!cancelled) setProfile(value) })
      .catch(cause => { if (!cancelled) setError(cause instanceof Error ? cause.message : 'Could not load your learning profile.') })
    return () => { cancelled = true }
  }, [courseId, sourceId, refreshKey, retry])
  if (!sourceId) return null
  return <section className="sw-learning sw-progress-panel" aria-label="Topic mastery">
    <header><div><h2>Your understanding of this material</h2><p>Estimated from checked answers in quizzes and tutor conversations.</p></div></header>
    {error ? <p className="sw-error" role="alert">{error} <button type="button" onClick={() => setRetry(value => value + 1)}>Retry</button></p>
      : !profile ? <p role="status">Loading your learning profile…</p>
        : <>
          {profile.diagnostic_recommended ? <div className="sw-learning-start"><h3>Find your starting point</h3><p>A short diagnostic checks different topics in the selected material. Topics you have not answered remain unknown.</p><button className="sw-primary" type="button" disabled={disabled} onClick={() => onPractice('diagnostic')}>Start diagnostic</button></div>
            : <><div className="sw-learning-actions"><button className="sw-primary" type="button" disabled={disabled} onClick={() => onPractice('adaptive')}>Practice my weakest topic</button><button type="button" disabled={disabled} onClick={() => onPractice('diagnostic')}>Check other topics</button></div>
              <div className="sw-mastery-list">{profile.topics.map(topic => <article key={topic.topic}>
                <div><strong>{topic.topic}</strong><small>{topic.evidence_count} checked answers · Suggested: {topic.difficulty}{topic.limited_evidence ? ' · Limited evidence' : ''}</small></div>
                <div className="sw-mastery-meter"><progress max={1} value={topic.mastery} aria-label={`${topic.topic}: ${Math.round(topic.mastery * 100)}% estimated mastery`} /><span>{Math.round(topic.mastery * 100)}%</span></div>
                <button type="button" disabled={disabled} onClick={() => onPractice('adaptive', topic.topic)}>Practice</button>
              </article>)}</div></>}
          <p className="sw-chart-note">{profile.notice}</p>
        </>}
  </section>
}
