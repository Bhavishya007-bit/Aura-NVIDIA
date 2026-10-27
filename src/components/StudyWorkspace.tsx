import { Skeleton } from './ui'
import StudyToolV2 from './StudyToolV2'
import ProgressV2 from './ProgressV2'
import { renameMaterial,deleteMaterial } from '../services/studyV2Api'
import { savedGeneration, resumeGeneration } from '../services/generationJobs'
import type { SavedGeneration } from '../services/generationJobs'
import { artifact as decodeArtifact, report as decodeReport } from '../services/studyToolsApi'
import TutorReply from './TutorReply'
import StudyOverview from './StudyOverview'
import StudyRhythm from './StudyRhythm'
import EvaluationSummary from './EvaluationSummary'
import TeachingText from './TeachingText'
import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import type { Course } from '../types/study'
import type { AuthUser } from '../services/authApi'
import { askTutor } from '../services/studyApi'
import { ApiHttpError } from '../services/apiClient'
import { queueMaterials } from '../services/preparationApi'
import type { PreparationJob, UploadEntry } from '../services/preparationApi'
import PreparationStatus from './PreparationStatus'
import UploadBatchStatus from './UploadBatchStatus'
import LearningPanel from './LearningPanel'
import AgentPanel from './AgentPanel'
import AccountMenu from './AccountMenu'
import { fileType } from './studyPlanModel'
import TutorCheck from './TutorCheck'
import SourceViewer from './SourceViewer'
import { citedNumbers, groupToolCitations } from '../services/citationDisplay'
import { generateTool, getPracticeProgress, listArtifacts, listMaterials, setMaterialArchived, submitAssessment } from '../services/studyToolsApi'
import type { Artifact, LearningMode, Material, PracticeProgress, ToolCitation, ToolKind } from '../services/studyToolsApi'
import { readWorkspace, saveWorkspace } from '../services/workspaceStorage'
import './StudyWorkspace.css'
import MaterialPicker, { cleanSelection, MaterialChips, materialReady } from './MaterialPicker'
import GenerationStatus from './GenerationStatus'
import ChoiceSelect, { ItemCount } from './ChoiceSelect'
import { useGeneration } from '../hooks/useGeneration'
import { useGenerationSupport } from '../hooks/useGenerationSupport'
import type { GenerationTicket } from '../hooks/useGeneration'
import { multiMaterialNotice } from '../services/generationSupport'

type Tab = 'Overview' | 'Tutor' | 'Notes' | 'Summary' | 'Flashcards' | 'Assessment' | 'Progress' | 'Agents'
const tabs: Tab[] = ['Overview', 'Tutor', 'Notes', 'Summary', 'Flashcards', 'Assessment', 'Progress', 'Agents']
const mainTabs: Tab[] = ['Overview', 'Tutor', 'Assessment', 'Agents']
const extraTabs: Tab[] = ['Notes', 'Summary', 'Flashcards', 'Progress']
const iconPaths = ['M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z', 'M4 4h16v12H9l-5 4z', 'M5 5h14 M5 10h14 M5 15h14 M5 20h9', 'M5 4h14v16H5z M8 8h8 M8 12h8 M8 16h5', 'M7 3h14v15H7z M3 7v14h14', 'M4 12l5 5L20 6', 'M4 19V5 M4 19h16 M7 15l4-5 4 2 5-7']
function WorkspaceIcon({ path }: { path: string }) { return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={path} /></svg> }
const kinds: Partial<Record<Tab, ToolKind>> = { Notes: 'notes', Summary: 'summary', Flashcards: 'flashcards', Assessment: 'assessment' }
type ChatEntry = { stopped?: boolean; clarifyingQuestion?: string; followUpOptions?: string[]; role: 'user' | 'assistant'; text: string; grounded?: boolean; answerMode?: 'source' | 'source_plus_background' | 'general_background' | 'visual' | 'excerpt'; citations?: ToolCitation[] }
type Saved = { materialIds?: string[]; preparationIds?: string[]; preparationId?: string; sourceId?: string; tab?: Tab; selectedArtifact?: string; question?: string; chats?: Record<string, ChatEntry[]>; answers?: Record<string, Record<string, string>> }
type Props = { user: AuthUser; courses: Course[]; courseId: string; coursesLoading: boolean; coursesError: string; theme: 'light' | 'dark'; onCourseChange: (id: string) => void; onThemeChange: () => void; onChatHome: () => void; onSignOut: () => void; signingOut: boolean; sessionNotice: string }
const explainError = (error: unknown) => error instanceof Error ? error.message : 'Could not complete this request. Please retry.'
const studyGenerationError = (error: unknown) => error instanceof ApiHttpError && error.status === 503
  ? 'Aura could not create and verify this study material right now. Please try again. Your selected material and topic are kept.'
  : explainError(error)

function SourceButtons({ ids, citations, onOpen }: { ids: number[]; citations: ToolCitation[]; onOpen: (citation: ToolCitation) => void }) {
  return <div className="sw-citations">{groupToolCitations(ids, citations).map(citation => <button key={`${citation.source_id}:${citation.id}`} type="button" onClick={() => onOpen(citation)} title={citation.title}>[{citation.referenceIds?.join(', ') ?? citation.id}] {citation.title} · {citation.location}</button>)}</div>
}

