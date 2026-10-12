import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent, FormEvent, KeyboardEvent } from 'react'
import { askTutor, generateSourceEmbeddings } from '../services/studyApi'
import { startPreparation } from '../services/preparationApi'
import type { PreparationJob } from '../services/preparationApi'
import PreparationStatus from './PreparationStatus'
import type { SourceUploadResult } from '../services/studyApi'
import type { ChatMessage, Citation, Course, SourceLocation } from '../types/study'
import './ChatHome.css'
import { readWorkspace, saveWorkspace } from '../services/workspaceStorage'

type Props = {
  courses: Course[]
  courseId: string
  coursesLoading: boolean
  coursesError: string
  studentName?: string
  onCourseChange: (id: string) => void
  onSignIn: () => void
  onSignOut?: () => void
  signingOut?: boolean
  sessionNotice?: string
  workspaceKey?: string
  onOpenWorkspace: () => void
}
type Entry = {
  message: ChatMessage
  citations: Citation[]
  grounded?: boolean
  scope?: string
}
type UploadStage = 'idle' | 'uploading' | 'embedding' | 'ready' | 'failed'

function locationLabel(location: SourceLocation): string {
  if (location.kind === 'pdf_page') return location.page > 0 ? `Page ${location.page}` : 'Location unavailable'
  if (location.kind === 'slide') return `Slide ${location.slide}`
  const minutes = Math.floor(location.seconds / 60)
  const seconds = Math.floor(location.seconds % 60).toString().padStart(2, '0')
  return `Timestamp ${minutes}:${seconds}`
}
function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong. Please try again.'
}

