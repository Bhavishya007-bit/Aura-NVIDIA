import { useState } from 'react'
import type { Artifact, Material } from '../services/studyToolsApi'
import { fileType } from './studyPlanModel'
import './StudyOverview.css'

type Destination = 'Tutor' | 'Notes' | 'Summary' | 'Flashcards' | 'Assessment' | 'Progress' | 'Agents'
type Props = {
  material?: Material; ready: boolean; busy: boolean; canUpload: boolean
  artifacts: Artifact[]; loading: boolean; error: string
  onNavigate: (destination: Destination) => void; onUpload: () => void
  onOpenArtifact: (artifact: Artifact) => void
}
const artifactDestination = (kind: Artifact['kind']): Destination => ({
  notes: 'Notes', summary: 'Summary', flashcards: 'Flashcards', assessment: 'Assessment',
})[kind] as Destination

export default function StudyOverview({ material, ready, busy, canUpload, artifacts, loading, error, onNavigate, onUpload, onOpenArtifact }: Props) {
  const [more, setMore] = useState(false)
  return <div className="study-home">
    <section className="study-home-hero" aria-labelledby="study-home-title">
      <div className="study-home-orbit" aria-hidden="true"><span>A.</span></div>
      <div className="study-home-copy">
        <p className="study-home-kicker">A LITTLE CLARITY. A LITTLE PROGRESS.</p>
        <h2 id="study-home-title">One idea at a time.</h2>
        <p>{material ? 'Start with a question. Turn what feels complicated into something you understand.' : 'Bring your lecture slides, notes or textbook. We’ll find a good place to start.'}</p>
        {material && <div className="study-home-file"><span>{fileType(material.title, material.type)}</span><strong title={material.title}>{material.title}</strong></div>}
        <div className="study-home-actions">
          {material ? <button className="sw-primary" type="button" disabled={!ready || busy} onClick={() => onNavigate('Tutor')}>Ask Aura <span aria-hidden="true">↗</span></button>
            : <button className="sw-primary" type="button" disabled={!canUpload || busy} onClick={onUpload}>Add your first material <span aria-hidden="true">＋</span></button>}
          {material && <button type="button" className="study-home-plan" disabled={!ready || busy} onClick={() => onNavigate('Agents')}>Make a study plan <span aria-hidden="true">→</span></button>}
        </div>
        {material && !ready && <p className="study-home-hint" role="status">{material.status === 'processing' ? 'Your material is being prepared. You can start as soon as it is ready.' : 'This material needs attention before you can study it. Choose another file or check its preparation status.'}</p>}
      </div>
    </section>

    <section className="study-home-next" aria-labelledby="study-next-title">
      <header><div><p className="study-home-kicker">WHEN YOU’RE READY</p><h2 id="study-next-title">Keep the momentum.</h2></div><button type="button" aria-expanded={more} aria-controls="study-home-tools" onClick={() => setMore(value => !value)}>{more ? 'Fewer tools −' : 'More tools +'}</button></header>
      <div className="study-home-cards">
        <button type="button" disabled={!ready || busy} onClick={() => onNavigate('Flashcards')}><span className="study-home-number" aria-hidden="true">01</span><span><strong>Remember the key ideas</strong><small>Practice with flashcards at your own pace.</small></span><span aria-hidden="true">↗</span></button>
        <button type="button" disabled={!ready || busy} onClick={() => onNavigate('Assessment')}><span className="study-home-number" aria-hidden="true">02</span><span><strong>See what’s sticking</strong><small>A short quiz to find your next step.</small></span><span aria-hidden="true">↗</span></button>
      </div>
      <div id="study-home-tools" className="study-home-extra" hidden={!more}>
        {(['Notes', 'Summary', 'Progress'] as Destination[]).map(destination => <button key={destination} type="button" disabled={busy || (destination !== 'Progress' && !ready)} onClick={() => onNavigate(destination)}>{destination}<span aria-hidden="true">↗</span></button>)}
      </div>
    </section>

    <section className="study-home-saved" aria-labelledby="study-saved-title"><header><h2 id="study-saved-title">Pick up where you left off</h2><span>Saved for this material</span></header>
      {loading ? <p role="status">Loading your saved work…</p> : error ? <p role="alert" className="sw-error">{error}</p>
        : artifacts.length ? <div>{artifacts.slice(0, 3).map(artifact => <button key={artifact.id} type="button" disabled={busy} onClick={() => onOpenArtifact(artifact)}><span className="study-home-saved-icon" aria-hidden="true">↳</span><span><strong>{artifactDestination(artifact.kind)}</strong><small>{artifact.payload.focus || 'From your selected material'}</small></span><time dateTime={artifact.created_at}>{Number.isFinite(Date.parse(artifact.created_at)) ? new Date(artifact.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : 'Saved'}</time><span aria-hidden="true">→</span></button>)}</div>
          : <p>Your notes, summaries and practice will appear here. Start with a question above.</p>}
    </section>
    <button className="study-home-progress" type="button" onClick={() => onNavigate('Progress')}>View your learning progress <span aria-hidden="true">→</span></button>
  </div>
}
