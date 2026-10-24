import { savedGeneration } from '../services/generationJobs'
import type { SavedGeneration } from '../services/generationJobs'
import TutorReply from './TutorReply'
import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent, FormEvent, KeyboardEvent } from 'react'
import { askTutor, generateSourceEmbeddings } from '../services/studyApi'
import { queueMaterials } from '../services/preparationApi'
import type { PreparationJob, UploadEntry } from '../services/preparationApi'
import PreparationStatus from './PreparationStatus'
import UploadBatchStatus from './UploadBatchStatus'
import SourceViewer from './SourceViewer'
import AccountMenu from './AccountMenu'
import { chatCitationGroups } from '../services/citationDisplay'
import type { ToolCitation } from '../services/studyToolsApi'
import type { SourceUploadResult } from '../services/studyApi'
import type { ChatMessage, Citation, Course } from '../types/study'
import './ChatHome.css'
import { readWorkspace, saveWorkspace } from '../services/workspaceStorage'
import { imageFilename, restoreChatImages } from '../services/chatImages'
import type { ChatImage } from '../services/chatImages'
import MaterialPicker, { cleanSelection, MaterialChips, materialReady } from './MaterialPicker'
import GenerationStatus from './GenerationStatus'
import TeachingText from './TeachingText'
import { listMaterials } from '../services/studyToolsApi'
import type { Material } from '../services/studyToolsApi'
import { useGeneration } from '../hooks/useGeneration'
import { useGenerationSupport } from '../hooks/useGenerationSupport'
import { multiMaterialNotice } from '../services/generationSupport'
import { ApiResponseError } from '../services/apiClient'

type Props = {
  courses: Course[]
  courseId: string
  coursesLoading: boolean
  coursesError: string
  studentName: string
  onCourseChange: (id: string) => void
  onSignOut?: () => void
  signingOut?: boolean
  sessionNotice?: string
  workspaceKey: string
  onOpenWorkspace: () => void
  onCreateStudyPlan?: (goal: string, source?: string) => void
}
type Entry = {
  stopped?: boolean
  message: ChatMessage
  citations: Citation[]
  clarifyingQuestion?: string
  followUpOptions?: string[]
  grounded?: boolean
  answerMode?: 'source' | 'source_plus_background' | 'general_background' | 'visual' | 'excerpt'
  scope?: string
  attachments?: { sourceId: string; filename: string }[]
}
type UploadStage = 'idle' | 'uploading' | 'embedding' | 'ready' | 'failed'

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong. Please try again.'
}