export default function ChatHome({
  courseId, coursesLoading, coursesError, studentName,
  onSignIn, onSignOut, signingOut, sessionNotice, workspaceKey = 'guest', onOpenWorkspace,
}: Props) {
  const storageKey = `aura.chat.v1:${workspaceKey}:${courseId}`
  const [saved] = useState(() => {
    const value = readWorkspace<Partial<{ question: string; entries: Entry[]; uploaded: SourceUploadResult; uploadStage: UploadStage; fileNames: Record<string, string>; preparationId: string; pendingFilename: string }>>(storageKey, {})
    const source = value.uploaded
    if (!source || source.courseId !== courseId || !/^\d+$/.test(source.sourceId) || typeof source.filename !== 'string') delete value.uploaded
    value.entries = Array.isArray(value.entries) ? value.entries.filter(entry =>
      entry && entry.message && typeof entry.message.id === 'string' && typeof entry.message.content === 'string' &&
      ['student', 'tutor'].includes(entry.message.role) && Array.isArray(entry.citations) && entry.citations.every(c =>
        c && typeof c.id === 'string' && typeof c.sourceId === 'string' && c.location &&
        ((c.location.kind === 'pdf_page' && typeof c.location.page === 'number') ||
         (c.location.kind === 'slide' && typeof c.location.slide === 'number') ||
         (c.location.kind === 'video_timestamp' && typeof c.location.seconds === 'number')) &&
        (c.excerpt === undefined || typeof c.excerpt === 'string'))
    ) : []
    return value
  })
  const [question, setQuestion] = useState(typeof saved.question === 'string' ? saved.question : '')
  const [entries, setEntries] = useState<Entry[]>(saved.entries ?? [])
  const [sending, setSending] = useState(false)
  const [chatError, setChatError] = useState('')
  const [failedQuestion, setFailedQuestion] = useState('')
  const [uploadStage, setUploadStage] = useState<UploadStage>(saved.preparationId ? 'embedding' : saved.uploaded ? saved.uploadStage === 'ready' ? 'ready' : 'failed' : 'idle')
  const [uploaded, setUploaded] = useState<SourceUploadResult | null>(saved.uploaded ?? null)
  const [uploadError, setUploadError] = useState(saved.uploaded && saved.uploadStage !== 'ready' ? 'File processing was interrupted. Retry to finish loading your file.' : '')
  const [uploadMenu, setUploadMenu] = useState(false)
  const [pendingFilename, setPendingFilename] = useState(saved.pendingFilename ?? '')
  const [preparationId, setPreparationId] = useState(saved.preparationId ?? '')
  const [preparationRefresh, setPreparationRefresh] = useState(0)
  const [fileNames, setFileNames] = useState<Record<string, string>>(() => Object.fromEntries(
    Object.entries(saved.fileNames && typeof saved.fileNames === 'object' ? saved.fileNames : {}).filter(([, value]) => typeof value === 'string')
  ))
  const fileInput = useRef<HTMLInputElement>(null)
  const composer = useRef<HTMLTextAreaElement>(null)
  const conversationEnd = useRef<HTMLDivElement>(null)
  const busyRef = useRef(false)
  const mounted = useRef(true)
  const hasConversation = entries.length > 0
  const preparing = uploadStage === 'uploading' || uploadStage === 'embedding'
  const busy = sending || preparing
  const canEmbed = uploaded &&
    (uploaded.processingStatus === 'success' || uploaded.processingStatus === 'partial') &&
    uploaded.contentUnitCount > 0
  const canSend = Boolean(courseId) && !coursesLoading && !coursesError && !busy &&
    (uploadStage === 'idle' || uploadStage === 'ready')
  const readySource = uploadStage === 'ready' ? uploaded : null
  const chatScope = `${courseId}:${readySource?.sourceId ?? ''}`
  useEffect(() => {
    if (courseId) saveWorkspace(storageKey, { question, entries, uploaded, uploadStage, fileNames, preparationId, pendingFilename })
  }, [storageKey, courseId, question, entries, uploaded, uploadStage, fileNames, preparationId, pendingFilename])

  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])
  useEffect(() => {
    conversationEnd.current?.scrollIntoView({ block: 'end', behavior: 'smooth' })
  }, [entries, sending, chatError])
  useEffect(() => {
    if (uploadMenu) fileInput.current?.focus()
  }, [uploadMenu])
  useEffect(() => {
    const input = composer.current
    if (!input) return
    input.style.height = 'auto'
    input.style.height = `${Math.min(input.scrollHeight, 104)}px`
  }, [question])

  async function prepareSource(source: SourceUploadResult) {
    setUploadStage('embedding')
    await generateSourceEmbeddings(source.sourceId)
    if (!mounted.current) return
    setUploadStage('ready')
    composer.current?.focus()
  }

  async function uploadFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file || !courseId || busyRef.current) return
    if (!studentName) { onSignIn(); return }
    busyRef.current = true
    setUploaded(null)
    setPendingFilename(file.name)
    setUploadError('')
    setChatError('')
    setFailedQuestion('')
    setUploadStage('uploading')
    setUploadMenu(false)
    try {
      const job = await startPreparation(courseId, file)
      if (!mounted.current) return
      setPreparationId(job.id)
      setPreparationRefresh(value => value + 1)
      setUploadStage('embedding')
    } catch (error) {
      if (mounted.current) {
        setUploadStage('failed')
        setUploadError(errorMessage(error))
      }
    } finally {
      busyRef.current = false
    }
  }

  function preparationReady(job: PreparationJob) {
    if (job.id !== preparationId || !job.result || !job.source_id) return
    const result = job.result
    const source: SourceUploadResult = {
      sourceId: String(job.source_id), courseId: String(job.course_id), filename: result.source_name,
      fileType: result.source_type, uploadStatus: 'uploaded', processingStatus: result.status,
      contentUnitCount: result.content_units, warnings: [], createdAt: new Date().toISOString(),
    }
    setUploaded(source); setUploadStage('ready'); setPreparationId('')
    setFileNames(current => ({ ...current, [source.sourceId]: source.filename }))
    composer.current?.focus()
  }
  function preparationFailed(job: PreparationJob) {
    if (job.id === preparationId) {
      setUploadStage('failed'); setUploadError(job.error ?? 'Preparation did not finish.')
    }
  }
  async function retryEmbeddings() {
    if (!uploaded || !canEmbed || uploaded.courseId !== courseId || busyRef.current) return
    busyRef.current = true
    setUploadError('')
    try {
      await prepareSource(uploaded)
    } catch (error) {
      if (mounted.current) {
        setUploadStage('failed')
        setUploadError(errorMessage(error))
      }
    } finally {
      busyRef.current = false
    }
  }

  async function sendQuestion(text: string, retry = false) {
    text = text.trim()
    if (!text || !canSend || busyRef.current) return
    busyRef.current = true
    setSending(true)
    setChatError('')
    setFailedQuestion('')
    if (!retry) {
      setEntries(current => [...current, {
        message: { id: crypto.randomUUID(), role: 'student', content: text, citationIds: [], isDemo: false },
        citations: [],
        scope: chatScope,
      }])
      setQuestion('')
    }
    try {
      const response = await askTutor({
        question: text,
        courseId,
        materialId: readySource?.sourceId,
        history: entries.filter(entry => entry.scope === chatScope && (entry.message.role === 'student' || entry.grounded))
          .slice(-8).map(entry => ({
            role: entry.message.role === 'student' ? 'user' as const : 'assistant' as const,
            content: entry.message.content.slice(0, 12000),
          })),
      })
      if (mounted.current) {
        setEntries(current => [...current, {
          message: response.message, citations: response.citations,
          grounded: response.groundingStatus === 'grounded',
          scope: chatScope,
        }])
      }
    } catch (error) {
      if (mounted.current) {
        setChatError(errorMessage(error))
        setFailedQuestion(text)
      }
    } finally {
      busyRef.current = false
      if (mounted.current) {
        setSending(false)
        composer.current?.focus()
      }
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void sendQuestion(question)
  }
  function handleKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      if (canSend) void sendQuestion(question)
    }
  }
  function removeAttachment() {
    setPreparationId('')
    if (busy) return
    setUploaded(null)
    setUploadStage('idle')
    setUploadError('')
    setPendingFilename('')
    setFailedQuestion('')
    setChatError('')
  }
  function newConversation() {
    if (busy) return
    setEntries([])
    setQuestion('')
    setChatError('')
    setFailedQuestion('')
    composer.current?.focus()
  }

  return (
    <div className={`aura-home ${hasConversation ? 'aura-home--conversation' : ''}`}>
      <header className="aura-home__header">
        <button type="button" className="aura-home__brand" onClick={newConversation} disabled={busy} aria-label="Aura — new conversation">
          <span className="aura-home__mark" aria-hidden="true">✦</span>Aura
        </button>
        <nav className="aura-home__nav" aria-label="Aura navigation">
          <button type="button" onClick={onOpenWorkspace} disabled={sending}>Study tools</button>
          {hasConversation && <button type="button" onClick={newConversation} disabled={busy}>New chat</button>}
          {studentName
            ? <><span className="aura-home__account">{studentName}</span>
                {onSignOut && <button type="button" onClick={onSignOut} disabled={sending || signingOut}>{signingOut ? 'Signing out…' : 'Sign out'}</button>}</>
            : <button type="button" className="aura-home__signin" onClick={onSignIn} disabled={busy}>Sign in</button>}
        </nav>
      </header>

      <main className="aura-home__main">
        {sessionNotice && <p className="aura-home__error" role="alert">{sessionNotice}</p>}
        {!hasConversation && <section className="aura-home__intro">
          <span className="aura-home__eyebrow">YOUR SPACE TO UNDERSTAND</span>
          <h1>What would you<br className="aura-home__linebreak" /> like to learn?</h1>
          <p>Bring your study materials. Ask a question.<br />Make the difficult things a little clearer.</p>
        </section>}

        {hasConversation && <section className="aura-home__conversation" aria-label="Conversation" aria-busy={sending}>
          {entries.map(entry => <article key={entry.message.id} className={`aura-home__message aura-home__message--${entry.message.role}`}>
            <div className="aura-home__speaker">{entry.message.role === 'student' ? 'You' : '✦ Aura'}</div>
            <div className="aura-home__message-text">{entry.message.content}</div>
            {entry.citations.length > 0 && <details className="aura-home__sources">
              <summary className="aura-home__source-heading">Sources</summary>
              {entry.citations.map(citation => <details key={citation.id} className="aura-home__citation">
                <summary>{fileNames[citation.sourceId] ?? `Source ${citation.sourceId}`} · {locationLabel(citation.location)}</summary>
                <p>{citation.excerpt || 'No excerpt was returned for this source.'}</p>
              </details>)}
            </details>}
          </article>)}
          {sending && <div className="aura-home__thinking" role="status">✦ Aura is thinking…</div>}
          {chatError && <div className="aura-home__error" role="alert">
            <p>{chatError}</p>
            {failedQuestion && <button type="button" onClick={() => void sendQuestion(failedQuestion, true)} disabled={!canSend}>Retry question</button>}
          </div>}
          <div ref={conversationEnd} />
        </section>}

        <div className="aura-home__composer-area">
          {studentName && <PreparationStatus courseId={courseId} refreshKey={preparationRefresh} pendingId={preparationId} onReady={preparationReady} onFailed={preparationFailed} />}
          {coursesError && <div className="aura-home__error" role="alert">Aura couldn't connect. Please refresh and try again.</div>}
          {coursesLoading && <p className="aura-home__loading" role="status">Getting Aura ready…</p>}
          {!coursesLoading && !coursesError && !courseId && <p className="aura-home__loading" role="status">Aura isn't ready yet. Please try again shortly.</p>}
          {uploadError && <div className="aura-home__error" role="alert">
            <p>{uploadError}</p>
            {canEmbed && uploaded?.courseId === courseId && <button type="button" onClick={() => void retryEmbeddings()} disabled={busy}>Retry preparation</button>}
          </div>}

          <form className="aura-home__composer" onSubmit={submit}>
            {uploadStage !== 'idle' && <div className={`aura-home__attachment aura-home__attachment--${uploadStage}`} aria-live="polite">
              {preparing
                ? <svg className="aura-home__spinner" viewBox="0 0 24 24" aria-hidden="true">
                    <circle className="aura-home__spinner-track" cx="12" cy="12" r="9" />
                    <g>
                      <circle className="aura-home__spinner-arc" cx="12" cy="12" r="9" strokeDasharray="17 40" />
                      <animateTransform attributeName="transform" type="rotate" from="0 12 12" to="360 12 12" dur="0.9s" repeatCount="indefinite" />
                    </g>
                  </svg>
                : <span className="aura-home__file-icon" aria-hidden="true">▤</span>}
              <strong title={uploaded?.filename ?? pendingFilename}>{uploaded?.filename || pendingFilename || 'Your file'}</strong>
              {preparing
                ? <span className="aura-home__sr-only">{uploadStage === 'uploading' ? 'Uploading file' : 'Loading file content'}</span>
                : <span className="aura-home__file-state">{uploadStage === 'ready' ? 'Ready' : 'Try again'}</span>}
              {!busy && <button type="button" onClick={removeAttachment} aria-label="Remove attachment from this conversation">×</button>}
            </div>}
            <label className="aura-home__sr-only" htmlFor="aura-question">Ask Aura a question</label>
            <textarea ref={composer} id="aura-question" value={question} rows={1} maxLength={12000}
              onChange={event => setQuestion(event.target.value)} onKeyDown={handleKey}
              placeholder={hasConversation ? 'Ask another question…' : 'Ask Aura about your materials…'} disabled={sending || uploadStage === 'uploading'} />
            <div className="aura-home__composer-controls">
              <div className="aura-home__upload-control" onKeyDown={event => { if (event.key === 'Escape') setUploadMenu(false) }}>
                <button type="button" className="aura-home__plus" aria-label="Add study material"
                  aria-expanded={uploadMenu} aria-controls="aura-upload-panel"
                  disabled={busy || !courseId || Boolean(coursesError)} onClick={() => setUploadMenu(current => !current)}>+</button>
                {uploadMenu && <div id="aura-upload-panel" className="aura-home__upload-panel">
                  <label htmlFor="aura-file">Upload study material</label>
                  <p>PDF, DOCX, PPTX, audio or MP4. One file at a time.</p>
                  <input ref={fileInput} id="aura-file" type="file" accept=".pdf,.docx,.ppt,.pptx,audio/*,.mp4" onChange={event => void uploadFile(event)} />
                </div>}
              </div>
              <span className="aura-home__composer-hint">{sending ? 'Thinking…' : ''}</span>
              <button type="submit" className="aura-home__send" aria-label="Send question" disabled={!canSend || !question.trim()}>↑</button>
            </div>
          </form>
          {!hasConversation && <p className="aura-home__footnote">{studentName ? 'Check the sources as you learn.' : 'Try Aura as a guest. No sign-up needed.'}</p>}
          {!hasConversation && <div className="aura-home__formats">PDF <span>·</span> PowerPoint <span>·</span> Notes <span>·</span> Audio & video</div>}
        </div>
      </main>
      {!hasConversation && <footer className="aura-home__footer">A little curiosity goes a long way.</footer>}
    </div>
  )
}