export default function StudyWorkspace(props: Props) {
  const { user, courseId, theme } = props
  const storageKey = `aura.study.v1:${user.id}:${courseId}`
  const [pendingJob] = useState(() => savedGeneration(`${storageKey}:generation`))
  const [saved] = useState(() => readWorkspace<Saved>(storageKey, {}))
  const [link] = useState(() => new URLSearchParams(window.location.search))
  const [initialPlanGoal, setInitialPlanGoal] = useState(link.get('goal')?.slice(0, 2500))
  const [tab, setTab] = useState<Tab>(tabs.includes(link.get('tab') as Tab) ? link.get('tab') as Tab : saved.tab && tabs.includes(saved.tab) ? saved.tab : 'Overview')
  const [materialsCollapsed,setMaterialsCollapsed] = useState(()=>readWorkspace<{collapsed?:boolean}>(`${storageKey}:materials`,{}).collapsed??window.matchMedia('(max-width: 800px)').matches)
  const [moreTools, setMoreTools] = useState(() => extraTabs.includes(tab))
  const materialManager = useRef<HTMLDetailsElement>(null)
  const [selectedIds, setSelectedIds] = useState<string[]>(() => pendingJob?.course === courseId && Array.isArray(pendingJob.payload.material_ids) ? cleanSelection(pendingJob.payload.material_ids.map(String)) : link.get('materials') ? cleanSelection(link.get('materials')!.split(',')) : link.get('source') ? cleanSelection([link.get('source')]) : saved.materialIds ? cleanSelection(saved.materialIds) : cleanSelection([saved.sourceId]))
  const sourceId = selectedIds[0] ?? ''
  const chatKey = selectedIds.length > 1 ? [...selectedIds].sort().join(',') : sourceId
  function setSourceId(id: string) { setSelectedIds(id ? [id] : []) }
  const generation = useGeneration()
  const support = useGenerationSupport(courseId)
  const resumed = useRef(false)
  const currentTicket = useRef<GenerationTicket | null>(null)
  const [partial, setPartial] = useState<{ key: string; text: string; prompt: string } | null>(null)
  const partialRef = useRef<typeof partial>(null)
  function updatePartial(value: typeof partial) { partialRef.current = value; setPartial(value) }
  const selectionInitialized = useRef(Array.isArray(saved.materialIds))
  const [materials, setMaterials] = useState<Material[]>([])
  const [materialSearch, setMaterialSearch] = useState('')
  const [showArchived, setShowArchived] = useState(false)
  const [materialNotice, setMaterialNotice] = useState('')
  const [materialsLoading, setMaterialsLoading] = useState(true)
  const [artifacts, setArtifacts] = useState<Artifact[]>([])
  const [artifactsLoading, setArtifactsLoading] = useState(false)
  const [selectedArtifact, setSelectedArtifact] = useState(link.get('artifact') ?? saved.selectedArtifact ?? '')
  const [question, setQuestion] = useState(typeof saved.question === 'string' ? saved.question : '')
  const [chats, setChats] = useState<Record<string, ChatEntry[]>>(saved.chats && typeof saved.chats === 'object' && !Array.isArray(saved.chats) ? saved.chats : {})
  const [answers, setAnswers] = useState<Record<string, Record<string, string>>>(saved.answers && typeof saved.answers === 'object' && !Array.isArray(saved.answers) ? saved.answers : {})
  const [count, setCount] = useState(3)
  const [focus, setFocus] = useState(link.get('topic')?.slice(0, 180) ?? '')
  const materialSearchInput = useRef<HTMLInputElement>(null)
  const [difficulty, setDifficulty] = useState('beginner')
  const [learningMode, setLearningMode] = useState<LearningMode>('adaptive')
  const [questionType, setQuestionType] = useState('mcq')
  const [busy, setBusy] = useState('')
  const [uploadEntries, setUploadEntries] = useState<UploadEntry[]>([])
  const [preparationIds, setPreparationIds] = useState<string[]>(Array.isArray(saved.preparationIds) ? saved.preparationIds.filter(id => typeof id === 'string') : [])
  const uploadController = useRef<AbortController | null>(null)
  const [preparationRefresh, setPreparationRefresh] = useState(0)
  const [preparationId, setPreparationId] = useState(saved.preparationId ?? '')
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
  const busyRef = useRef(false)
  const mounted = useRef(true)
  const transcript = useRef<HTMLDivElement>(null)
  const activeMaterials = materials.filter(item => !item.archived)
  const archivedCount = materials.filter(item => item.archived).length
  const visibleMaterials = materials.filter(item => Boolean(item.archived) === showArchived && item.title.toLocaleLowerCase().includes(materialSearch.trim().toLocaleLowerCase()))
  const material = activeMaterials.find(item => item.id === sourceId)
  const sourceReady = selectedIds.length > 0 && selectedIds.every(id => activeMaterials.some(item => item.id === id && materialReady(item)))
  const imageGroup = selectedIds.length > 1 && selectedIds.every(id => /\.(png|jpe?g)$/i.test(materials.find(item => item.id === id)?.title ?? ''))
  const canUseGroup = selectedIds.length <= 1 || support.multi_study
  const canChatGroup = selectedIds.length <= 1 || imageGroup || support.multi_chat
  const kind = kinds[tab]
  const available = artifacts.filter(item => item.kind === kind && item.payload.learning?.mode !== 'conversation' && (selectedIds.length < 2 || item.payload.material_ids?.length === selectedIds.length && selectedIds.every(id => item.payload.material_ids!.includes(Number(id)))))
  const active = available.find(item => item.id === selectedArtifact) ?? available[0]
  const entries = Array.isArray(chats[chatKey]) ? chats[chatKey].filter(item => item && typeof item.text === 'string' && ['user', 'assistant'].includes(item.role)) : []
  const draftAnswers = active && answers[active.id] && typeof answers[active.id] === 'object' ? answers[active.id] : {}

  useEffect(() => { setUploadEntries([]); return () => uploadController.current?.abort() }, [courseId])
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  useEffect(() => {
    saveWorkspace(storageKey, { sourceId, materialIds: selectedIds, tab, selectedArtifact, question, chats, answers, preparationId, preparationIds })
  }, [storageKey, sourceId, selectedIds, tab, selectedArtifact, question, chats, answers, preparationId, preparationIds])
  useEffect(() => {
    let cancelled = false
    if (!courseId) { setMaterialsLoading(false); return }
    setMaterialsLoading(true); setMaterialsError('')
    listMaterials(courseId, support.study_v2).then(items => {
      if (cancelled) return
      setMaterials(items)
      const visible = items.filter(item => !item.archived)
      setSelectedIds(current => {
        const retained = current.filter(id => visible.some(item => item.id === id))
        if (retained.length || selectionInitialized.current) return retained
        selectionInitialized.current = true
        const home = readWorkspace<{ uploaded?: { sourceId?: string } }>(`aura.chat.v1:${user.id}:${courseId}`, {})
        const ready = visible.filter(item => item.status === 'success' || item.status === 'partial' || item.status === 'ready')
        const initial = visible.find(item => item.id === home.uploaded?.sourceId && materialReady(item))?.id ?? ready.at(-1)?.id
        return initial ? [initial] : []
      })
    }).catch(cause => { if (!cancelled) setMaterialsError(explainError(cause)) })
      .finally(() => { if (!cancelled) setMaterialsLoading(false) })
    return () => { cancelled = true }
  }, [courseId, user.id, reload, support.study_v2])
  useEffect(() => {
    if (materialsLoading) return
    const url = new URL(window.location.href)
    if (url.searchParams.get('view') !== 'study') return
    if (url.searchParams.get('source') && url.searchParams.get('source') !== sourceId) { url.searchParams.delete('topic'); setFocus('') }
    if (sourceId) url.searchParams.set('source', sourceId)
    else url.searchParams.delete('source')
    if (selectedIds.length > 1) url.searchParams.set('materials', selectedIds.join(','))
    else url.searchParams.delete('materials')
    window.history.replaceState(null, '', url)
  }, [sourceId, selectedIds, materialsLoading])
  useEffect(() => {
    let cancelled = false
    setArtifacts([]); setArtifactsError('')
    if (!courseId || !sourceId) { setArtifactsLoading(false); return }
    setArtifactsLoading(true)
    listArtifacts(courseId, sourceId, support.multi_study ? selectedIds : undefined).then(items => { if (!cancelled) setArtifacts(items) })
      .catch(cause => { if (!cancelled) setArtifactsError(explainError(cause)) })
      .finally(() => { if (!cancelled) setArtifactsLoading(false) })
    return () => { cancelled = true }
  }, [courseId, chatKey, reload, support.multi_study])
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
    if (tab === 'Tutor' && transcript.current) transcript.current.scrollTop = transcript.current.scrollHeight
  }, [chats, tab, busy])

  function selectTab(next: Tab) {
    setTab(next); if (extraTabs.includes(next)) setMoreTools(true); setError(''); setOpenCitation(null); setInitialPlanGoal(undefined)
    const url = new URL(window.location.href)
    url.searchParams.set('view', 'study'); url.searchParams.set('tab', next)
    url.searchParams.delete('goal'); url.searchParams.delete('topic'); url.searchParams.delete('artifact')
    if (sourceId) url.searchParams.set('source', sourceId)
    else url.searchParams.delete('source')
    window.history.replaceState(null, '', url)
  }
  useEffect(()=>saveWorkspace(`${storageKey}:materials`,{collapsed:materialsCollapsed}),[storageKey,materialsCollapsed])
  useEffect(()=>{const close=(event:KeyboardEvent)=>{if(event.key==='Escape'&&window.matchMedia('(max-width: 800px)').matches){setMaterialsCollapsed(true)}};window.addEventListener('keydown',close);return()=>window.removeEventListener('keydown',close)},[])
  function changeMaterial() { setMaterialsCollapsed(false); if (materialManager.current) materialManager.current.open = true; setShowArchived(false); setMaterialSearch(''); requestAnimationFrame(()=>{materialSearchInput.current?.scrollIntoView({ block: 'center' }); materialSearchInput.current?.focus()}) }
  function openPlanTool(next: 'Flashcards' | 'Assessment' | 'Summary', topic: string, source: string, artifactId?: string, materialIds?: string[]) {
    if (!activeMaterials.some(m => m.id === source)) { setError('The material for this plan is no longer active. Restore it from Materials to continue.'); return }
    selectTab(next); setSelectedIds(materialIds?.length ? materialIds : [source]); setFocus(topic); setSelectedArtifact(artifactId ?? ''); setLearningMode('manual'); if (artifactId) setReload(value => value + 1)
    const url = new URL(window.location.href)
    url.searchParams.set('source', source); url.searchParams.set('topic', topic)
    if (artifactId) url.searchParams.set('artifact', artifactId)
    window.history.replaceState(null, '', url)
  }
  function begin(label: string) { if (busyRef.current) return false; busyRef.current = true; setBusy(label); setError(''); return true }
  function end() { busyRef.current = false; if (mounted.current) setBusy('') }
  function beginGeneration(label: string) {
    if (!begin(label)) return null
    const ticket = generation.start()
    if (!ticket) { end(); return null }
    currentTicket.current = ticket
    resumed.current = true
    return ticket
  }
  function endGeneration(ticket: GenerationTicket) { generation.finish(ticket); if (currentTicket.current === ticket) end() }
  async function stopGeneration() {
    await generation.stop()
    if (currentTicket.current?.signal.aborted) { setBusy(''); busyRef.current = false; if (partial?.prompt) setQuestion(partial.prompt) }
  }
  function changeSelection(ids: string[]) { if (busyRef.current || generation.active) return; selectionInitialized.current = true; setSelectedIds(ids); setSelectedArtifact(''); setError(''); setFlipped({}); setFocus(''); updatePartial(null) }
  async function archiveMaterial(item: Material, archived: boolean) {
    if (!begin(archived ? 'Archiving material…' : 'Restoring material…')) return
    setMaterialNotice('')
    try {
      await setMaterialArchived(courseId, item.id, archived)
      if (!mounted.current) return
      setMaterials(current => current.map(material => material.id === item.id ? { ...material, archived } : material))
      if (archived && selectedIds.includes(item.id)) {
        setSelectedIds(current => current.filter(id => id !== item.id))
        setSelectedArtifact(''); setFlipped({}); setFocus(''); setOpenCitation(null)
      }
      if (!archived && !sourceId) setSourceId(item.id)
      setMaterialNotice(archived ? `${item.title} archived. Your saved work is kept.` : `${item.title} restored.`)
    } catch (cause) { if (mounted.current) setError(explainError(cause)) }
    finally { end() }
  }
  async function upload(files: File[]) {
    if (!files.length || !courseId || !begin('Uploading selected materials…')) return
    const controller = new AbortController()
    uploadController.current = controller
    try {
      const entries = await queueMaterials(courseId, files, setUploadEntries, (job, first) => {
        setPreparationIds(current => [...current, job.id])
        if (first) setPreparationId(job.id)
        setPreparationRefresh(value => value + 1)
      }, controller.signal)
      if (!controller.signal.aborted && mounted.current) {
        const count = entries.filter(entry => entry.state === 'queued').length
        setMaterialNotice(`${count} files queued. Each file has its own preparation status.`)
      }
    } catch (cause) { if (!controller.signal.aborted && mounted.current) setError(explainError(cause)) }
    finally { end(); uploadController.current = null; if (fileInput.current) fileInput.current.value = '' }
  }
  function preparationReady(job: PreparationJob) {
    if (String(job.course_id) !== courseId) return
    setPreparationIds(current => current.filter(id => id !== job.id))
    setReload(value => value + 1)
    if (job.id === preparationId && job.source_id) {
      setSourceId(String(job.source_id)); setTab('Tutor'); setPreparationId('')
      setMaterialNotice(`${job.filename} is ready.`)
    }
  }
  async function generate() {
    if (!kind || !sourceReady || !canUseGroup) return
    const ticket = beginGeneration('Creating and checking your study material…'); if (!ticket) return
    try {
      const generated = await generateTool(courseId, sourceId, kind, { count, focus, difficulty, questionType, learningMode: kind === 'assessment' ? learningMode : 'manual' }, { signal: ticket.signal, materialIds: selectedIds, enabled: support.study_jobs, course: courseId, storageKey: `${storageKey}:generation`, setCancel: generation.setCancel })
      if (ticket.current()) { setArtifacts(current => [generated, ...current]); setSelectedArtifact(generated.id); setFlipped({}) }
    } catch (cause) { if (ticket.current()) setError(studyGenerationError(cause)) }
    finally { endGeneration(ticket) }
  }
  async function startLearning(mode: LearningMode, topic = '') {
    if (!sourceReady || !canUseGroup) return
    const ticket = beginGeneration('Creating and checking your practice…'); if (!ticket) return
    try {
      const generated = await generateTool(courseId, sourceId, 'assessment', {
        count: mode === 'diagnostic' ? 5 : count, focus: topic,
        difficulty: 'beginner', questionType, learningMode: mode,
      }, { signal: ticket.signal, materialIds: selectedIds, enabled: support.study_jobs, course: courseId, storageKey: `${storageKey}:generation`, setCancel: generation.setCancel })
      if (ticket.current()) {
        setArtifacts(current => [generated, ...current]); setSelectedArtifact(generated.id)
        setLearningMode(mode); setFocus(topic); selectTab('Assessment')
      }
    } catch (cause) { if (ticket.current()) setError(studyGenerationError(cause)) }
    finally { endGeneration(ticket) }
  }
  async function send(resume?: SavedGeneration) {
    const text = String(resume?.payload.question ?? question).trim()
    if (!text || !sourceReady || !canChatGroup) return
    const ticket = beginGeneration('Aura is thinking…'); if (!ticket) return
    setQuestion('')
    updatePartial({ key: chatKey, text: '', prompt: text })
    if (!resume) setChats(current => ({ ...current, [chatKey]: [...entries, { role: 'user', text }] }))
    try {
      const response = await askTutor({ courseId, materialId: sourceId, materialIds: selectedIds, question: text,
        history: entries.filter(item => !item.stopped && item.text.trim()).slice(-8).map(item => ({ role: item.role, content: item.text.slice(0, 12000) })) }, { signal: ticket.signal, resume, enabled: support.study_jobs, course: courseId, storageKey: `${storageKey}:generation`, setCancel: generation.setCancel, combinedMaterials: !imageGroup && support.multi_chat,
        onText: value => { if (ticket.current()) updatePartial({ key: chatKey, text: value, prompt: text }) } })
      const citations: ToolCitation[] = response.citations.map((citation, index) => {
        const location = citation.location
        const label = location.kind === 'pdf_page' ? (/\.(png|jpe?g)$/i.test(material?.title ?? '') ? 'Image' : `Page ${location.page}`) : location.kind === 'slide' ? `Slide ${location.slide}` : `${Math.floor(location.seconds / 60)}:${String(Math.floor(location.seconds % 60)).padStart(2, '0')}`
        return { id: citation.citationNumber ?? index + 1, page: location.kind === 'pdf_page' ? location.page : null, slide: location.kind === 'slide' ? location.slide : null, seconds: location.kind === 'video_timestamp' ? location.seconds : null, chunk_id: 0, source_id: Number(citation.sourceId), title: citation.sourceName ?? materials.find(item => item.id === citation.sourceId)?.title ?? 'Material', location: label, excerpt: citation.excerpt ?? '' }
      })
      if (ticket.current()) { updatePartial(null); setChats(current => ({ ...current, [chatKey]: [...(current[chatKey] ?? []), { role: 'assistant', text: response.message.content, clarifyingQuestion: response.clarifyingQuestion, followUpOptions: response.followUpOptions, grounded: response.groundingStatus === 'grounded', answerMode: response.answerMode, citations }] })) }
    } catch (cause) { if (ticket.current()) { setError('Aura could not finish this answer. Your question and any received text are kept. Please retry.'); setQuestion(text) } else if (ticket.signal.aborted && mounted.current && currentTicket.current === ticket) setQuestion(text) }
    finally {
      if (mounted.current && currentTicket.current === ticket) {
        const captured = partialRef.current
        if (captured?.key === chatKey && captured.text) setChats(chats => ({ ...chats, [chatKey]: [...(chats[chatKey] ?? []), { role: 'assistant', text: captured.text, stopped: true }] }))
        updatePartial(null)
      }
      endGeneration(ticket)
    }
  }
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!active) return
    const ticket = beginGeneration('Checking your answers…'); if (!ticket) return
    try {
      const result = await submitAssessment(active.id, draftAnswers, ticket.signal, {enabled:support.study_jobs,course:courseId,storageKey:`${storageKey}:generation`,setCancel:generation.setCancel})
      if (ticket.current()) { setArtifacts(current => current.map(item => item.id === active.id ? { ...item, result } : item)); setProgressReload(value => value + 1) }
    } catch (cause) { if (ticket.current()) setError('Aura could not finish checking your answers. Your answers are kept; please retry.') }
    finally { endGeneration(ticket) }
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

  useEffect(() => {
    if (resumed.current || !support.study_jobs || materialsLoading || busyRef.current) return
    const pending = savedGeneration(`${storageKey}:generation`)
    if (!pending || pending.course !== courseId) return
    resumed.current = true
    if (pending.operation === 'chat') { void send(pending); return }
    const ticket = beginGeneration('Reopening your saved work…'); if (!ticket) return
    const options = { signal: ticket.signal, storageKey: `${storageKey}:generation`, setCancel: generation.setCancel,onPartial:(value:unknown)=>{if(pending.operation!=='generate'||!ticket.current())return;try{const partial=decodeArtifact(value);setArtifacts(current=>[partial,...current.filter(item=>item.id!==partial.id)]);setSelectedArtifact(partial.id)}catch{/* Keep waiting for checked content. */}} }
    const work = pending.operation === 'generate' ? resumeGeneration(pending, decodeArtifact, options).then(value => {
      if (ticket.current()) { setArtifacts(current => [value, ...current.filter(item => item.id !== value.id)]); setSelectedArtifact(value.id) }
    }) : resumeGeneration(pending, decodeReport, options).then(result => {
      if (ticket.current()) { setArtifacts(current => current.map(item => item.id === pending.payload.artifact_id ? {...item,result} : item)); setReload(value => value + 1); setProgressReload(value => value + 1) }
    })
    work.catch(() => { if (ticket.current()) setError('Aura could not reopen this work. Your earlier results are kept; please retry.') }).finally(() => endGeneration(ticket))
  }, [support.study_jobs, materialsLoading, storageKey, tab])

  function navigationItem(item: Tab) {
    return <button key={item} type="button" aria-current={tab === item ? 'page' : undefined} className={tab === item ? 'is-active' : ''} onClick={() => selectTab(item)}><span aria-hidden="true"><WorkspaceIcon path={iconPaths[tabs.indexOf(item)] ?? 'M4 12h16 M12 4v16'} /></span>{item === 'Agents' ? 'Study Plan' : item === 'Tutor' ? 'Tutor' : item}</button>
  }

  return <div className="aura-study" data-theme={theme} data-tab={tab} data-materials-collapsed={materialsCollapsed}>
    <aside className="sw-rail">
      <button className="sw-brand" onClick={props.onChatHome} disabled={!!busy} type="button"><span>A.</span>Aura</button>
      <p className="sw-rail-label">YOUR WORKSPACE</p>
      <nav aria-label="Study tools">{mainTabs.map(navigationItem)}<button type="button" className="sw-more-toggle" aria-expanded={moreTools} aria-controls="sw-extra-tools" onClick={() => setMoreTools(value => !value)}>More study tools <span aria-hidden="true">{moreTools ? '−' : '+'}</span></button><div id="sw-extra-tools" hidden={!moreTools}>{extraTabs.map(navigationItem)}</div></nav>
      <div className="sw-account"><AccountMenu demo={user.isDemo} name={user.fullName} courseId={courseId} onSignOut={props.onSignOut} signingOut={props.signingOut} disabled={!!busy} /></div>
    </aside>
    <div className="sw-shell">
      <header className="sw-topbar"><div><strong>Study workspace</strong><span className="sw-top-subtitle">Your materials and saved practice</span></div>
        <div className="sw-top-actions"><div className="sw-mobile-account"><AccountMenu demo={user.isDemo} name={user.fullName} courseId={courseId} onSignOut={props.onSignOut} signingOut={props.signingOut} disabled={!!busy} /></div><button type="button" onClick={props.onThemeChange} aria-label={theme === 'light' ? 'Use dark theme' : 'Use light theme'}><WorkspaceIcon path={theme === 'light' ? 'M20 15a8 8 0 01-11-11 8 8 0 1011 11z' : 'M12 3v2 M12 19v2 M3 12h2 M19 12h2 M5 5l2 2 M17 17l2 2 M5 19l2-2 M17 7l2-2 M16 12a4 4 0 11-8 0 4 4 0 018 0z'} /></button><button type="button" onClick={props.onChatHome} disabled={!!busy}>Chat home</button></div>
      </header>
      {(props.sessionNotice || props.coursesError) && <p className="sw-error" role="alert">{props.sessionNotice || props.coursesError}</p>}
      <div className="sw-body">
        <aside className="sw-materials" aria-label="Study materials" onKeyDown={event=>{if(event.key!=='Tab'||materialsCollapsed||!window.matchMedia('(max-width: 800px)').matches)return;const controls=Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled):not([hidden]),summary,a[href]')).filter(el=>el.getClientRects().length>0);const first=controls[0],last=controls[controls.length-1];if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus()}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus()}}}><button type="button" className="sw-material-toggle" aria-expanded={!materialsCollapsed} aria-label={materialsCollapsed?'Show materials':'Hide materials'} onClick={()=>setMaterialsCollapsed(v=>!v)}>{materialsCollapsed?`▤ ${selectedIds.length}`:'Hide materials ←'}</button><div className="sw-material-heading"><h2>Materials</h2><button type="button" aria-label="Refresh materials" disabled={!!busy || materialsLoading} onClick={() => setReload(value => value + 1)}>↻</button></div>
          <button type="button" className="sw-add" disabled={!!busy || !courseId} onClick={() => fileInput.current?.click()}>＋ Add material</button>
          <input ref={fileInput} type="file" multiple hidden accept=".pdf,.docx,.ppt,.pptx,.jpg,.jpeg,.png,audio/*,.mp4" onChange={event => void upload(Array.from(event.target.files ?? []))} />
          {materialsLoading && <Skeleton label="Loading materials" lines={3} />}
          {materialsError && <p className="sw-error" role="alert">{materialsError}</p>}
          <details className="sw-material-manage" ref={materialManager}><summary>Find &amp; manage materials</summary>
          <label className="sw-material-search"><span className="sw-sr-only">Search materials</span><input ref={materialSearchInput} type="search" placeholder="Search materials" value={materialSearch} onChange={event => setMaterialSearch(event.target.value)} /></label>
          <div className="sw-material-tabs"><button type="button" aria-pressed={!showArchived} onClick={() => setShowArchived(false)}>Active <span>{activeMaterials.length}</span></button><button type="button" aria-pressed={showArchived} onClick={() => setShowArchived(true)}>Archived <span>{archivedCount}</span></button></div>
          {!showArchived && !support.study_v2 && <div className="sw-archive-actions">{visibleMaterials.map(item => <button type="button" key={item.id} disabled={!!busy || generation.active} onClick={() => void archiveMaterial(item, true)} aria-label={`Archive ${item.title}`}>Archive {item.title}</button>)}</div>}
          </details>
          {!showArchived && <MaterialPicker materials={visibleMaterials} selected={selectedIds} onChange={changeSelection} storageKey={`aura.sets.v1:${user.id}:${courseId}`} disabled={!!busy || generation.active} loading={materialsLoading} onRename={support.study_v2?async(id,name)=>{const value=await renameMaterial(courseId,id,name);setMaterials(v=>v.map(m=>m.id===id?{...m,title:String(value.name)}:m));setReload(v=>v+1)}:undefined} onArchive={id=>{const item=materials.find(m=>m.id===id);if(item)void archiveMaterial(item,true)}} onDelete={support.study_v2?async(id)=>{await deleteMaterial(courseId,id);setMaterials(v=>v.filter(m=>m.id!==id));setSelectedIds(v=>v.filter(x=>x!==id))}:undefined} />}
          <div className="sw-material-list">{(showArchived ? visibleMaterials : []).map(item => <div key={item.id} className={`sw-material-row ${!showArchived && item.id === sourceId ? 'is-selected' : ''}`}>
            {showArchived ? <div className="sw-archived-title"><strong>{item.title}</strong><small>{fileType(item.title, item.type)}</small></div> : <button className="sw-material-select" type="button" disabled={!!busy || item.status === 'processing'} aria-current={item.id === sourceId ? 'true' : undefined} onClick={() => { setSourceId(item.id); setSelectedArtifact(''); setError(''); setFlipped({}); setFocus('') }}><span className="sw-file-icon"><WorkspaceIcon path="M6 3h8l4 4v14H6z M14 3v5h4 M9 12h6 M9 16h6" /></span><span><strong>{item.title}</strong><small>{fileType(item.title, item.type)}{item.status === 'processing' ? ' · Preparing' : ''}{['empty', 'error', 'not_configured'].includes(item.status) ? ' · Needs attention' : ''}</small></span></button>}
            <button className="sw-material-action" type="button" disabled={!!busy} aria-label={`${showArchived ? 'Restore' : 'Archive'} ${item.title}`} title={showArchived ? 'Restore to active materials' : 'Archive material; saved work is kept'} onClick={() => void archiveMaterial(item, !showArchived)}><WorkspaceIcon path={showArchived ? 'M5 9a8 8 0 111 9 M5 4v5h5' : 'M3 4h18v4H3z M5 8v12h14V8 M9 12h6'} /></button>
          </div>)}</div>
          {!materialsLoading && !visibleMaterials.length && !materialsError && <p className="sw-material-empty">{materialSearch ? 'No matching materials.' : showArchived ? 'No archived materials.' : 'Add a file or restore an archived material.'}</p>}
          {materialNotice && <p className="sw-material-notice" role="status">{materialNotice}</p>}
          <p className="sw-material-footnote">Choose up to 5 materials. Your selection stays with this study session.</p>
        </aside>
        <main className="sw-main">
          <div className="sw-heading"><div><p className="sw-eyebrow">{tab === 'Progress' ? 'All materials in this course' : 'YOUR STUDY WORKSPACE'}</p><h1>{tab === 'Agents' ? 'Study Plan' : tab === 'Tutor' ? 'Ask Aura' : tab === 'Overview' ? 'Your study space' : tab}</h1>{tab === 'Agents' && <p className="sw-plan-subtitle">Make time for what matters. Aura will help you get there.</p>}</div></div>
          <MaterialChips materials={materials} selected={selectedIds} onChange={changeSelection} disabled={!!busy || generation.active} onChangeOpen={changeMaterial} />
          {selectedIds.length > 1 && (tab === 'Tutor' ? !canChatGroup : tab !== 'Agents' && !canUseGroup) && <p className="sw-status" role="status">{multiMaterialNotice}</p>}
          {error && <p className="sw-error" role="alert">{error}</p>}
          <UploadBatchStatus simple={tab === 'Agents'} entries={uploadEntries} busy={!!busy} onRetry={() => void upload(uploadEntries.filter(entry => entry.state === 'failed').map(entry => entry.file))} />
          <PreparationStatus simple={tab === 'Agents'} pendingIds={preparationIds} courseId={courseId} refreshKey={preparationRefresh} pendingId={preparationId} onReady={preparationReady} onFailed={job => { setPreparationIds(current => current.filter(id => id !== job.id)); setReload(value => value + 1) }} />
          {busy && !generation.active && <div className="sw-status" role="status"><span className="sw-spinner" aria-hidden="true" />{busy}</div>}
          <GenerationStatus active={generation.active} cancelling={generation.state === 'cancelling'} stopped={generation.state === 'stopped' || generation.state === 'cancelled' ? generation.state : undefined} label={busy} slow={generation.slow} notice={generation.notice} onStop={() => void stopGeneration()} onKeepWaiting={generation.keepWaiting} />
          {tab === 'Agents' && <AgentPanel key={`${user.id}:${courseId}`} courseId={courseId} studyV2={support.study_v2} sourceId={sourceId} materialIds={selectedIds} multiMaterial={support.multi_agents} materialReady={sourceReady} storageKey={`aura.plan.v1:${user.id}:${courseId}`} initialGoal={initialPlanGoal} materialNames={Object.fromEntries(materials.map(item => [item.id, item.title]))} onOpenTool={openPlanTool} />}
          {tab === 'Overview' && <StudyOverview material={material} ready={sourceReady} busy={!!busy} canUpload={!!courseId} artifacts={artifacts} loading={artifactsLoading} error={artifactsError} onNavigate={selectTab} onUpload={() => fileInput.current?.click()} onOpenArtifact={artifact => { setSelectedArtifact(artifact.id); selectTab(artifact.kind === 'assessment' ? 'Assessment' : artifact.kind === 'notes' ? 'Notes' : artifact.kind === 'summary' ? 'Summary' : 'Flashcards') }} />}
          {tab === 'Tutor' && <><section className="sw-tutor"><div className="sw-transcript" ref={transcript} aria-live="polite">{!entries.length && <div className="sw-chat-empty"><span>✦</span><h2>What would you like to understand?</h2><p>Ask about {material?.title ?? 'a material you select'}.</p><div>{['What is this material about?', 'Explain the main ideas'].map(prompt => <button key={prompt} type="button" onClick={() => setQuestion(prompt)}>{prompt}</button>)}</div></div>}{entries.map((entry, index) => <article key={index} className={`sw-chat-entry ${entry.role}`}><strong>{entry.role === 'user' ? 'You' : '✦ Aura'}</strong>{entry.role === 'assistant' ? <TutorReply text={entry.text} clarification={entry.clarifyingQuestion} followUps={entry.followUpOptions} onFollowUp={value => { setQuestion(value); document.getElementById('sw-question')?.focus() }} /> : <><p>{entry.text}</p><button type="button" className="sw-link" disabled={!!busy} onClick={() => { setQuestion(entry.text); document.getElementById('sw-question')?.focus() }}>Edit &amp; resend</button></>}{entry.stopped && <span className="aura-stopped">■ Stopped</span>}{entry.role === 'assistant' && !entry.stopped && <><span className="sw-grounding">{entry.answerMode === 'visual' ? 'Visual interpretation — check against the image' : entry.answerMode === 'excerpt' ? 'Quoted source excerpts — explanation unavailable' : entry.answerMode === 'source_plus_background' ? 'Source-backed section + separately labelled background' : entry.answerMode === 'general_background' ? 'General background — outside your material' : (entry.answerMode === 'source' || entry.grounded) ? 'Source checked' : 'Contains unverified content — see answer label'}</span>{entry.citations?.length ? <SourceButtons ids={citedNumbers(entry.text)} citations={entry.citations} onOpen={setOpenCitation} /> : null}</>}</article>)}{partial?.key === chatKey && partial.text && <article className="sw-chat-entry assistant"><strong>✦ Aura</strong><TeachingText text={partial.text} /><span className="aura-stopped">{generation.active ? 'Writing…' : 'Stopped'}</span></article>}</div><form className="sw-composer" onSubmit={event => { event.preventDefault(); void send() }}><label className="sw-sr-only" htmlFor="sw-question">Ask Aura a question</label><textarea id="sw-question" rows={2} onKeyDown={event => {
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && event.nativeEvent.keyCode !== 229) {
                event.preventDefault()
                void send()
              }
            }} value={question} disabled={!sourceId || !!busy} onChange={event => setQuestion(event.target.value)} placeholder={sourceId ? 'Ask a question about this material…' : 'Select or add a material first'} />{generation.active ? <button className="sw-primary" type="button" aria-label="Stop generation" disabled={generation.state === 'cancelling'} onClick={() => void stopGeneration()}>■</button> : <button className="sw-primary" type="submit" disabled={!sourceReady || !canChatGroup || !question.trim() || !!busy}>Send ↑</button>}</form></section><TutorCheck key={`${courseId}:${chatKey}`} courseId={courseId} sourceId={sourceId} materialIds={selectedIds} disabled={!!busy || !sourceReady || !canUseGroup} onUpdated={() => { setProgressReload(value => value + 1); setReload(value => value + 1) }} onOpen={setOpenCitation} /></>}
          {support.study_v2 && kind && kind !== 'summary' && available.length>0 && <div className="sw-output-toolbar"><div className="aura-field"><span>Saved version</span><ChoiceSelect label="Saved version" value={active?.id??''} disabled={!!busy} onChange={setSelectedArtifact} options={available.map(a=>({value:a.id,label:`${new Date(a.created_at).toLocaleString()}${a.payload.focus?` · ${a.payload.focus}`:''}`}))}/></div></div>}
          {support.study_v2 && kind && kind !== 'summary' && <StudyToolV2 key={`${kind}:${chatKey}`} courseId={courseId} materialIds={selectedIds} kind={kind} ready={sourceReady} active={active} storageKey={storageKey} focus={focus} onArtifact={value=>{setArtifacts(v=>[value,...v.filter(a=>a.id!==value.id)]);setSelectedArtifact(value.id)}} onOpen={setOpenCitation} onUpdated={()=>setProgressReload(v=>v+1)} onBusyChange={active=>{busyRef.current=active;setBusy(active?'Creating your study material…':'');if(active)resumed.current=false}}/>}
          {kind && (!support.study_v2 || kind === 'summary' || kind === 'assessment' && active && active.payload.generation_version !== 2) && <>
            <form className="sw-generation" hidden={support.study_v2 && kind !== 'summary'} onSubmit={event => { event.preventDefault(); void generate() }}><label className="sw-focus">Focus <span>(optional)</span><input value={focus} maxLength={180} onChange={event => setFocus(event.target.value)} placeholder="e.g. cytoskeleton functions" disabled={!!busy} /></label>{kind !== 'summary' && <ItemCount value={count} onChange={setCount} disabled={!!busy} label={kind === 'assessment' ? 'Questions' : 'Items'} />}{kind === 'assessment' && <><div className="aura-field"><span>Format</span><ChoiceSelect label="Question format" value={questionType} disabled={!!busy} onChange={setQuestionType} options={[{value:'mcq',label:'Multiple choice'},{value:'short_answer',label:'Short answer'},{value:'numerical',label:'Numerical (with units)'}]} /></div><div className="aura-field"><span>Practice mode</span><ChoiceSelect label="Practice mode" value={learningMode} disabled={!!busy} onChange={value => setLearningMode(value as LearningMode)} options={[{value:'adaptive',label:'Adapt to my understanding'},{value:'diagnostic',label:'Starting-point diagnostic'},{value:'manual',label:'Choose difficulty myself'}]} /></div>{learningMode === 'manual' && <div className="aura-field"><span>Difficulty</span><ChoiceSelect label="Difficulty" value={difficulty} disabled={!!busy} onChange={setDifficulty} options={['beginner','intermediate','advanced'].map(value => ({value,label:value[0].toUpperCase()+value.slice(1)}))} /></div>}</>}<button className="sw-primary" disabled={!sourceReady || !canUseGroup || !!busy || artifactsLoading || !!artifactsError} type="submit">{active ? 'Generate new' : 'Generate'}</button></form>
            {artifactsError && <p className="sw-error" role="alert">{artifactsError} <button type="button" onClick={() => setReload(value => value + 1)}>Retry</button></p>}
            {artifactsLoading ? <p className="sw-muted" role="status">Loading saved work…</p> : !active ? <div className="sw-empty"><span>{tab === 'Assessment' ? '✓' : '▤'}</span><h2>{sourceId ? `Create your first ${tab.toLowerCase()}` : 'Choose a material first'}</h2><p>{sourceId ? 'Aura will generate content from selected passages and check its sources before saving.' : 'Select a file from the materials list or upload one.'}</p></div> : <>
              <div className="sw-output-toolbar" hidden={support.study_v2}><div className="aura-field"><span>Saved version</span><ChoiceSelect label="Saved version" value={active.id} disabled={!!busy} onChange={value => { setSelectedArtifact(value); setFlipped({}) }} options={available.map(item => ({value:item.id,label:`${new Date(item.created_at).toLocaleString()}${item.payload.focus ? ` · ${item.payload.focus}` : ''}`}))} /></div>{kind !== 'assessment' && <button type="button" onClick={exportTool}>Export text ↓</button>}</div>
              {kind === 'assessment' && active.payload.learning && <p className="sw-status" role="status">{active.payload.learning.mode === 'diagnostic' ? 'Diagnostic' : active.payload.learning.mode === 'adaptive' ? 'Adaptive practice' : 'Practice'}: {active.payload.learning.reason}{active.payload.learning.difficulty ? ` Suggested difficulty: ${active.payload.learning.difficulty}.` : ''}</p>}
              <p className="sw-coverage">Based on your selected material. Check the linked slides as you study.</p>
              {active.payload.notice && <p className="sw-status" role="status">{active.payload.notice}</p>}
              {(kind === 'notes' || kind === 'summary') && <div className="sw-reading">{active.payload.items.map(item => <article key={item.id}><h2>{item.title}</h2><TeachingText text={item.text ?? ''} /><SourceButtons ids={item.citation_ids} citations={active.payload.citations} onOpen={setOpenCitation} /></article>)}</div>}
              {kind === 'flashcards' && <div className="sw-flashcards">{active.payload.items.map((item, index) => <article key={item.id}><span className="sw-eyebrow">CARD {index + 1} OF {active.payload.items.length}</span><h2>{item.question}</h2><button className="sw-reveal" type="button" aria-expanded={!!flipped[item.id]} onClick={() => setFlipped(current => ({ ...current, [item.id]: !current[item.id] }))}>{flipped[item.id] ? 'Hide answer' : 'Reveal answer'}</button>{flipped[item.id] && <div className="sw-card-answer"><TeachingText text={item.answer ?? ''} /><SourceButtons ids={item.citation_ids} citations={active.payload.citations} onOpen={setOpenCitation} /></div>}</article>)}</div>}
              {kind === 'assessment' && (!active.result ? <form className="sw-assessment" onSubmit={event => void submit(event)}>{active.payload.items.map((item, index) => <fieldset key={item.id} disabled={!!busy}><legend><small>QUESTION {index + 1} · {item.difficulty} · {item.topic}</small>{item.prompt}</legend>{item.kind === 'mcq' ? item.choices?.map(choice => <label key={choice.id} className={draftAnswers[item.id] === choice.id ? 'is-chosen' : ''}><input type="radio" name={item.id} value={choice.id} required checked={draftAnswers[item.id] === choice.id} onChange={() => setAnswers(current => ({ ...current, [active.id]: { ...draftAnswers, [item.id]: choice.id } }))} /><span>{choice.id}</span>{choice.text}</label>) : <textarea aria-label={`Answer question ${index + 1}`} required rows={3} placeholder={item.kind === 'numerical' ? 'Enter a number and unit, e.g. 12 cm/s' : 'Explain your answer'} maxLength={3000} value={draftAnswers[item.id] ?? ''} onChange={event => setAnswers(current => ({ ...current, [active.id]: { ...draftAnswers, [item.id]: event.target.value } }))} />}<SourceButtons ids={item.citation_ids} citations={active.payload.citations} onOpen={setOpenCitation} /></fieldset>)}<button className="sw-primary" type="submit" disabled={!!busy || active.payload.items.some(item => !draftAnswers[item.id]?.trim())}>Submit assessment</button></form> : <section className="sw-report"><div className="sw-report-heading"><div><span className="sw-eyebrow">ASSESSMENT COMPLETE</span><h2>{active.result.correct_count} of {active.result.question_count} correct</h2></div><strong>{active.result.score}%</strong></div><p>{active.result.recommended_action}</p>{Boolean(active.result.mastery_updates?.length) && <p className="sw-status">Your topic mastery estimates were updated. <button type="button" onClick={() => selectTab('Progress')}>View understanding and next practice →</button></p>}{active.result.feedback.map((item, index) => <article key={item.question_id}><small className={item.correct ? 'sw-correct' : 'sw-incorrect'}>{item.correct ? 'Correct' : 'Review this'} · QUESTION {index + 1}</small><h3>{item.prompt}</h3><p><strong>Your answer:</strong> {item.submitted_answer}</p><p><strong>Expected answer:</strong> {item.expected_answer}</p><TeachingText text={item.explanation} />{item.numerical_feedback && <p>{item.numerical_feedback.hint}</p>}{item.misconception && <aside className="sw-status"><strong>Possible misconception: {item.misconception.category.replaceAll('_', ' ')}</strong><p>{item.misconception.hint}</p>{item.misconception.student_quote && <p>Your response: “{item.misconception.student_quote}”</p>}{item.misconception.source_quote && <p>Source evidence: “{item.misconception.source_quote}”</p>}<small>This is a feedback hypothesis from this answer, not a confirmed diagnosis.</small></aside>}<SourceButtons ids={item.citation_ids} citations={active.payload.citations} onOpen={setOpenCitation} /><button type="button" className="sw-link" onClick={() => { setFocus(item.topic); selectTab('Flashcards') }}>Review {item.topic} →</button></article>)}</section>)}
            </>}
          </>}
          {tab === 'Progress' && support.study_v2 && <ProgressV2 courseId={courseId} onPractice={(tool,topic)=>{selectTab(tool);setFocus(topic)}}/>}
          {tab === 'Progress' && !support.study_v2 && <section className="sw-progress"><LearningPanel courseId={courseId} sourceId={sourceId} refreshKey={progressReload} disabled={!!busy || !sourceReady || !canUseGroup} onPractice={(mode, topic) => void startLearning(mode, topic)} />{progressError ? <p className="sw-error" role="alert">{progressError} <button type="button" onClick={() => setProgressReload(value => value + 1)}>Retry</button></p> : !progress ? <p role="status">Loading progress…</p> : <ProgressDashboard progress={progress} onPractice={() => selectTab('Assessment')} />}{weakTopics.length > 0 && <details className="sw-disclosure"><summary>Suggested review</summary><p className="sw-muted">Based on your completed practice.</p>{weakTopics.slice(0, 3).map(item => <button className="sw-review" key={item.topic} type="button" onClick={() => { setFocus(item.topic); selectTab('Flashcards') }}>{item.topic}<span>Create review cards →</span></button>)}</details>}<details className="sw-disclosure"><summary>Daily study rhythm &amp; reminders</summary><StudyRhythm courseId={courseId} onPractice={(topic, source) => openPlanTool('Assessment', topic, source)} /></details><EvaluationSummary courseId={courseId} /></section>}
        </main>
      </div>
    </div>
    <SourceViewer citation={openCitation} onClose={() => setOpenCitation(null)} />
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

