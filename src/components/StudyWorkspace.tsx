import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import type { Course } from '../types/study'
import type { AuthUser } from '../services/authApi'
import { askTutor, generateSourceEmbeddings, uploadCourseSource } from '../services/studyApi'
import { generateTool, getPracticeProgress, listArtifacts, listMaterials, setMaterialArchived, submitAssessment } from '../services/studyToolsApi'
import type { Artifact, Material, PracticeProgress, ToolCitation, ToolKind } from '../services/studyToolsApi'
import { readWorkspace, saveWorkspace } from '../services/workspaceStorage'
import './StudyWorkspace.css'

type Tab = 'Overview' | 'Tutor' | 'Notes' | 'Summary' | 'Flashcards' | 'Assessment' | 'Progress'
const tabs: Tab[] = ['Overview', 'Tutor', 'Notes', 'Summary', 'Flashcards', 'Assessment', 'Progress']
const iconPaths = ['M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z', 'M4 4h16v12H9l-5 4z', 'M5 5h14 M5 10h14 M5 15h14 M5 20h9', 'M5 4h14v16H5z M8 8h8 M8 12h8 M8 16h5', 'M7 3h14v15H7z M3 7v14h14', 'M4 12l5 5L20 6', 'M4 19V5 M4 19h16 M7 15l4-5 4 2 5-7']
function WorkspaceIcon({ path }: { path: string }) { return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={path} /></svg> }
const kinds: Partial<Record<Tab, ToolKind>> = { Notes: 'notes', Summary: 'summary', Flashcards: 'flashcards', Assessment: 'assessment' }
type ChatEntry = { role: 'user' | 'assistant'; text: string; grounded?: boolean; citations?: ToolCitation[] }
type Saved = { sourceId?: string; tab?: Tab; selectedArtifact?: string; question?: string; chats?: Record<string, ChatEntry[]>; answers?: Record<string, Record<string, string>> }
type Props = { user: AuthUser; courses: Course[]; courseId: string; coursesLoading: boolean; coursesError: string; theme: 'light' | 'dark'; onCourseChange: (id: string) => void; onThemeChange: () => void; onChatHome: () => void; onSignOut: () => void; signingOut: boolean; sessionNotice: string }
const explainError = (error: unknown) => error instanceof Error ? error.message : 'Could not complete this request. Please retry.'

function SourceButtons({ ids, citations, onOpen }: { ids: number[]; citations: ToolCitation[]; onOpen: (citation: ToolCitation) => void }) {
  return <div className="sw-citations">{ids.map(id => {
    const citation = citations.find(item => item.id === id)
    return citation ? <button key={id} type="button" onClick={() => onOpen(citation)} title={citation.title}>[{id}] {citation.location}</button> : null
  })}</div>
}