export default function ChatHome({
  courseId, coursesLoading, coursesError, studentName,
  onSignOut, signingOut, sessionNotice, workspaceKey, onOpenWorkspace, onCreateStudyPlan,
}: Props) {
  const storageKey = `aura.chat.v1:${workspaceKey}:${courseId}`
  const [pendingJob] = useState(() => savedGeneration(`${storageKey}:generation`))
  const [openCitation, setOpenCitation] = useState<ToolCitation | null>(null)
  const [saved] = useState(() => {
    const value = readWorkspace<Partial<{ partial: { id: string; text: string; scope: string }; materialIds: string[]; question: string; entries: Entry[]; uploaded: SourceUploadResult; uploadStage: UploadStage; fileNames: Record<string, string>; preparationIds: string[]; preparationId: string; pendingFilename: string; imageAttachments: ChatImage[] }>>(storageKey, {})
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
    if (value.partial && typeof value.partial.id === 'string' && typeof value.partial.text === 'string' && value.partial.text && typeof value.partial.scope === 'string') value.entries.push({ message: { id: value.partial.id, role: 'tutor', content: value.partial.text, citationIds: [], isDemo: false }, citations: [], stopped: true, scope: value.partial.scope })
    return value
  })
  const [question, setQuestion] = useState(typeof saved.question === 'string' ? saved.question : '')
  const [entries, setEntries] = useState<Entry[]>(saved.entries ?? [])
  const [selectedMaterialIds, setSelectedMaterialIds] = useState(() => cleanSelection(pendingJob?.course === courseId && Array.isArray(pendingJob.payload.material_ids) ? pendingJob.payload.material_ids.map(String) : saved.materialIds ?? (saved.uploaded ? [saved.uploaded.sourceId] : [])))
  const [materials, setMaterials] = useState<Material[]>([])
  const [materialsLoading, setMaterialsLoading] = useState(false)
  const [materialsError, setMaterialsError] = useState('')
  const [materialRefresh, setMaterialRefresh] = useState(0)
  const generation = useGeneration()
  const support = useGenerationSupport(courseId)
  const [partial, setPartial] = useState<{ id: string; text: string; scope: string } | null>(null)
  const partialRef = useRef<typeof partial>(null)
  const requestVersion = useRef(0)
  const resumed = useRef(false)
  const [sending, setSending] = useState(false)
  const [chatError, setChatError] = useState('')
  const [failedQuestion, setFailedQuestion] = useState('')
  const [uploadStage, setUploadStage] = useState<UploadStage>(saved.preparationId ? 'embedding' : saved.uploaded ? saved.uploadStage === 'ready' ? 'ready' : 'failed' : 'idle')
  const [uploaded, setUploaded] = useState<SourceUploadResult | null>(saved.uploaded ?? null)
  const [imageAttachments, setImageAttachments] = useState<ChatImage[]>(() => restoreChatImages(saved.imageAttachments, courseId,
    saved.uploadStage === 'ready' ? saved.uploaded : undefined))
  const [uploadError, setUploadError] = useState(saved.uploaded && saved.uploadStage !== 'ready' ? 'File processing was interrupted. Retry to finish loading your file.' : '')
  const [uploadMenu, setUploadMenu] = useState(false)
  const [pendingFilename, setPendingFilename] = useState(saved.pendingFilename ?? '')
  const [preparationId, setPreparationId] = useState(saved.preparationId ?? '')
  const [uploadEntries, setUploadEntries] = useState<UploadEntry[]>([])
  const [preparationIds, setPreparationIds] = useState<string[]>(Array.isArray(saved.preparationIds) ? saved.preparationIds.filter(id => typeof id === 'string') : [])
  const uploadController = useRef<AbortController | null>(null)
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
  const readyImages = imageAttachments.flatMap(item => item.stage === 'ready' && item.source ? [item.source] : [])
  const effectiveIds = imageAttachments.length ? readyImages.map(source => source.sourceId) : selectedMaterialIds
  const materialOptions = [...new Map([...materials, ...[...readyImages, ...(uploaded ? [uploaded] : [])].map(source => ({ id: source.sourceId, title: source.filename, type: source.fileType, status: 'ready' }))].map(item => [item.id, item])).values()]
  const selectedReady = effectiveIds.every(id => materialOptions.some(item => item.id === id && materialReady(item)))
  const legacyImages = effectiveIds.length > 1 && effectiveIds.every(id => imageFilename(materialOptions.find(item => item.id === id)?.title ?? ''))
  const groupSupported = effectiveIds.length <= 1 || legacyImages || support.multi_chat
  const preparing = imageAttachments.length ? imageAttachments.some(item => ['uploading', 'embedding'].includes(item.stage)) : uploadStage === 'uploading' || uploadStage === 'embedding'
  const busy = sending || preparing || uploadEntries.some(entry => entry.state === 'waiting' || entry.state === 'uploading')
  const canEmbed = uploaded &&
    (uploaded.processingStatus === 'success' || uploaded.processingStatus === 'partial') &&
    uploaded.contentUnitCount > 0
  const canSend = Boolean(studentName && workspaceKey && courseId) && !coursesLoading && !coursesError && !busy && !generation.active && selectedReady && groupSupported &&
    (imageAttachments.length ? readyImages.length === imageAttachments.length : uploadStage === 'idle' || uploadStage === 'ready')
  const readySource = effectiveIds[0] ? { sourceId: effectiveIds[0] } : null
  const chatScope = `${courseId}:${effectiveIds.join(',')}`
  useEffect(() => {
    if (courseId) saveWorkspace(storageKey, { question, entries, uploaded: imageAttachments.length ? imageAttachments[0].source ?? null : uploaded,
      uploadStage: imageAttachments.length ? readyImages.length === imageAttachments.length ? 'ready' : 'embedding' : uploadStage,
      imageAttachments, fileNames, preparationId, preparationIds, pendingFilename, materialIds: effectiveIds, partial })
  }, [storageKey, courseId, question, entries, uploaded, uploadStage, imageAttachments, fileNames, preparationId, preparationIds, pendingFilename, selectedMaterialIds, partial])
  useEffect(() => {
    let cancelled = false
    if (!courseId || !studentName) return
    setMaterialsLoading(true); setMaterialsError('')
    listMaterials(courseId).then(items => { if (!cancelled) { setMaterials(items); setFileNames(current => ({ ...current, ...Object.fromEntries(items.map(item => [item.id, item.title])) })) } })
      .catch(() => { if (!cancelled) setMaterialsError('Could not load your saved materials. Refresh the list to try again.') })
      .finally(() => { if (!cancelled) setMaterialsLoading(false) })
    return () => { cancelled = true }
  }, [courseId, studentName, materialRefresh])

  useEffect(() => { setUploadEntries([]); return () => uploadController.current?.abort() }, [courseId])
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])
  useEffect(() => {
    conversationEnd.current?.scrollIntoView({ block: 'end', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
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
    const files = Array.from(event.target.files ?? [])
    event.target.value = ''
    await uploadFiles(files)
  }
  async function uploadFiles(files: File[], retry = false) {
    if (!files.length || !courseId || busyRef.current) return
    if (!studentName || !workspaceKey) return
    const images = files.every(file => imageFilename(file.name))
    if ((!images && imageAttachments.length) || (images && uploaded && !imageFilename(uploaded.filename))) {
      setUploadError('Remove the current attachments before switching between screenshots and a document.'); return
    }
    if (files.some(file => imageFilename(file.name)) && !images) {
      setUploadError('Choose screenshots together, or upload document files separately.'); return
    }
    const reused = new Set<string>()
    const added: ChatImage[] = images ? files.map(file => {
      const prior = retry ? imageAttachments.find(item => item.stage === 'failed' && item.filename === file.name && !reused.has(item.key)) : undefined
      if (prior) reused.add(prior.key)
      return {key: prior?.key ?? crypto.randomUUID(), filename: file.name, stage: 'uploading'}
    }) : []
    if (images && imageAttachments.length + added.filter(item => !reused.has(item.key)).length > 5) {
      setUploadError('You can attach up to 5 screenshots to one question. Remove one before adding another.'); return
    }
    if (images) setImageAttachments(current => [...current.map(item => added.find(slot => slot.key === item.key) ?? item), ...added.filter(slot => !current.some(item => item.key === slot.key))])
    busyRef.current = true
    const controller = new AbortController()
    uploadController.current = controller
    if (!images) setUploaded(null)
    setPendingFilename(files[0].name)
    setUploadError(''); setChatError(''); setFailedQuestion('')
    setUploadStage('uploading'); setUploadMenu(false)
    try {
      const entries = await queueMaterials(courseId, files, updates => {
        setUploadEntries(updates)
        if (images) setImageAttachments(current => current.map(item => {
          const index = added.findIndex(slot => slot.key === item.key)
          if (index < 0 || !updates[index]) return item
          const update = updates[index]
          if (update.state === 'failed') return {...item, stage: 'failed', error: update.error}
          if (update.job && item.stage !== 'ready' && !(item.stage === 'failed' && item.jobId)) return {...item, jobId: update.job.id, stage: 'embedding'}
          return item
        }))
      }, (job, first) => {
        setPreparationIds(current => [...current, job.id])
        if (first && !images) { setPreparationId(job.id); setPendingFilename(job.filename); setUploadStage('embedding') }
        setPreparationRefresh(value => value + 1)
      }, controller.signal)
      if (!controller.signal.aborted && mounted.current && !entries.some(entry => entry.state === 'queued')) setUploadStage('failed')
    } catch (error) {
      if (!controller.signal.aborted && mounted.current) { setUploadStage('failed'); setUploadError(errorMessage(error)) }
    } finally { busyRef.current = false; uploadController.current = null }
  }

  function preparationReady(job: PreparationJob) {
    if (String(job.course_id) !== courseId) return
    setPreparationIds(current => current.filter(id => id !== job.id))
    const image = imageAttachments.find(item => item.jobId === job.id)
    if ((!image && job.id !== preparationId) || !job.result || !job.source_id) return
    const result = job.result
    const source: SourceUploadResult = {
      sourceId: String(job.source_id), courseId: String(job.course_id), filename: result.source_name,
      fileType: result.source_type, uploadStatus: 'uploaded', processingStatus: result.status,
      contentUnitCount: result.content_units, warnings: result.warnings ?? [], createdAt: new Date().toISOString(),
    }
    if (image) setImageAttachments(current => current.map(item => item.jobId === job.id ? {...item, source, stage: 'ready', error: undefined} : item))
    else {
      setUploaded(source); setUploadStage('ready'); setPreparationId('')
      setSelectedMaterialIds([source.sourceId])
      if (imageFilename(source.filename)) setImageAttachments([{key: `source-${source.sourceId}`, filename: source.filename, source, stage: 'ready'}])
    }
    setFileNames(current => ({ ...current, [source.sourceId]: source.filename }))
    setMaterialRefresh(current => current + 1)
    composer.current?.focus()
  }
  function preparationFailed(job: PreparationJob) {
    if (String(job.course_id) !== courseId) return
    setPreparationIds(current => current.filter(id => id !== job.id))
    setImageAttachments(current => current.map(item => item.jobId === job.id ? {...item, stage: 'failed', error: job.error ?? 'Screenshot preparation failed.'} : item))
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

  async function sendQuestion(text: string, retry = false, resume?: SavedGeneration) {
    text = text.trim()
    if (!text || !canSend || busyRef.current) return
    const ticket = generation.start(); if (!ticket) return
    resumed.current = true
    const version = ++requestVersion.current
    const draft = { id: crypto.randomUUID(), text: '', scope: chatScope }
    partialRef.current = draft; setPartial(draft)
    busyRef.current = true
    setSending(true)
    setChatError('')
    setFailedQuestion('')
    if (!retry) {
      setEntries(current => [...current, {
        message: { id: crypto.randomUUID(), role: 'student', content: text, citationIds: [], isDemo: false },
        citations: [],
        scope: chatScope,
        ...(effectiveIds.length ? { attachments: effectiveIds.map(id => ({sourceId: id, filename: materialOptions.find(item => item.id === id)?.title ?? 'Material'})) } : {}),
      }])
      setQuestion('')
    }
    try {
      const response = await askTutor({
        question: text,
        courseId,
        materialId: readySource?.sourceId,
        materialIds: effectiveIds,
        // Background answers also establish conversational subjects. The backend
        // treats history as context, never as uploaded-source evidence.
        history: entries.filter(entry => entry.scope === chatScope && !entry.stopped)
          .slice(-8).map(entry => ({
            role: entry.message.role === 'student' ? 'user' as const : 'assistant' as const,
            content: entry.message.content.slice(0, 12000),
          })),
      }, { signal: ticket.signal, resume, enabled: support.study_jobs, course: courseId, storageKey: `${storageKey}:generation`, setCancel: generation.setCancel, combinedMaterials: !legacyImages && support.multi_chat,
        onText: text => { if (ticket.current()) { const value = { ...draft, text }; partialRef.current = value; setPartial(value) } } })
      if (ticket.current()) {
        partialRef.current = null; setPartial(null)
        setEntries(current => [...current, {
          message: response.message, citations: response.citations, clarifyingQuestion: response.clarifyingQuestion, followUpOptions: response.followUpOptions,
          grounded: response.groundingStatus === 'grounded', answerMode: response.answerMode,
          scope: chatScope,
        }])
      }
    } catch (error) {
      if (mounted.current && requestVersion.current === version) {
        if (!ticket.signal.aborted && !ticket.cancelRequested()) setChatError(error instanceof ApiResponseError && error.message.startsWith('Aura could not confirm that all attached screenshots') ? error.message : 'Aura could not finish this answer. Your attachments and any received text are kept. Please retry.')
        setFailedQuestion(text)
        if (ticket.signal.aborted || ticket.cancelRequested()) setQuestion(text)
      }
    } finally {
      generation.finish(ticket)
      if (mounted.current && requestVersion.current === version) {
        const captured = partialRef.current
        if (captured?.text) setEntries(current => [...current, { message: { id: captured.id, role: 'tutor', content: captured.text, citationIds: [], isDemo: false }, citations: [], scope: captured.scope, stopped: true }])
        partialRef.current = null; setPartial(null); busyRef.current = false
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
  function removeAttachment(key?: string) {
    if (sending || uploadEntries.some(entry => ['waiting', 'uploading'].includes(entry.state))) return
    const removedJob = imageAttachments.find(item => item.key === key)?.jobId
    const removedSource = imageAttachments.find(item => item.key === key)?.source?.sourceId
    if (removedJob) setPreparationIds(current => current.filter(id => id !== removedJob))
    setImageAttachments(current => key ? current.filter(item => item.key !== key) : [])
    setPreparationId('')
    setUploaded(null)
    setSelectedMaterialIds(current => key ? current.filter(id => id !== removedSource) : [])
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
  useEffect(() => {
    if (resumed.current || !support.study_jobs || !canSend) return
    const pending = savedGeneration(`${storageKey}:generation`)
    if (!pending || pending.course !== courseId || pending.operation !== 'chat') return
    resumed.current = true
    void sendQuestion(String(pending.payload.question ?? ''), true, pending)
  }, [support.study_jobs, canSend, storageKey])
  function changeMaterials(ids: string[]) {
    if (busy || generation.active) return
    setSelectedMaterialIds(ids); setImageAttachments([]); setUploaded(null); setUploadStage('idle'); setUploadError(''); setChatError(''); setFailedQuestion('')
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
          <AccountMenu name={studentName} courseId={courseId} onSignOut={onSignOut} signingOut={signingOut} disabled={sending} />
        </nav>
      </header>

      <main className="aura-home__main">
        {sessionNotice && <p className="aura-home__error" role="alert">{sessionNotice}</p>}
        {!hasConversation && <section className="aura-home__intro">
          <span className="aura-home__eyebrow">YOUR SPACE TO UNDERSTAND</span>
          <h1>What would you<br className="aura-home__linebreak" /> like to learn?</h1>
          <p>Bring your study materials. Ask a question.<br />Make the difficult things a little clearer.</p>
        </section>}

        <details className="aura-home__materials"><summary>Materials · {effectiveIds.length} selected</summary><MaterialPicker materials={materialOptions} selected={effectiveIds} onChange={changeMaterials} storageKey={`aura.sets.v1:${workspaceKey}:${courseId}`} disabled={busy || generation.active} loading={materialsLoading} />{materialsLoading && <p role="status">Loading materials…</p>}{materialsError && <p role="alert">{materialsError} <button type="button" onClick={() => setMaterialRefresh(value => value + 1)}>Refresh</button></p>}</details>
        <MaterialChips materials={materialOptions} selected={effectiveIds} onChange={changeMaterials} disabled={busy || generation.active} />
        {!groupSupported && <p className="aura-home__loading" role="status">{multiMaterialNotice}</p>}
        {hasConversation && <section className="aura-home__conversation" aria-label="Conversation" aria-busy={sending}>
          {entries.map(entry => <article key={entry.message.id} className={`aura-home__message aura-home__message--${entry.message.role}`}>
            <div className="aura-home__speaker">{entry.message.role === 'student' ? 'You' : '✦ Aura'}</div>
            <div className="aura-home__message-text">{entry.message.role === 'tutor' ? <TutorReply text={entry.message.content} clarification={entry.clarifyingQuestion} followUps={entry.followUpOptions} onFollowUp={value => { setQuestion(value); composer.current?.focus() }} /> : entry.message.content}</div>
            {entry.message.role === 'student' && Array.isArray(entry.attachments) && <ul className="aura-home__sent-images" aria-label="Materials sent with this question">{entry.attachments.filter(item => item && typeof item.filename === 'string').map((item, index) => <li key={index}>{imageFilename(item.filename) ? `Image ${index+1}: ` : ''}{item.filename}</li>)}</ul>}
            {entry.message.role === 'student' && <button type="button" className="aura-home__plan-link" disabled={sending} onClick={() => { setQuestion(entry.message.content); composer.current?.focus() }}>Edit &amp; resend</button>}
            {entry.stopped && <span className="aura-stopped">■ Stopped</span>}
            {entry.message.role === 'student' && onCreateStudyPlan && /\b(?:study plan|revision plan|exam|prepare for|study goal|\d+[- ]day plan)\b/i.test(entry.message.content) && <button className="aura-home__plan-link" type="button" onClick={() => onCreateStudyPlan(entry.message.content, uploaded?.sourceId)}>Turn this into a study plan ↗</button>}
            {entry.message.role === 'tutor' && entry.answerMode && <small>{entry.answerMode === 'visual' ? 'Visual interpretation — check against the image' : entry.answerMode === 'excerpt' ? 'Quoted source excerpts — explanation unavailable' : entry.answerMode === 'source_plus_background' ? 'Source-backed section + separately labelled background' : entry.answerMode === 'general_background' ? 'General background — outside your material' : (entry.answerMode === 'source' || entry.grounded) ? 'Source checked' : 'Answer could not be verified'}</small>}
            {chatCitationGroups(entry.message.content, entry.citations, id => fileNames[id] ?? `Source ${id}`).length > 0 && <details className="aura-home__sources">
              <summary className="aura-home__source-heading">Sources</summary>
              {chatCitationGroups(entry.message.content, entry.citations, id => fileNames[id] ?? `Source ${id}`).map(citation => <button key={`${citation.source_id}:${citation.id}`} className="aura-home__citation" type="button" onClick={() => setOpenCitation(citation)}>[{citation.referenceIds?.join(', ')}] {citation.title} · {citation.location}</button>)}
            </details>}
          </article>)}
          {partial?.text && <article className="aura-home__message aura-home__message--tutor"><div className="aura-home__speaker">✦ Aura</div><TeachingText text={partial.text} /><span className="aura-stopped">Writing…</span></article>}
          {chatError && <div className="aura-home__error" role="alert">
            <p>{chatError}</p>
            {failedQuestion && <button type="button" onClick={() => void sendQuestion(failedQuestion, true)} disabled={!canSend}>Retry question</button>}
          </div>}
          <div ref={conversationEnd} />
        </section>}

        <div className="aura-home__composer-area">
          {studentName && <UploadBatchStatus entries={uploadEntries} busy={sending || uploadEntries.some(entry => entry.state === 'waiting' || entry.state === 'uploading')} onRetry={() => void uploadFiles(uploadEntries.filter(entry => entry.state === 'failed').map(entry => entry.file), true)} />}
          {studentName && <PreparationStatus pendingIds={[...new Set([...preparationIds, ...imageAttachments.flatMap(item => item.jobId ? [item.jobId] : [])])]} courseId={courseId} refreshKey={preparationRefresh} pendingId={preparationId} onReady={preparationReady} onFailed={preparationFailed} />}
          {coursesError && <div className="aura-home__error" role="alert">Aura couldn't connect. Please refresh and try again.</div>}
          {coursesLoading && <p className="aura-home__loading" role="status">Getting Aura ready…</p>}
          {!coursesLoading && !coursesError && !courseId && <p className="aura-home__loading" role="status">Aura isn't ready yet. Please try again shortly.</p>}
          {uploadError && <div className="aura-home__error" role="alert">
            <p>{uploadError}</p>
            {canEmbed && uploaded?.courseId === courseId && <button type="button" onClick={() => void retryEmbeddings()} disabled={busy}>Retry preparation</button>}
          </div>}

          <GenerationStatus active={generation.active} cancelling={generation.state === 'cancelling'} stopped={generation.state === 'stopped' || generation.state === 'cancelled' ? generation.state : undefined} slow={generation.slow} notice={generation.notice} onStop={() => void generation.stop()} onKeepWaiting={generation.keepWaiting} />
          <form className="aura-home__composer" onSubmit={submit}>
            {imageAttachments.length > 0 && <div className="aura-home__image-attachments" role="group" aria-label="Attached screenshots" aria-live="polite">
              {imageAttachments.map((item, index) => <div className={`aura-home__attachment aura-home__attachment--${item.stage}`} key={item.key}>
                <span className="aura-home__file-icon" aria-hidden="true">▧</span><strong title={item.filename}>Image {index+1}: {item.filename}</strong>
                <span className="aura-home__file-state">{item.stage === 'ready' ? 'Ready' : item.stage === 'failed' ? 'Needs attention' : 'Preparing…'}</span>
                <button type="button" disabled={sending || uploadEntries.some(entry => ['waiting', 'uploading'].includes(entry.state))} onClick={() => removeAttachment(item.key)} aria-label={`Remove ${item.filename}`}>×</button>
                {item.error && <small role="alert">{item.error}</small>}
              </div>)}
            </div>}
            {!imageAttachments.length && uploadStage !== 'idle' && <div className={`aura-home__attachment aura-home__attachment--${uploadStage}`} aria-live="polite">
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
              {!busy && <button type="button" onClick={() => removeAttachment()} aria-label="Remove attachment from this conversation">×</button>}
            </div>}
            <label className="aura-home__sr-only" htmlFor="aura-question">Ask Aura a question</label>
            <textarea ref={composer} id="aura-question" value={question} rows={1} maxLength={12000}
              onChange={event => setQuestion(event.target.value)} onKeyDown={handleKey}
              onPaste={event => { const images = Array.from(event.clipboardData.files).filter(file => imageFilename(file.name)); if (images.length) void uploadFiles(images) }}
              placeholder={hasConversation ? 'Ask another question…' : 'Ask Aura about your materials…'} disabled={sending || uploadEntries.some(entry => ['waiting', 'uploading'].includes(entry.state))} />
            <div className="aura-home__composer-controls">
              <div className="aura-home__upload-control" onKeyDown={event => { if (event.key === 'Escape') setUploadMenu(false) }}>
                <button type="button" className="aura-home__plus" aria-label="Add study material"
                  aria-expanded={uploadMenu} aria-controls="aura-upload-panel"
                  disabled={sending || uploadEntries.some(entry => ['waiting', 'uploading'].includes(entry.state)) || !courseId || Boolean(coursesError)} onClick={() => setUploadMenu(current => !current)}>+</button>
                {uploadMenu && <div id="aura-upload-panel" className="aura-home__upload-panel">
                  <label htmlFor="aura-file">Upload study material</label>
                  <p>Attach up to 5 JPEG/PNG screenshots to one question, together or one at a time. You can also study a PDF, DOCX, presentation, audio or MP4. Each file can be up to 100 MiB.</p>
                  <input ref={fileInput} id="aura-file" type="file" multiple accept=".pdf,.docx,.ppt,.pptx,.jpg,.jpeg,.png,audio/*,.mp4" onChange={event => void uploadFile(event)} />
                </div>}
              </div>
              <span className="aura-home__composer-hint">{sending ? 'Thinking…' : ''}</span>
              {generation.active ? <button type="button" className="aura-home__send" aria-label="Stop generation" onClick={() => void generation.stop()}>■</button> : <button type="submit" className="aura-home__send" aria-label="Send question" disabled={!canSend || !question.trim()}>↑</button>}
            </div>
          </form>
          {!hasConversation && <p className="aura-home__footnote">Check the sources as you learn.</p>}
          {!hasConversation && <div className="aura-home__formats">PDF <span>·</span> PowerPoint <span>·</span> Notes <span>·</span> Audio & video</div>}
        </div>
      </main>
      {!hasConversation && <footer className="aura-home__footer">A little curiosity goes a long way.</footer>}
      <SourceViewer citation={openCitation} onClose={() => setOpenCitation(null)} />
    </div>
  )
}

