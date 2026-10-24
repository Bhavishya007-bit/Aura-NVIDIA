import TeachingText from './TeachingText'
import { planSessions } from './studyPlanModel'

/** Formats saved plan instructions without creating new tasks or inferred dates. */
export default function StudyPlanSteps({ text, label = 'Study steps' }: { text: string; label?: string }) {
  const sessions = planSessions(text)
  if (!sessions.length) return null
  return <div className="plan-sessions" aria-label={label}>
    {sessions.map((session, index) => <section className="plan-session" key={index}>
      <header className="plan-session-heading"><h4>{session.title}</h4>{session.duration && <span className="plan-session-time">{session.duration}</span>}</header>
      <ul className="plan-action-list">{session.items.map((item, n) => <li key={n}><TeachingText text={item} /></li>)}</ul>
    </section>)}
  </div>
}