export default function StudyWorkspace(props: Props) {
  const { user, courseId, theme } = props
  const storageKey = `aura.study.v1:${user.id}:${courseId}`
  const [saved] = useState(() => readWorkspace<Saved>(storageKey, {}))
  const [tab, setTab] = useState<Tab>(saved.tab && tabs.includes(saved.tab) ? saved.tab : 'Overview')
  const [sourceId, setSourceId] = useState(typeof saved.sourceId === 'string' ? saved.sourceId : '')
  const [materials, setMaterials] = useState<Material[]>([])
  const [materialSearch, setMaterialSearch] = useState('')
  const [showArchived, setShowArchived] = useState(false)
  const [materialNotice, setMaterialNotice] = useState('')
  const [materialsLoading, setMaterialsLoading] = useState(true)
  const [artifacts, setArtifacts] = useState<Artifact[]>([])
  const [artifactsLoading, setArtifactsLoading] = useState(false)
  const [selectedArtifact, setSelectedArtifact] = useState(saved.selectedArtifact ?? '')
  const [question, setQuestion] = useState(typeof saved.question === 'string' ? saved.question : '')
  const [chats, setChats] = useState<Record<string, ChatEntry[]>>(saved.chats && typeof saved.chats === 'object' && !Array.isArray(saved.chats) ? saved.chats : {})
  const [answers, setAnswers] = useState<Record<string, Record<string, string>>>(saved.answers && typeof saved.answers === 'object' && !Array.isArray(saved.answers) ? saved.answers : {})
  const [count, setCount] = useState(3)
  const [focus, setFocus] = useState('')
  const [difficulty, setDifficulty] = useState('beginner')
  const [questionType, setQuestionType] = useState('mcq')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [materialsError, setMaterialsError] = useState('')
  const [artifactsError, setArtifactsError] = useState('')
  const [progressError, setProgressError] = useState('')
  const [progress, setProgress] = useState<PracticeProgress | null>(null)
  const [reload, setReload] = useState(0)
  const [progressReload, setProgressReload] = useState(0)
  const [openCitation, setOpenCitation] = useState<ToolCitation | null>(null)
  const [flipped, setFlipped] = useState<Record<string, boolean>>({})
  const fileInput = useRef<HTMLInputElement>(null)
  const citationDialog = useRef<HTMLDialogElement>(null)
  const busyRef = useRef(false)
  const mounted = useRef(true)
  const chatEnd = useRef<HTMLDivElement>(null)
  const activeMaterials = materials.filter(item => !item.archived)
  const archivedCount = materials.filter(item => item.archived).length
  const visibleMaterials = materials.filter(item => Boolean(item.archived) === showArchived && item.title.toLocaleLowerCase().includes(materialSearch.trim().toLocaleLowerCase()))
  const material = activeMaterials.find(item => item.id === sourceId)
  const kind = kinds[tab]
  const available = artifacts.filter(item => item.kind === kind)
  const active = available.find(item => item.id === selectedArtifact) ?? available[0]
  const entries = Array.isArray(chats[sourceId]) ? chats[sourceId].filter(item => item && typeof item.text === 'string' && ['user', 'assistant'].includes(item.role)) : []
  const draftAnswers = active && answers[active.id] && typeof answers[active.id] === 'object' ? answers[active.id] : {}

  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  useEffect(() => {
    saveWorkspace(storageKey, { sourceId, tab, selectedArtifact, question, chats, answers })
  }, [storageKey, sourceId, tab, selectedArtifact, question, chats, answers])
  useEffect(() => {
    let cancelled = false
    if (!courseId) { setMaterialsLoading(false); return }
    setMaterialsLoading(true); setMaterialsError('')
    listMaterials(courseId).then(items => {
      if (cancelled) return
      setMaterials(items)
      const visible = items.filter(item => !item.archived)
      setSourceId(current => {
        if (visible.some(item => item.id === current)) return current
        const home = readWorkspace<{ uploaded?: { sourceId?: string } }>(`aura.chat.v1:${user.id}:${courseId}`, {})
        const ready = visible.filter(item => item.status === 'success' || item.status === 'partial' || item.status === 'ready')
        return visible.find(item => item.id === home.uploaded?.sourceId)?.id ?? ready.at(-1)?.id ?? visible.at(-1)?.id ?? ''
      })
    }).catch(cause => { if (!cancelled) setMaterialsError(explainError(cause)) })
      .finally(() => { if (!cancelled) setMaterialsLoading(false) })
    return () => { cancelled = true }
  }, [courseId, user.id, reload])
  useEffect(() => {
    let cancelled = false
    setArtifacts([]); setArtifactsError('')
    if (!courseId || !sourceId) { setArtifactsLoading(false); return }
    setArtifactsLoading(true)
    listArtifacts(courseId, sourceId).then(items => { if (!cancelled) setArtifacts(items) })
      .catch(cause => { if (!cancelled) setArtifactsError(explainError(cause)) })
      .finally(() => { if (!cancelled) setArtifactsLoading(false) })
    return () => { cancelled = true }
  }, [courseId, sourceId, reload])
  useEffect(() => {
    let cancelled = false
    if (!courseId) return
    setProgressError('')
    setProgress(null)
    getPracticeProgress(courseId).then(value => { if (!cancelled) setProgress(value) })
      .catch(cause => { if (!cancelled) setProgressError(explainError(cause)) })
    return () => { cancelled = true }
  }, [courseId, progressReload])
  useEffect(() => {
    if (openCitation) citationDialog.current?.showModal()
    else citationDialog.current?.close()
  }, [openCitation])
  useEffect(() => { if (tab === 'Tutor') chatEnd.current?.scrollIntoView({ block: 'nearest' }) }, [chats, tab, busy])

  function selectTab(next: Tab) { setTab(next); setError(''); setOpenCitation(null) }
  function begin(label: string) { if (busyRef.current) return false; busyRef.current = true; setBusy(label); setError(''); return true }
  function end() { busyRef.current = false; if (mounted.current) setBusy('') }
  async function archiveMaterial(item: Material, archived: boolean) {
    if (!begin(archived ? 'Archiving material…' : 'Restoring material…')) return
    setMaterialNotice('')
    try {
      await setMaterialArchived(courseId, item.id, archived)
      if (!mounted.current) return
      setMaterials(current => current.map(material => material.id === item.id ? { ...material, archived } : material))
      if (archived && sourceId === item.id) {
        setSourceId(activeMaterials.find(material => material.id !== item.id)?.id ?? '')
        setSelectedArtifact(''); setFlipped({}); setFocus(''); setOpenCitation(null)
      }
      if (!archived && !sourceId) setSourceId(item.id)
      setMaterialNotice(archived ? `${item.title} archived. Your saved work is kept.` : `${item.title} restored.`)
    } catch (cause) { if (mounted.current) setError(explainError(cause)) }
    finally { end() }
  }
  async function upload(file?: File) {
    if (!file || !courseId || !begin('Uploading and reading your material…')) return
    try {
      const result = await uploadCourseSource(courseId, file)
      if (!mounted.current) return
      if (!['success', 'partial'].includes(result.processingStatus) || result.contentUnitCount < 1) throw new Error('No readable content was found. Try another file.')
      setShowArchived(false); setMaterialSearch(''); setMaterialNotice('')
      setSourceId(result.sourceId)
      setMaterials(current => [...current, { id: result.sourceId, title: result.filename, type: result.fileType, status: result.processingStatus }])
      setBusy('Indexing your material for the tutor…')
      await generateSourceEmbeddings(result.sourceId)
      if (mounted.current) { setReload(value => value + 1); setTab('Tutor') }
    } catch (cause) { if (mounted.current) setError(explainError(cause)) }
    finally { end(); if (fileInput.current) fileInput.current.value = '' }
  }
  async function generate() {
    if (!kind || !sourceId || !begin('Creating and checking your study material…')) return
    try {
      const generated = await generateTool(courseId, sourceId, kind, { count, focus, difficulty, questionType })
      if (mounted.current) { setArtifacts(current => [generated, ...current]); setSelectedArtifact(generated.id); setFlipped({}) }
    } catch (cause) { if (mounted.current) setError(explainError(cause)) }
    finally { end() }
  }
  async function send(event: FormEvent) {
    event.preventDefault()
    const text = question.trim()
    if (!text || !sourceId || !begin('Aura is thinking…')) return
    setQuestion('')
    setChats(current => ({ ...current, [sourceId]: [...entries, { role: 'user', text }] }))
    try {
      const response = await askTutor({ courseId, materialId: sourceId, question: text,
        history: entries.filter(item => item.role === 'user' || item.grounded).slice(-8).map(item => ({ role: item.role, content: item.text })) })
      const citations: ToolCitation[] = response.citations.map((citation, index) => {
        const location = citation.location
        const label = location.kind === 'pdf_page' ? `Page ${location.page}` : location.kind === 'slide' ? `Slide ${location.slide}` : `${Math.floor(location.seconds / 60)}:${String(Math.floor(location.seconds % 60)).padStart(2, '0')}`
        return { id: index + 1, chunk_id: 0, source_id: Number(citation.sourceId), title: material?.title ?? 'Source', location: label, excerpt: citation.excerpt ?? '' }
      })
      if (mounted.current) setChats(current => ({ ...current, [sourceId]: [...(current[sourceId] ?? []), { role: 'assistant', text: response.message.content, grounded: response.groundingStatus === 'grounded', citations }] }))
    } catch (cause) { if (mounted.current) { setError(explainError(cause)); setQuestion(text) } }
    finally { end() }
  }
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!active || !begin('Checking your answers…')) return
    try {
      const result = await submitAssessment(active.id, draftAnswers)
      if (mounted.current) { setArtifacts(current => current.map(item => item.id === active.id ? { ...item, result } : item)); setProgressReload(value => value + 1) }
    } catch (cause) { if (mounted.current) setError(explainError(cause)) }
    finally { end() }
  }
  function exportTool() {
    if (!active) return
    const blocks = active.payload.items.map(item => `${item.title ?? item.question ?? item.prompt ?? ''}\n${item.text ?? item.answer ?? ''}\n${item.citation_ids.map(id => `[${id}]`).join(' ')}`)
    const references = active.payload.citations.map(citation => `[${citation.id}] ${citation.title} · ${citation.location}\n${citation.excerpt}`)
    const blob = new Blob([`${tab} — ${active.payload.source_title}\n\n${blocks.join('\n\n')}\n\nSources\n${references.join('\n\n')}`], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a'); link.href = url; link.download = `aura-${active.kind}.txt`; link.click(); URL.revokeObjectURL(url)
  }
  const weakTopics = progress?.topics.filter(item => item.score < 65) ?? []

  return <div className="aura-study" data-theme={theme}>
    <aside className="sw-rail">
      <button className="sw-brand" onClick={props.onChatHome} disabled={!!busy} type="button"><span>A.</span>Aura</button>
      <p className="sw-rail-label">YOUR WORKSPACE</p>
      <nav aria-label="Study tools">{tabs.map((item, index) => <button key={item} type="button" aria-current={tab === item ? 'page' : undefined} className={tab === item ? 'is-active' : ''} onClick={() => selectTab(item)}><span aria-hidden="true"><WorkspaceIcon path={iconPaths[index]} /></span>{item}</button>)}</nav>
      <div className="sw-account"><strong title={user.fullName}>{user.fullName}</strong><small>Study account</small><button type="button" onClick={props.onSignOut} disabled={props.signingOut || !!busy}>{props.signingOut ? 'Signing out…' : 'Sign out'}</button></div>
    </aside>
    <div className="sw-shell">
      <header className="sw-topbar"><div><strong>Study workspace</strong><span className="sw-top-subtitle">Your materials and saved practice</span></div>
        <div className="sw-top-actions"><button type="button" onClick={props.onThemeChange} aria-label={theme === 'light' ? 'Use dark theme' : 'Use light theme'}><WorkspaceIcon path={theme === 'light' ? 'M20 15a8 8 0 01-11-11 8 8 0 1011 11z' : 'M12 3v2 M12 19v2 M3 12h2 M19 12h2 M5 5l2 2 M17 17l2 2 M5 19l2-2 M17 7l2-2 M16 12a4 4 0 11-8 0 4 4 0 018 0z'} /></button><button type="button" onClick={props.onChatHome} disabled={!!busy}>Chat home</button></div>
      </header>
      {(props.sessionNotice || props.coursesError) && <p className="sw-error" role="alert">{props.sessionNotice || props.coursesError}</p>}
      <div className="sw-body">
        <aside className="sw-materials"><div className="sw-material-heading"><h2>Materials</h2><button type="button" aria-label="Refresh materials" disabled={!!busy || materialsLoading} onClick={() => setReload(value => value + 1)}>↻</button></div>
          <button type="button" className="sw-add" disabled={!!busy || !courseId} onClick={() => fileInput.current?.click()}>＋ Add material</button>
          <input ref={fileInput} type="file" hidden accept=".pdf,.docx,.ppt,.pptx,audio/*,.mp4" onChange={event => void upload(event.target.files?.[0])} />
          {materialsLoading && <p className="sw-muted" role="status">Loading materials…</p>}
          {materialsError && <p className="sw-error" role="alert">{materialsError}</p>}
          <label className="sw-material-search"><span className="sw-sr-only">Search materials</span><input type="search" placeholder="Search materials" value={materialSearch} onChange={event => setMaterialSearch(event.target.value)} /></label>
          <div className="sw-material-tabs"><button type="button" aria-pressed={!showArchived} onClick={() => setShowArchived(false)}>Active <span>{activeMaterials.length}</span></button><button type="button" aria-pressed={showArchived} onClick={() => setShowArchived(true)}>Archived <span>{archivedCount}</span></button></div>
          <div className="sw-material-list">{visibleMaterials.map(item => <div key={item.id} className={`sw-material-row ${!showArchived && item.id === sourceId ? 'is-selected' : ''}`}>
            {showArchived ? <div className="sw-archived-title"><strong>{item.title}</strong><small>{item.type.toUpperCase()}</small></div> : <button className="sw-material-select" type="button" disabled={!!busy} aria-current={item.id === sourceId ? 'true' : undefined} onClick={() => { setSourceId(item.id); setSelectedArtifact(''); setError(''); setFlipped({}); setFocus('') }}><span className="sw-file-icon"><WorkspaceIcon path="M6 3h8l4 4v14H6z M14 3v5h4 M9 12h6 M9 16h6" /></span><span><strong>{item.title}</strong><small>{item.type.toUpperCase()}{['empty', 'error', 'not_configured'].includes(item.status) ? ' · Needs attention' : ''}</small></span></button>}
            <button className="sw-material-action" type="button" disabled={!!busy} aria-label={`${showArchived ? 'Restore' : 'Archive'} ${item.title}`} title={showArchived ? 'Restore to active materials' : 'Archive material; saved work is kept'} onClick={() => void archiveMaterial(item, !showArchived)}><WorkspaceIcon path={showArchived ? 'M5 9a8 8 0 111 9 M5 4v5h5' : 'M3 4h18v4H3z M5 8v12h14V8 M9 12h6'} /></button>
          </div>)}</div>
          {!materialsLoading && !visibleMaterials.length && !materialsError && <p className="sw-material-empty">{materialSearch ? 'No matching materials.' : showArchived ? 'No archived materials.' : 'Add a file or restore an archived material.'}</p>}
          {materialNotice && <p className="sw-material-notice" role="status">{materialNotice}</p>}
          <p className="sw-material-footnote">All tools use the selected material.</p>
        </aside>
        <main className="sw-main">
          <div className="sw-heading"><div><p className="sw-eyebrow">{tab === 'Progress' ? 'All materials in this course' : material?.title ?? 'Your study materials'}</p><h1>{tab === 'Overview' ? 'Overview' : tab === 'Tutor' ? 'Ask Aura' : tab}</h1></div>{tab !== 'Overview' && tab !== 'Progress' && <span className="sw-source-badge">{material ? 'Selected material' : 'Choose a material'}</span>}</div>
          {error && <p className="sw-error" role="alert">{error}</p>}
          {busy && <div className="sw-status" role="status"><span className="sw-spinner" aria-hidden="true" />{busy}</div>}
          {tab === 'Overview' && <>
            <section className="sw-start"><span className="sw-eyebrow">CONTINUE WITH</span><h2>{material?.title ?? 'Your first study material'}</h2><p>{material ? 'Ask a question, build revision material, or check what you know.' : 'Upload a lecture, textbook, or presentation to get started.'}</p><button className="sw-primary" type="button" disabled={!material} onClick={() => selectTab('Tutor')}>Open tutor →</button></section>
            <div className="sw-tool-grid">{(['Notes', 'Summary', 'Flashcards', 'Assessment'] as Tab[]).map(item => <button key={item} type="button" onClick={() => selectTab(item)}><strong>{item}</strong><span>{item === 'Notes' ? 'Organize key explanations' : item === 'Summary' ? 'Review the main ideas' : item === 'Flashcards' ? 'Practice active recall' : 'Test your understanding'}</span><span aria-hidden="true">↗</span></button>)}</div>
            <section className="sw-section"><h2>Recent study material</h2>{artifactsLoading ? <p className="sw-muted">Loading your saved work…</p> : artifactsError ? <p className="sw-error">{artifactsError}</p> : artifacts.length ? <div className="sw-recent">{artifacts.slice(0, 5).map(item => <button key={item.id} type="button" onClick={() => { setSelectedArtifact(item.id); selectTab(item.kind === 'assessment' ? 'Assessment' : item.kind === 'notes' ? 'Notes' : item.kind === 'summary' ? 'Summary' : 'Flashcards') }}><span>{item.kind.charAt(0).toUpperCase() + item.kind.slice(1)}</span><small>{new Date(item.created_at).toLocaleDateString()} · {item.payload.items.length} {item.kind === 'assessment' ? 'questions' : 'items'}</small><span>→</span></button>)}</div> : <p className="sw-muted">Your generated notes, cards, and assessments will appear here.</p>}</section>
            {weakTopics.length > 0 && <section className="sw-section"><h2>Suggested review</h2><p className="sw-muted">Based on your completed practice.</p>{weakTopics.slice(0, 3).map(item => <button className="sw-review" key={item.topic} type="button" onClick={() => { setFocus(item.topic); selectTab('Flashcards') }}>{item.topic}<span>Create review cards →</span></button>)}</section>}
          </>}
          {tab === 'Tutor' && <section className="sw-tutor"><div className="sw-transcript" aria-live="polite">{!entries.length && <div className="sw-chat-empty"><span>✦</span><h2>What would you like to understand?</h2><p>Ask about {material?.title ?? 'a material you select'}.</p><div>{['Explain the main ideas', 'Help me revise this material'].map(prompt => <button key={prompt} type="button" onClick={() => setQuestion(prompt)}>{prompt}</button>)}</div></div>}{entries.map((entry, index) => <article key={index} className={`sw-chat-entry ${entry.role}`}><strong>{entry.role === 'user' ? 'You' : '✦ Aura'}</strong><p>{entry.text}</p>{entry.role === 'assistant' && <><span className="sw-grounding">{entry.grounded ? 'Source checked' : 'Contains unverified content — see answer label'}</span>{entry.citations?.length ? <SourceButtons ids={entry.citations.map(c => c.id)} citations={entry.citations} onOpen={setOpenCitation} /> : null}</>}</article>)}<div ref={chatEnd} /></div><form className="sw-composer" onSubmit={event => void send(event)}><label className="sw-sr-only" htmlFor="sw-question">Ask Aura a question</label><textarea id="sw-question" rows={2} value={question} disabled={!sourceId || !!busy} onChange={event => setQuestion(event.target.value)} placeholder={sourceId ? 'Ask a question about this material…' : 'Select or add a material first'} /><button className="sw-primary" type="submit" disabled={!sourceId || !question.trim() || !!busy}>Send ↑</button></form></section>}
          {kind && <>
            <form className="sw-generation" onSubmit={event => { event.preventDefault(); void generate() }}><label className="sw-focus">Focus <span>(optional)</span><input value={focus} maxLength={180} onChange={event => setFocus(event.target.value)} placeholder="e.g. cytoskeleton functions" disabled={!!busy} /></label>{kind !== 'summary' && <label>{kind === 'assessment' ? 'Questions' : 'Items'}<select value={count} disabled={!!busy} onChange={event => setCount(Number(event.target.value))}>{[1, 2, 3, 4, 5].map(value => <option key={value} value={value}>{value}</option>)}</select></label>}{kind === 'assessment' && <><label>Format<select value={questionType} disabled={!!busy} onChange={event => setQuestionType(event.target.value)}><option value="mcq">Multiple choice</option><option value="short_answer">Short answer</option></select></label><label>Difficulty<select value={difficulty} disabled={!!busy} onChange={event => setDifficulty(event.target.value)}>{['beginner', 'intermediate', 'advanced'].map(value => <option key={value} value={value}>{value}</option>)}</select></label></>}<button className="sw-primary" disabled={!sourceId || !!busy || artifactsLoading || !!artifactsError} type="submit">{active ? 'Generate new' : 'Generate'}</button></form>
            {artifactsError && <p className="sw-error" role="alert">{artifactsError} <button type="button" onClick={() => setReload(value => value + 1)}>Retry</button></p>}
            {artifactsLoading ? <p className="sw-muted" role="status">Loading saved work…</p> : !active ? <div className="sw-empty"><span>{tab === 'Assessment' ? '✓' : '▤'}</span><h2>{sourceId ? `Create your first ${tab.toLowerCase()}` : 'Choose a material first'}</h2><p>{sourceId ? 'Aura will generate content from selected passages and check its sources before saving.' : 'Select a file from the materials list or upload one.'}</p></div> : <>
              <div className="sw-output-toolbar"><label>Saved version<select aria-label="Saved version" value={active.id} disabled={!!busy} onChange={event => { setSelectedArtifact(event.target.value); setFlipped({}) }}>{available.map(item => <option key={item.id} value={item.id}>{new Date(item.created_at).toLocaleString()}{item.payload.focus ? ` · ${item.payload.focus}` : ''}</option>)}</select></label>{kind !== 'assessment' && <button type="button" onClick={exportTool}>Export text ↓</button>}</div>
              <p className="sw-coverage">Based on {active.payload.coverage.selected_passages} selected passages from this material. Sources are model checked.</p>
              {active.payload.notice && <p className="sw-status" role="status">{active.payload.notice}</p>}
              {(kind === 'notes' || kind === 'summary') && <div className="sw-reading">{active.payload.items.map(item => <article key={item.id}><h2>{item.title}</h2><p>{item.text}</p><SourceButtons ids={item.citation_ids} citations={active.payload.citations} onOpen={setOpenCitation} /></article>)}</div>}
              {kind === 'flashcards' && <div className="sw-flashcards">{active.payload.items.map((item, index) => <article key={item.id}><span className="sw-eyebrow">CARD {index + 1} OF {active.payload.items.length}</span><h2>{item.question}</h2><button className="sw-reveal" type="button" aria-expanded={!!flipped[item.id]} onClick={() => setFlipped(current => ({ ...current, [item.id]: !current[item.id] }))}>{flipped[item.id] ? 'Hide answer' : 'Reveal answer'}</button>{flipped[item.id] && <div className="sw-card-answer"><p>{item.answer}</p><SourceButtons ids={item.citation_ids} citations={active.payload.citations} onOpen={setOpenCitation} /></div>}</article>)}</div>}
              {kind === 'assessment' && (!active.result ? <form className="sw-assessment" onSubmit={event => void submit(event)}>{active.payload.items.map((item, index) => <fieldset key={item.id} disabled={!!busy}><legend><small>QUESTION {index + 1} · {item.difficulty} · {item.topic}</small>{item.prompt}</legend>{item.kind === 'mcq' ? item.choices?.map(choice => <label key={choice.id} className={draftAnswers[item.id] === choice.id ? 'is-chosen' : ''}><input type="radio" name={item.id} value={choice.id} required checked={draftAnswers[item.id] === choice.id} onChange={() => setAnswers(current => ({ ...current, [active.id]: { ...draftAnswers, [item.id]: choice.id } }))} /><span>{choice.id}</span>{choice.text}</label>) : <textarea aria-label={`Answer question ${index + 1}`} required rows={3} maxLength={3000} value={draftAnswers[item.id] ?? ''} onChange={event => setAnswers(current => ({ ...current, [active.id]: { ...draftAnswers, [item.id]: event.target.value } }))} />}<SourceButtons ids={item.citation_ids} citations={active.payload.citations} onOpen={setOpenCitation} /></fieldset>)}<button className="sw-primary" type="submit" disabled={!!busy || active.payload.items.some(item => !draftAnswers[item.id]?.trim())}>Submit assessment</button></form> : <section className="sw-report"><div className="sw-report-heading"><div><span className="sw-eyebrow">ASSESSMENT COMPLETE</span><h2>{active.result.correct_count} of {active.result.question_count} correct</h2></div><strong>{active.result.score}%</strong></div><p>{active.result.recommended_action}</p>{active.result.feedback.map((item, index) => <article key={item.question_id}><small className={item.correct ? 'sw-correct' : 'sw-incorrect'}>{item.correct ? 'Correct' : 'Review this'} · QUESTION {index + 1}</small><h3>{item.prompt}</h3><p><strong>Your answer:</strong> {item.submitted_answer}</p><p><strong>Expected answer:</strong> {item.expected_answer}</p><p>{item.explanation}</p><SourceButtons ids={item.citation_ids} citations={active.payload.citations} onOpen={setOpenCitation} /><button type="button" className="sw-link" onClick={() => { setFocus(item.topic); selectTab('Flashcards') }}>Review {item.topic} →</button></article>)}</section>)}
            </>}
          </>}
          {tab === 'Progress' && <section className="sw-progress">{progressError ? <p className="sw-error" role="alert">{progressError} <button type="button" onClick={() => setProgressReload(value => value + 1)}>Retry</button></p> : !progress ? <p role="status">Loading progress…</p> : <ProgressDashboard progress={progress} onPractice={() => selectTab('Assessment')} />}</section>}
        </main>
      </div>
    </div>
    <dialog ref={citationDialog} className="sw-source-dialog" onCancel={() => setOpenCitation(null)}><header><div><p className="sw-eyebrow">SOURCE EXCERPT</p><h2>{openCitation?.title}</h2><span>{openCitation?.location}</span></div><button type="button" aria-label="Close source excerpt" onClick={() => setOpenCitation(null)}>×</button></header><p>{openCitation?.excerpt || 'No excerpt is available for this source.'}</p><small>Extracted text from this location; this is not a full document preview.</small></dialog>
  </div>
}

