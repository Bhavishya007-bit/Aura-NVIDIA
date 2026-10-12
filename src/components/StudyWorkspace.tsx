import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import type { Course } from '../types/study'
import type { AuthUser } from '../services/authApi'
import { askTutor, generateSourceEmbeddings, uploadCourseSource } from '../services/studyApi'
import { generateTool, getPracticeProgress, listArtifacts, listMaterials, submitAssessment } from '../services/studyToolsApi'
import type { Artifact, Material, PracticeProgress, ToolCitation, ToolKind } from '../services/studyToolsApi'
import { readWorkspace, saveWorkspace } from '../services/workspaceStorage'
import './StudyWorkspace.css'

type Tab = 'Overview' | 'Tutor' | 'Notes' | 'Summary' | 'Flashcards' | 'Assessment' | 'Progress'
const tabs: Tab[] = ['Overview', 'Tutor', 'Notes', 'Summary', 'Flashcards', 'Assessment', 'Progress']
const icons = ['◫', '✦', '≡', '▤', '▱', '✓', '↗']
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
  const { user, courses, courseId, theme } = props
  const storageKey = `aura.study.v1:${user.id}:${courseId}`
  const [saved] = useState(() => readWorkspace<Saved>(storageKey, {}))
  const [tab, setTab] = useState<Tab>(saved.tab && tabs.includes(saved.tab) ? saved.tab : 'Overview')
  const [sourceId, setSourceId] = useState(typeof saved.sourceId === 'string' ? saved.sourceId : '')
  const [materials, setMaterials] = useState<Material[]>([])
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
  const material = materials.find(item => item.id === sourceId)
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
      setSourceId(current => {
        if (items.some(item => item.id === current)) return current
        const home = readWorkspace<{ uploaded?: { sourceId?: string } }>(`aura.chat.v1:${user.id}:${courseId}`, {})
        const ready = items.filter(item => item.status === 'success' || item.status === 'partial' || item.status === 'ready')
        return items.find(item => item.id === home.uploaded?.sourceId)?.id ?? ready.at(-1)?.id ?? items.at(-1)?.id ?? ''
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
  async function upload(file?: File) {
    if (!file || !courseId || !begin('Uploading and reading your material…')) return
    try {
      const result = await uploadCourseSource(courseId, file)
      if (!mounted.current) return
      if (!['success', 'partial'].includes(result.processingStatus) || result.contentUnitCount < 1) throw new Error('No readable content was found. Try another file.')
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
      <nav aria-label="Study tools">{tabs.map((item, index) => <button key={item} type="button" aria-current={tab === item ? 'page' : undefined} className={tab === item ? 'is-active' : ''} onClick={() => selectTab(item)}><span aria-hidden="true">{icons[index]}</span>{item}</button>)}</nav>
      <div className="sw-account"><strong title={user.fullName}>{user.fullName}</strong><small>Study account</small><button type="button" onClick={props.onSignOut} disabled={props.signingOut || !!busy}>{props.signingOut ? 'Signing out…' : 'Sign out'}</button></div>
    </aside>
    <div className="sw-shell">
      <header className="sw-topbar"><div><span className="sw-top-label">STUDY SPACE</span><strong>{courses.find(item => item.id === courseId)?.title ?? 'Choose a course'}</strong></div>
        <div className="sw-top-actions"><select aria-label="Course" value={courseId} disabled={props.coursesLoading || !!busy} onChange={event => props.onCourseChange(event.target.value)}>{!courses.length && <option value="">No courses available</option>}{courses.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select><button type="button" onClick={props.onThemeChange} aria-label={theme === 'light' ? 'Use dark theme' : 'Use light theme'}>{theme === 'light' ? '☾' : '☀'}</button><button type="button" onClick={props.onChatHome} disabled={!!busy}>Chat home</button></div>
      </header>
      {(props.sessionNotice || props.coursesError) && <p className="sw-error" role="alert">{props.sessionNotice || props.coursesError}</p>}
      <div className="sw-body">
        <aside className="sw-materials"><div className="sw-material-heading"><h2>Materials</h2><button type="button" aria-label="Refresh materials" disabled={!!busy || materialsLoading} onClick={() => setReload(value => value + 1)}>↻</button></div>
          <button type="button" className="sw-add" disabled={!!busy || !courseId} onClick={() => fileInput.current?.click()}>＋ Add material</button>
          <input ref={fileInput} type="file" hidden accept=".pdf,.docx,.ppt,.pptx,audio/*,.mp4" onChange={event => void upload(event.target.files?.[0])} />
          {materialsLoading && <p className="sw-muted" role="status">Loading materials…</p>}
          {materialsError && <p className="sw-error" role="alert">{materialsError}</p>}
          <div className="sw-material-list">{materials.map(item => <button key={item.id} type="button" disabled={!!busy} className={item.id === sourceId ? 'is-selected' : ''} onClick={() => { setSourceId(item.id); setSelectedArtifact(''); setError(''); setFlipped({}) }}><span className="sw-file-icon" aria-hidden="true">▤</span><span><strong>{item.title}</strong><small>{item.type.toUpperCase()}{['empty', 'error', 'not_configured'].includes(item.status) ? ' · Needs attention' : ''}</small></span></button>)}</div>
          {!materialsLoading && !materials.length && !materialsError && <p className="sw-muted">Add your first file to start studying.</p>}
          <p className="sw-material-footnote">All tools use the selected material.</p>
        </aside>
        <main className="sw-main">
          <div className="sw-heading"><div><p className="sw-eyebrow">{material?.title ?? 'Your learning, in one place'}</p><h1>{tab === 'Overview' ? 'Let’s keep learning' : tab === 'Tutor' ? 'Ask Aura' : tab}</h1></div>{tab !== 'Overview' && tab !== 'Progress' && <span className="sw-source-badge">{material ? 'Selected material' : 'Choose a material'}</span>}</div>
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
              {(kind === 'notes' || kind === 'summary') && <div className="sw-reading">{active.payload.items.map(item => <article key={item.id}><h2>{item.title}</h2><p>{item.text}</p><SourceButtons ids={item.citation_ids} citations={active.payload.citations} onOpen={setOpenCitation} /></article>)}</div>}
              {kind === 'flashcards' && <div className="sw-flashcards">{active.payload.items.map((item, index) => <article key={item.id}><span className="sw-eyebrow">CARD {index + 1} OF {active.payload.items.length}</span><h2>{item.question}</h2><button className="sw-reveal" type="button" aria-expanded={!!flipped[item.id]} onClick={() => setFlipped(current => ({ ...current, [item.id]: !current[item.id] }))}>{flipped[item.id] ? 'Hide answer' : 'Reveal answer'}</button>{flipped[item.id] && <div className="sw-card-answer"><p>{item.answer}</p><SourceButtons ids={item.citation_ids} citations={active.payload.citations} onOpen={setOpenCitation} /></div>}</article>)}</div>}
              {kind === 'assessment' && (!active.result ? <form className="sw-assessment" onSubmit={event => void submit(event)}>{active.payload.items.map((item, index) => <fieldset key={item.id} disabled={!!busy}><legend><small>QUESTION {index + 1} · {item.difficulty} · {item.topic}</small>{item.prompt}</legend>{item.kind === 'mcq' ? item.choices?.map(choice => <label key={choice.id} className={draftAnswers[item.id] === choice.id ? 'is-chosen' : ''}><input type="radio" name={item.id} value={choice.id} required checked={draftAnswers[item.id] === choice.id} onChange={() => setAnswers(current => ({ ...current, [active.id]: { ...draftAnswers, [item.id]: choice.id } }))} /><span>{choice.id}</span>{choice.text}</label>) : <textarea aria-label={`Answer question ${index + 1}`} required rows={3} maxLength={3000} value={draftAnswers[item.id] ?? ''} onChange={event => setAnswers(current => ({ ...current, [active.id]: { ...draftAnswers, [item.id]: event.target.value } }))} />}<SourceButtons ids={item.citation_ids} citations={active.payload.citations} onOpen={setOpenCitation} /></fieldset>)}<button className="sw-primary" type="submit" disabled={!!busy || active.payload.items.some(item => !draftAnswers[item.id]?.trim())}>Submit assessment</button></form> : <section className="sw-report"><div className="sw-report-heading"><div><span className="sw-eyebrow">ASSESSMENT COMPLETE</span><h2>{active.result.correct_count} of {active.result.question_count} correct</h2></div><strong>{active.result.score}%</strong></div><p>{active.result.recommended_action}</p>{active.result.feedback.map((item, index) => <article key={item.question_id}><small className={item.correct ? 'sw-correct' : 'sw-incorrect'}>{item.correct ? 'Correct' : 'Review this'} · QUESTION {index + 1}</small><h3>{item.prompt}</h3><p><strong>Your answer:</strong> {item.submitted_answer}</p><p><strong>Expected answer:</strong> {item.expected_answer}</p><p>{item.explanation}</p><SourceButtons ids={item.citation_ids} citations={active.payload.citations} onOpen={setOpenCitation} /><button type="button" className="sw-link" onClick={() => { setFocus(item.topic); selectTab('Flashcards') }}>Review {item.topic} →</button></article>)}</section>)}
            </>}
          </>}
          {tab === 'Progress' && <section className="sw-progress"><p className="sw-muted">Practice accuracy from your completed assessments. This is not a measured learning gain or a calibrated mastery estimate.</p>{progressError ? <p className="sw-error" role="alert">{progressError} <button type="button" onClick={() => setProgressReload(value => value + 1)}>Retry</button></p> : !progress ? <p role="status">Loading progress…</p> : <><div className="sw-stat-row"><div><strong>{progress.assessment_count}</strong><span>Assessments completed</span></div><div><strong>{progress.question_count}</strong><span>Questions answered</span></div></div><h2>Topic practice</h2>{!progress.topics.length ? <div className="sw-empty"><h3>Start with a short assessment</h3><p>Your topic results will appear after you submit answers.</p><button type="button" className="sw-primary" onClick={() => selectTab('Assessment')}>Take an assessment →</button></div> : progress.topics.map(item => <div className="sw-topic" key={item.topic}><div><strong>{item.topic}</strong><small>{item.correct}/{item.total} correct · {item.total < 5 ? 'Limited practice evidence' : 'Practice accuracy'}</small></div><progress max={100} value={item.score} aria-label={`${item.topic}: ${item.score}% practice accuracy`} /><span>{item.score}%</span><button type="button" onClick={() => { setFocus(item.topic); selectTab('Flashcards') }}>Review</button></div>)}</>}</section>}
        </main>
      </div>
    </div>
    <dialog ref={citationDialog} className="sw-source-dialog" onCancel={() => setOpenCitation(null)}><header><div><p className="sw-eyebrow">SOURCE EXCERPT</p><h2>{openCitation?.title}</h2><span>{openCitation?.location}</span></div><button type="button" aria-label="Close source excerpt" onClick={() => setOpenCitation(null)}>×</button></header><p>{openCitation?.excerpt || 'No excerpt is available for this source.'}</p><small>Extracted text from this location; this is not a full document preview.</small></dialog>
  </div>
}
