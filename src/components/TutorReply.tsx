import TeachingText from './TeachingText'
export default function TutorReply({ text, clarification, followUps = [], onFollowUp }: { text: string; clarification?: string; followUps?: string[]; onFollowUp: (value: string) => void }) {
  // The backend already includes this question in its compatibility text answer.
  const question = typeof clarification === 'string' ? clarification.trim() : ''
  const body = question && text.trimEnd().endsWith(question) ? text.trimEnd().slice(0, -question.length).trimEnd() : text
  const suggestions = Array.isArray(followUps) ? followUps.filter((value): value is string => typeof value === 'string' && !!value.trim()).slice(0,3) : []
  return <><TeachingText text={body} />{question && <aside className="aura-tutor-clarification"><strong>One quick question</strong><p>{question}</p></aside>}{suggestions.length > 0 && <div className="aura-tutor-followups" aria-label="Continue learning">{suggestions.map((value,index) => <button key={index} type="button" onClick={() => onFollowUp(value)}>{value} ↗</button>)}</div>}</>
}