function ProgressDashboard({ progress, onPractice }: { progress: PracticeProgress; onPractice: () => void }) {
  const [topicSort, setTopicSort] = useState<'accuracy' | 'volume'>('accuracy')
  const correct = progress.correct_count ?? progress.topics.reduce((sum, item) => sum + item.correct, 0)
  const accuracy = progress.question_count ? Math.round(100 * correct / progress.question_count) : null
  const history = progress.score_history ?? [...progress.recent_results].reverse()
  const topics = [...progress.topics].sort((a, b) => topicSort === 'volume' ? b.total - a.total || a.score - b.score : a.score - b.score || b.total - a.total)
  const latest = history.at(-1)
  const x = (index: number) => history.length === 1 ? 300 : 46 + index * 520 / (history.length - 1)
  const y = (score: number) => 174 - score * 1.4
  const points = history.map((item, index) => `${x(index)},${y(item.score)}`).join(' ')
  function when(value?: string | null) {
    if (!value || Number.isNaN(Date.parse(value))) return 'Date unavailable'
    return new Date(value).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
  }
  return <>
    <div className="sw-progress-intro"><p className="sw-muted">See how your assessment scores change and where to focus your next practice.</p><button type="button" onClick={onPractice}>Take an assessment →</button></div>
    <div className="sw-progress-stats">
      <div><span>Practice accuracy</span><strong>{accuracy === null ? '—' : `${accuracy}%`}</strong><small>{correct} correct out of {progress.question_count}</small></div>
      <div><span>Questions answered</span><strong>{progress.question_count}</strong><small>Across {progress.topics.length} practiced topics</small></div>
      <div><span>Assessments completed</span><strong>{progress.assessment_count}</strong><small>Saved in this course</small></div>
      <div><span>Latest score</span><strong>{latest ? `${latest.score}%` : '—'}</strong><small>{latest ? `${latest.correct_count}/${latest.question_count} correct · ${when(latest.completed_at)}` : 'Take your first assessment'}</small></div>
    </div>
    {!progress.assessment_count ? <div className="sw-empty"><h3>Your progress starts here</h3><p>Complete an assessment to see your score history and topic results.</p><button type="button" className="sw-primary" onClick={onPractice}>Take an assessment →</button></div> : <>
      <div className="sw-progress-charts">
        <section className="sw-progress-panel"><header><div><h2>Assessment score trend</h2><p>Last {history.length} completed assessments · oldest to newest</p></div><span className="sw-chart-pill">Score %</span></header>
          {history.length ? <><svg className="sw-score-chart" viewBox="0 0 600 215" role="img" aria-label={`Assessment scores in order: ${history.map(item => `${item.score}%`).join(', ')}`}>
            {[0, 25, 50, 75, 100].map(value => <g key={value}><line x1="46" x2="566" y1={y(value)} y2={y(value)} className="sw-chart-grid" /><text x="34" y={y(value) + 4} textAnchor="end">{value}</text></g>)}
            {history.length > 1 && <><polygon points={`46,174 ${points} 566,174`} className="sw-chart-area" /><polyline points={points} className="sw-chart-line" /></>}
            {history.map((item, index) => <g key={index}><circle cx={x(index)} cy={y(item.score)} r="5" tabIndex={0} aria-label={`Assessment ${index + 1}: ${item.score}%, ${item.correct_count} of ${item.question_count} correct`}><title>{when(item.completed_at)} · {item.score}% · {item.correct_count}/{item.question_count} correct</title></circle>{(index === 0 || index === history.length - 1) && <text x={x(index)} y="200" textAnchor="middle">{when(item.completed_at)}</text>}</g>)}
          </svg>{history.length === 1 && <p className="sw-chart-note">One result so far. Your trend appears as you complete more assessments.</p>}</> : <p className="sw-muted">No score history available yet.</p>}
        </section>
        <section className="sw-progress-panel sw-practice-next"><header><div><h2>Where to focus next</h2><p>Based on your answered questions</p></div></header>
          {topics.filter(item => item.score < 65).length ? topics.filter(item => item.score < 65).slice(0, 3).map(item => <div className="sw-focus-topic" key={item.topic}><strong>{item.topic}</strong><span>{item.correct}/{item.total} correct · {item.score}% accuracy</span></div>) : <div className="sw-focus-topic"><strong>Build on your current results</strong><span>Try another assessment to check more topics.</span></div>}
          <p className="sw-chart-note">Small question counts give limited evidence. Scores reflect practice accuracy; difficulty and topic scope can differ between assessments.</p>
        </section>
      </div>
      <section className="sw-progress-panel"><header><div><h2>Questions by topic</h2><p>Correct and incorrect answers across your saved assessments</p></div><label className="sw-topic-sort">Sort by<select value={topicSort} onChange={event => setTopicSort(event.target.value as 'accuracy' | 'volume')}><option value="accuracy">Needs practice first</option><option value="volume">Most questions answered</option></select></label></header>
        <div className="sw-chart-legend"><span><i className="sw-answer-correct" />Correct</span><span><i className="sw-answer-incorrect" />Incorrect</span></div>
        <div className="sw-topic-results">{topics.map(item => <div className="sw-topic-result" key={item.topic}><div><strong>{item.topic}</strong><small>{item.total} answered · {item.correct} correct · {item.total - item.correct} incorrect{item.total < 5 ? ' · Limited evidence' : ''}</small></div><div className="sw-topic-bar" role="img" aria-label={`${item.topic}: ${item.correct} correct and ${item.total - item.correct} incorrect`}><span className="sw-answer-correct" style={{ width: `${item.score}%` }} /><span className="sw-answer-incorrect" style={{ width: `${100 - item.score}%` }} /></div><strong className="sw-topic-accuracy">{item.score}%</strong></div>)}</div>
      </section>
      <section className="sw-progress-panel sw-history-panel"><header><div><h2>Recent assessments</h2><p>Your latest saved results</p></div></header><div className="sw-history-table"><table><thead><tr><th>Completed</th><th>Score</th><th>Correct answers</th><th>Topics practiced</th></tr></thead><tbody>{progress.recent_results.map((item, index) => <tr key={`${item.completed_at}-${index}`}><td>{when(item.completed_at)}</td><td><strong>{item.score}%</strong></td><td>{item.correct_count}/{item.question_count}</td><td>{item.topics.map(topic => topic.topic).join(', ')}</td></tr>)}</tbody></table></div></section>
    </>}
  </>
}
