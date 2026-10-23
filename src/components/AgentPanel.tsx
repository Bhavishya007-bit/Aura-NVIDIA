import StudyRhythm from './StudyRhythm'
import TeachingText from './TeachingText'
import { useEffect, useRef, useState } from 'react'
import { cancelAgent, deleteMemory, getAgentCapabilities, getAgentRuns, getMemories, getTasks, saveMemory, startAgent, updateTask } from '../services/agentApi'
import type { AgentRun, CodeInput, MemoryItem, MemoryState, Task } from '../services/agentApi'
import { readWorkspace, saveWorkspace } from '../services/workspaceStorage'
import { displayGoal, goalWithOptions, isActive, planContent, savedAssessment, slideReferences, stateLabel, stepLabel, taskForDay } from './studyPlanModel'
import type { PlanOptions } from './studyPlanModel'
import MemoryDialog from './MemoryDialog'
import ResearchResult from './ResearchResult'
import CodeResult, { savedCodeOutput, codeFailureMessage } from './CodeResult'
import './AgentPanel.css'

type Props = { courseId: string; sourceId: string; materialReady: boolean; storageKey: string; initialGoal?: string; materialNames?: Record<string, string>; onOpenTool: (tool: 'Flashcards' | 'Assessment' | 'Summary', topic: string, sourceId: string, artifactId?: string) => void }
type Draft = { goal?: string; skill?: string; options?: PlanOptions; hidden?: string[]; selected?: string; runOptions?: Record<string, PlanOptions> }
const examples = [
  { label: '3-day plan', goal: 'Create a 3-day study plan from my material, with a review task for each day.' },
  { label: 'Exam tomorrow, focus on weak topics', goal: 'My exam is tomorrow. Create a 1-day revision plan. Prioritize topics I have struggled with if my saved progress is available; otherwise help me identify them.' },
  { label: 'Explain only the hard parts', goal: 'Create a study plan focused on the most challenging ideas in this material. Explain the hard parts with examples.' },
]
const researchExamples = [
  { label: 'Explore a key concept', goal: 'Research a major concept in this material. Separate what the material says from additional web findings.' },
  { label: 'Compare explanations', goal: 'Compare how my material and public sources explain the central topic. Cite sources and state any disagreements.' },
  { label: 'Find a real-world example', goal: 'Research a real-world example related to the main topic in my material. Explain the connection and cite the sources.' },
]
const quizExamples = [
  { label: 'Check the fundamentals', goal: 'Create a quiz on the main concepts in this material.' },
  { label: 'Test the hard parts', goal: 'Create a quiz on conceptually challenging topics in this material. Use only facts supported by the slides.' },
  { label: 'Practice applying concepts', goal: 'Create a quiz that tests relationships and comparisons explained in this material.' },
]
const codeExamples = [
  { label: 'Analyze my CSV', goal: 'Analyze my attached CSV. Summarize numeric columns, check missing values and save a results.csv with the findings.' },
  { label: 'Compare algorithms', goal: 'Write and run Python comparing linear search and binary search on a small sorted list. Explain the results and limitations.' },
  { label: 'Calculate and explain', goal: 'Write and run a Python simulation of 1000 coin flips with a fixed seed. Report the head proportion and explain sampling variation. Save results.json.' },
]
const defaults: PlanOptions = { days: '', minutes: '', depth: 'standard' }
const dateLabel = (value?: string) => value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : 'Time unavailable'
function duration(run: AgentRun) {
  if (!run.started_at || !run.updated_at) return 'Not reported'
  const seconds = Math.max(0, Math.round((Date.parse(run.updated_at) - Date.parse(run.started_at)) / 1000))
  return Number.isFinite(seconds) ? `${Math.floor(seconds / 60)}m ${seconds % 60}s${isActive(run) ? ' at last update' : ''}` : 'Not reported'
}
function RichText({ text }: { text: string }) { return <TeachingText text={text} /> }

export default function AgentPanel({ courseId, sourceId, materialReady, storageKey, initialGoal, materialNames = {}, onOpenTool }: Props) {
  const [saved] = useState(() => readWorkspace<Draft>(storageKey, {}))
  const [pane, setPane] = useState<'Plan' | 'Today'>('Plan')
  const [goal, setGoal] = useState(initialGoal ?? saved.goal ?? '')
  const [skill, setSkill] = useState(!initialGoal && ['research_brief', 'assessment', 'code_analysis'].includes(saved.skill ?? '') ? saved.skill! : 'study_plan')
  const [codeEnabled, setCodeEnabled] = useState(false)
  const [codeInputs, setCodeInputs] = useState<CodeInput[]>([])
  const [inputError, setInputError] = useState('')
  const [readingFiles, setReadingFiles] = useState(false)
  const fileReadVersion = useRef(0)
  const [quizCount, setQuizCount] = useState(3)
  const [quizDifficulty, setQuizDifficulty] = useState('beginner')
  const [assessmentEnabled, setAssessmentEnabled] = useState(false)
  const [options, setOptions] = useState<PlanOptions>(() => ({ ...defaults, ...saved.options }))
  const [runOptions, setRunOptions] = useState<Record<string, PlanOptions>>(saved.runOptions ?? {})
  const [allowMemory, setAllowMemory] = useState(false)
  const [memoryOpen, setMemoryOpen] = useState(false)
  const [webEnabled, setWebEnabled] = useState<boolean | null>(null)
  const [memory, setMemory] = useState<MemoryState>({ enabled: false, items: [] })
  const [runs, setRuns] = useState<AgentRun[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [selected, setSelected] = useState(initialGoal ? '__new__' : saved.selected ?? '')
  const [hidden, setHidden] = useState<string[]>(Array.isArray(saved.hidden) ? saved.hidden : [])
  const [removed, setRemoved] = useState<string>()
  const [loaded, setLoaded] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [refresh, setRefresh] = useState(0)
  const [memoryNote, setMemoryNote] = useState<{ item: MemoryItem; before?: MemoryItem }>()
  const seenWrites = useRef(new Set<string>())
  const previousMemory = useRef(new Map<string, MemoryItem>())
  const firstLoad = useRef(true)
  const actionLock = useRef(false)
  const goalInput = useRef<HTMLTextAreaElement>(null)
  const manageMemoryButton = useRef<HTMLButtonElement>(null)
  const resultHeading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { saveWorkspace(storageKey, { goal, skill, options, hidden, selected, runOptions }) }, [storageKey, goal, skill, options, hidden, selected, runOptions])
  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    async function load() {
      // Independent resources remain usable if one fails. Polling also recovers after a connection drop.
      const results = await Promise.allSettled([getAgentRuns(courseId), getTasks(courseId), getMemories(courseId), getAgentCapabilities()])
      if (cancelled) return
      const [jobs, todo, mem, capabilities] = results
      if (capabilities.status === 'fulfilled') { setWebEnabled(capabilities.value.web_search); setAssessmentEnabled(capabilities.value.assessment_agent); setCodeEnabled(capabilities.value.code_execution) }
      let keepPolling = results.some(r => r.status === 'rejected')
      if (jobs.status === 'fulfilled') {
        setRuns(jobs.value); setLoaded(true)
        keepPolling ||= jobs.value.some(isActive)
        for (const run of jobs.value) for (const [index, step] of run.steps.entries()) {
          if (step.tool !== 'memory_write' || step.state !== 'completed') continue
          const key = `${run.id}:${index}`
          if (seenWrites.current.has(key)) continue
          seenWrites.current.add(key)
          if (!firstLoad.current && step.observation && typeof step.observation === 'object') {
            const item = step.observation as MemoryItem
            if (typeof item.id === 'string' && typeof item.record?.text === 'string') setMemoryNote({ item, before: previousMemory.current.get(item.id) })
          }
        }
        firstLoad.current = false
      }
      if (todo.status === 'fulfilled') setTasks(todo.value)
      if (mem.status === 'fulfilled') { setMemory(mem.value); previousMemory.current = new Map(mem.value.items.map(item => [item.id, item])) }
      if (results.some(r => r.status === 'rejected')) setError('Some saved work could not be refreshed. Your run can continue in the background.')
      else setError('')
      if (keepPolling) timer = setTimeout(() => void load(), 3000)
    }
    if (courseId) void load()
    return () => { cancelled = true; if (timer) clearTimeout(timer) }
  }, [courseId, refresh])
  async function act(work: () => Promise<unknown>) {
    if (actionLock.current) return
    actionLock.current = true; setBusy(true); setError('')
    try { await work(); setRefresh(v => v + 1) }
    catch { setError('Could not complete that action. Please try again.') }
    finally { actionLock.current = false; setBusy(false) }
  }
  const visible = runs.filter(r => !hidden.includes(r.id) || isActive(r))
  const active = runs.find(isActive)
  const run = selected === '__new__' ? active : visible.find(r => r.id === selected) ?? active ?? visible[0]
  const content = run ? planContent(run) : null
  const working = isActive(run)
  const assessment = run ? savedAssessment(run) : undefined
  const codeOutput = run?.request.skill === 'code_analysis' ? savedCodeOutput(run) : undefined
  const hasContent = Boolean(content?.markdown.trim()) || !!assessment || !!codeOutput
  const goalExamples = skill === 'code_analysis' ? codeExamples : skill === 'assessment' ? quizExamples : skill === 'research_brief' ? researchExamples : examples
  const early = !!run && ['budget_exhausted', 'timed_out', 'interrupted'].includes(run.state)
  const activeCount = runs.filter(isActive).length
  const canUseMaterial = skill === 'code_analysis' || (!!sourceId && materialReady)
  const canStart = (skill !== 'assessment' || assessmentEnabled) && (skill !== 'code_analysis' || codeEnabled) && canUseMaterial && loaded && !!courseId && !!goal.trim() && !busy && (skill !== 'code_analysis' || (!readingFiles && !inputError)) && activeCount < 2
  const canRegenerate = !busy && activeCount < 2 && (run?.request.skill === 'code_analysis' ? codeEnabled : !!sourceId && materialReady)
  const finishedSteps = run?.steps.filter(s => s.state === 'completed') ?? []
  const currentStep = run?.steps.find(s => ['running', 'started', 'pending'].includes(s.state))
  const announcement = run ? working ? `${finishedSteps.length} steps complete. ${currentStep?.tool === 'verification' && run.request.skill === 'assessment' ? 'Checking your questions' : stepLabel(currentStep?.tool ?? '')}.` : stateLabel(run.state) : ''
  const completedTasks = tasks.filter(t => t.done).length
  const progressLabel = (tool: string) => tool === 'verification' && run?.request.skill === 'assessment' ? 'Checking your questions' : stepLabel(tool)
  const webAttempts = run?.steps.filter(step => step.tool === 'web_search') ?? []
  const reportedCredits = webAttempts.map(step => {
    const data = step.observation as { credits?: unknown } | undefined
    return typeof data?.credits === 'number' && Number.isFinite(data.credits) && data.credits >= 0 ? data.credits : null
  })
  const knownCredits = reportedCredits.reduce<number>((sum, n) => sum + (n ?? 0), 0)

  async function create(inputGoal = goal, simple = false, source = sourceId, nextSkill = skill, chosenOptions = options, inputs = codeInputs) {
    if ((nextSkill !== 'code_analysis' && (!source || !materialReady)) || !inputGoal.trim()) return
    await act(async () => {
      const selectedOptions: PlanOptions = simple ? { days: '1', minutes: '20', depth: 'quick' } : chosenOptions
      const latestMemory = nextSkill === 'code_analysis' ? memory : await getMemories(courseId)
      setMemory(latestMemory); previousMemory.current = new Map(latestMemory.items.map(item => [item.id, item]))
      const adjustedGoal = nextSkill === 'assessment' ? inputGoal.replace(/\b(?:\d{1,3}|one|two|three|four|five)\s*[-–]?\s*(?:multiple-choice\s+|mcq\s+)?questions?\b/gi, `${simple ? 1 : quizCount} questions`) : inputGoal
      let requestGoal = goalWithOptions(adjustedGoal, nextSkill !== 'study_plan' ? { ...selectedOptions, days: '', minutes: '' } : selectedOptions) + (allowMemory && latestMemory.enabled ? '\nRemember learning preferences I explicitly state in this goal.' : '')
      if (nextSkill === 'assessment') requestGoal += `\nCreate exactly ${simple ? 1 : quizCount} multiple-choice questions. Difficulty: ${simple ? 'beginner' : quizDifficulty}.`
      if (nextSkill === 'code_analysis') requestGoal = inputGoal + (simple ? '\nUse one small calculation, print the essential result and skip output files.' : '')
      const value = await startAgent(courseId, source && materialReady ? source : '', requestGoal, nextSkill, nextSkill !== 'code_analysis' && allowMemory && latestMemory.enabled, inputs)
      setSelected(String(value.id)); setPane('Plan'); setRunOptions(current => ({ ...current, [String(value.id)]: selectedOptions }))
    })
  }
  function regenerate(simple = false) {
    if (!run) return
    const original = displayGoal(run.request.goal)
    setGoal(original); setSkill(run.request.skill); setOptions(simple ? { days: '1', minutes: '20', depth: 'quick' } : runOptions[run.id] ?? defaults)
    // Regeneration always uses the selected header material; never silently switches files.
    void create(original, simple, sourceId, run.request.skill, runOptions[run.id] ?? defaults, run.request.inputs ?? [])
  }
  async function attachCSVs(files: File[]) {
    const version = ++fileReadVersion.current
    setReadingFiles(true); setInputError('')
    try {
      if (files.length > 2) throw new Error('Choose up to two CSV files.')
      const inputs: CodeInput[] = []
      for (const file of files) {
        if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,74}\.csv$/.test(file.name) || file.size > 16384 || !file.size) throw new Error('Use a .csv filename with letters, numbers, dots, hyphens or underscores, up to 16 KiB per file.')
        const text = new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer())
        if (!text || text.includes('\0') || inputs.some(item => item.name.toLowerCase() === file.name.toLowerCase())) throw new Error('Use distinct, non-empty UTF-8 CSV files.')
        inputs.push({ name: file.name, text })
      }
      if (version === fileReadVersion.current) setCodeInputs(inputs)
    } catch (error) {
      if (version === fileReadVersion.current) { setCodeInputs([]); setInputError(error instanceof Error ? error.message : 'Could not read these CSV files.') }
    } finally { if (version === fileReadVersion.current) setReadingFiles(false) }
  }
  function download() {
    if (!content) return
    const researchSources = run?.result?.sources?.map(source => source.kind === 'web' ? `- [${source.reference}] ${source.title}: ${source.url}` : `- [${source.reference}] ${source.title}${source.slide ? ', Slide ' + source.slide : source.page ? ', Page ' + source.page : ''}`) ?? []
    const citations = run ? content.days.flatMap(d => slideReferences(run, d.references).map(r => `- Day ${d.day}: Slide ${r.slide}`)) : []
    const blob = new Blob([`# Aura ${run?.request.skill === 'research_brief' ? 'research' : 'study plan'}\n\n${content.markdown}\n\n${citations.length ? '## Source slides\n' + [...new Set(citations)].join('\n') : ''}${researchSources.length ? '\n\n## Sources\n' + researchSources.join('\n') : ''}`], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob), link = document.createElement('a')
    link.href = url; link.download = run?.request.skill === 'research_brief' ? 'aura-research.md' : 'aura-study-plan.md'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  function useExample(example: typeof examples[number]) { setGoal(example.goal); setOptions(v => ({ ...v, days: '' })); setPane('Plan'); goalInput.current?.focus() }
  function renderTask(task: Task) {
    return <label className={`plan-task ${task.done ? 'is-done' : ''}`} key={task.id}><input type="checkbox" checked={task.done} disabled={busy} onChange={e => void act(() => updateTask(courseId, task.id, e.target.checked))} /><span><strong>{task.title}</strong>{task.details && <span>{task.details}</span>}</span></label>
  }
  return <section className="study-plan" aria-label="Study plan workspace">
    <nav className="plan-tabs" aria-label="Plan views">{(['Plan', 'Today'] as const).map(p => <button key={p} type="button" aria-pressed={pane === p} onClick={() => setPane(p)}>{p}{p === 'Today' && tasks.some(t => !t.done) && <span>{tasks.filter(t => !t.done).length}</span>}</button>)}</nav>
    {error && <div className="plan-notice plan-notice--warning" role="alert">{error} <button type="button" disabled={busy} onClick={() => setRefresh(v => v + 1)}>Retry</button></div>}
    {memoryNote && <div className="plan-notice" role="status">Noted: {memoryNote.item.record.text}<button type="button" disabled={busy} onClick={() => void act(async () => { if (memoryNote.before) await saveMemory(courseId, memoryNote.before.record, memoryNote.before.id); else await deleteMemory(courseId, memoryNote.item.id); setMemoryNote(undefined) })}>Undo</button><button type="button" aria-label="Dismiss memory notice" onClick={() => setMemoryNote(undefined)}>✕</button></div>}
    <div className="plan-sr-only" aria-live="polite" aria-atomic="true">{announcement}</div>
    {!loaded && !error && <p className="plan-loading" role="status">Opening your saved plans…</p>}
    {pane === 'Today' ? <section className="plan-today"><StudyRhythm courseId={courseId} onPractice={(topic, source) => onOpenTool('Assessment', topic, source)} /><div className="plan-section-heading"><div><span className="plan-kicker">ONE STEP AT A TIME</span><h2>What will you learn today?</h2><p>Your workspace checklist. Pick up where you left off.</p></div>{tasks.length > 0 && <span className="plan-status">{completedTasks} / {tasks.length} done</span>}</div>{loaded && !tasks.length ? <div className="plan-empty"><span aria-hidden="true">✓</span><h3>A clear next step starts with a plan</h3><p>Create a study plan and your saved tasks will appear here.</p><button type="button" onClick={() => { setPane('Plan'); goalInput.current?.focus() }}>Create a plan</button></div> : <div className="plan-checklist">{tasks.map(renderTask)}</div>}<p className="plan-caption">Checkmarks save automatically. Tasks are not assigned to a calendar date yet.</p></section> : <>
      <form className="plan-compose" onSubmit={e => { e.preventDefault(); if (canStart) void create() }}>
        <div className="plan-section-heading"><div><span className="plan-kicker">A LITTLE STRUCTURE. A LOT MORE CLARITY.</span><h2>What do you want to achieve?</h2><p>Turn your material into a next step you can follow.</p></div><span className="plan-spark" aria-hidden="true">✦</span></div>
        <fieldset className="plan-outcomes"><legend className="plan-sr-only">Choose an outcome</legend>{[{ value: 'study_plan', title: 'Study plan', text: 'A daily path through your material.', icon: '▤' }, { value: 'research_brief', title: 'Research a topic', text: webEnabled ? 'Explore your material with web sources.' : 'Explore an idea in your uploaded material.', icon: '⌕' }, { value: 'assessment', title: 'Quiz me', text: 'Check your understanding with a saved quiz.', icon: '✓' }, { value: 'code_analysis', title: 'Code & data', text: codeEnabled ? 'Run Python and explore a small CSV.' : 'Execution needs to be enabled in setup.', icon: '⌘' }].map(item => <label key={item.value} className={skill === item.value ? 'is-selected' : ''}><input type="radio" name="plan-outcome" value={item.value} disabled={(item.value === 'assessment' && !assessmentEnabled) || (item.value === 'code_analysis' && !codeEnabled)} checked={skill === item.value} onChange={() => setSkill(item.value)} /><span className="plan-outcome-icon" aria-hidden="true">{item.icon}</span><span><strong>{item.title}</strong><small>{item.text}</small></span><span className="plan-radio-dot" aria-hidden="true" /></label>)}</fieldset>
        <label className="plan-goal-label" htmlFor="plan-goal">Your goal</label>
        <textarea ref={goalInput} id="plan-goal" required maxLength={2500} rows={3} value={goal} onChange={e => setGoal(e.target.value)} placeholder={skill === 'code_analysis' ? 'What would you like Python to calculate, test or analyze?' : skill === 'assessment' ? 'What would you like to test your understanding of?' : skill === 'research_brief' ? 'What topic would you like to understand better?' : 'Tell Aura what you’re studying and what you want to feel ready for…'} aria-describedby="plan-goal-hint" />
        {skill === 'research_brief' && <p className="plan-caption" role="status">{webEnabled === true ? 'Aura checks your material, then looks up public topic keywords and links the web sources it uses.' : webEnabled === false ? 'Web search is unavailable. Research will use your uploaded material.' : 'Aura will report which sources were available for this research.'}</p>}
        {skill === 'assessment' && <p className="plan-caption">Aura will create {quizCount} multiple-choice questions from your material and check their sources. Answer and get feedback in Assessment.</p>}
        {skill === 'code_analysis' && <div className="plan-code-input"><p className="plan-caption">Python standard library · no network access · up to two attempts. A material is optional. Only attached CSVs and any material excerpts Aura reads are sent for execution.</p><label htmlFor="plan-code-files">Attach CSV files <small>Optional · up to 2 files, 16 KiB each · UTF-8</small></label><input id="plan-code-files" type="file" accept=".csv,text/csv" multiple disabled={busy || readingFiles} onChange={e => void attachCSVs(Array.from(e.target.files ?? []))} />{readingFiles && <p role="status">Reading files…</p>}{inputError && <p role="alert">{inputError}</p>}{codeInputs.length > 0 && <><ul>{codeInputs.map(item => <li key={item.name}>{item.name}</li>)}</ul><button type="button" onClick={() => { ++fileReadVersion.current; setCodeInputs([]); setInputError(''); setReadingFiles(false); const field = document.getElementById('plan-code-files') as HTMLInputElement; if (field) field.value = '' }}>Remove files</button></>}</div>}
        <div className="plan-examples" aria-label="Example goals">{goalExamples.map(example => <button key={example.label} type="button" onClick={() => useExample(example)}>{example.label}<span aria-hidden="true"> ↗</span></button>)}</div>
        {skill !== 'code_analysis' && <details className="plan-options"><summary>Options <span>Time, depth &amp; memory</span></summary><div className="plan-option-fields">{skill === 'assessment' && <><label>Questions<select value={quizCount} onChange={e => setQuizCount(Number(e.target.value))}>{[1, 2, 3, 4, 5].map(value => <option key={value} value={value}>{value}</option>)}</select></label><label>Difficulty<select value={quizDifficulty} onChange={e => setQuizDifficulty(e.target.value)}>{['beginner', 'intermediate', 'advanced'].map(value => <option key={value} value={value}>{value}</option>)}</select></label></>}{skill === 'study_plan' && <><label>Days available<input type="number" min={1} max={14} step={1} value={options.days} placeholder="Optional · 1–14" onChange={e => setOptions({ ...options, days: e.target.value })} /></label><label>Minutes per day<input type="number" min={5} max={600} step={1} value={options.minutes} placeholder="Optional · e.g. 30" onChange={e => setOptions({ ...options, minutes: e.target.value })} /></label></>}<label>Depth<select value={options.depth} onChange={e => setOptions({ ...options, depth: e.target.value as PlanOptions['depth'] })}><option value="quick">Quick</option><option value="standard">Standard</option><option value="deep">Deep</option></select></label></div><div className="plan-memory-option"><label><input type="checkbox" role="switch" checked={allowMemory && memory.enabled} disabled={!memory.enabled} onChange={e => setAllowMemory(e.target.checked)} /><span>Remember what I learn from this plan<small>{memory.enabled ? 'Aura can save preferences you explicitly ask it to remember.' : 'Memory is off in this workspace.'}</small></span></label><button ref={manageMemoryButton} type="button" className="plan-text-button" onClick={() => setMemoryOpen(true)}>Manage memory</button></div></details>}
        <div className="plan-compose-footer"><p id="plan-goal-hint">{skill === 'code_analysis' ? codeEnabled ? 'Code runs in an isolated environment. Results are saved with this run.' : 'Enable a Python execution backend to begin.' : !sourceId ? 'Choose a material to create your plan.' : !materialReady ? 'Your material needs to finish preparing before you begin.' : activeCount >= 2 ? 'Two plans are already in progress. Finish or cancel one to begin.' : 'Your progress is saved, even when you leave.'}</p><button type="submit" className="plan-primary" disabled={!canStart}>{busy ? 'Saving…' : skill === 'code_analysis' ? 'Run analysis' : skill === 'assessment' ? 'Create my quiz' : skill === 'research_brief' ? 'Start research' : 'Create my plan'} <span aria-hidden="true">→</span></button></div>
      </form>
      {loaded && !run && <div className="plan-empty plan-empty--quiet"><span aria-hidden="true">✦</span><h3>Your next study session, thoughtfully planned</h3><p>Choose an example above or tell Aura your goal. Your plan and checklist will live here.</p></div>}
      {run && <section className="plan-result" aria-labelledby="plan-result-title">
        <header className="plan-result-heading"><div><span className={`plan-status ${early || run.state === 'failed' ? 'plan-status--warning' : ''}`}>{stateLabel(run.state)}</span><h2 ref={resultHeading} tabIndex={-1} id="plan-result-title">{working ? 'Making a little room for progress' : early ? 'Stopped early. Here is what Aura found so far.' : run.state === 'failed' ? 'Something went wrong' : run.state === 'cancelled' ? 'Cancelled' : run.request.skill === 'code_analysis' ? 'Your analysis' : run.request.skill === 'assessment' ? 'Your quiz is ready' : run.request.skill === 'research_brief' ? 'Your research brief' : 'Your study plan'}</h2><p>{displayGoal(run.request.goal)}</p></div><div className="plan-result-actions">{working ? <button type="button" disabled={busy} onClick={() => void act(() => cancelAgent(courseId, run.id))}>Cancel</button> : <>{hasContent && !assessment && run.request.skill !== 'code_analysis' && <button type="button" onClick={download}>Download .md</button>}{run.state === 'completed' && <button type="button" disabled={!canRegenerate} onClick={() => regenerate()}>Regenerate</button>}</>}</div></header>
        {run.source_id && String(run.source_id) !== sourceId && <p className="plan-caption">Saved work for: {materialNames[String(run.source_id)] ?? 'a different material'}. Review actions use that file; regenerating uses the material selected above.</p>}
        {working && <div className="plan-progress"><ol>{finishedSteps.map((step, index) => <li key={index}><span className="plan-step-mark" aria-hidden="true">✓</span><span>{progressLabel(step.tool)}</span><small>Done</small></li>)}<li aria-current="step"><span className="plan-step-mark plan-step-mark--current" aria-hidden="true"><span className="plan-spinner" /></span><span>{run.state === 'queued' ? 'Getting ready to begin' : progressLabel(currentStep?.tool ?? '')}</span><small>In progress</small></li></ol><p>You can leave this page. Aura will keep working.</p></div>}
        {!working && codeOutput && <CodeResult run={run} courseId={courseId} />}
        {!working && assessment && <div className="plan-content plan-quiz-ready"><span className="plan-kicker">READY TO PRACTICE</span><h3>{assessment.title}</h3><p>{assessment.question_count} multiple-choice questions · {assessment.difficulty}</p><p className="plan-caption">Questions were checked against cited passages by an AI model. Your score and feedback appear after you answer in Assessment.</p><button type="button" className="plan-primary" disabled={!run.source_id} onClick={() => onOpenTool('Assessment', assessment.focus, String(run.source_id), assessment.artifact_id)}>Open my quiz <span aria-hidden="true">↗</span></button></div>}
        {!working && run.result?.research_sections && <ResearchResult run={run} />}
        {!working && hasContent && !assessment && run.request.skill !== 'code_analysis' && !run.result?.research_sections && <div className="plan-content">{run.result?.verified !== true && <p className="plan-caption">A draft based on your material. Check the source slides as you study.</p>}{content!.overview && <RichText text={content!.overview} />}<div className="plan-days">{content!.days.map(day => {
          const task = taskForDay(day, tasks), refs = slideReferences(run, day.references), minutes = runOptions[run.id]?.minutes
          return <article className="plan-day" key={day.day}><div className="plan-day-top"><span className="plan-day-number">DAY {String(day.day).padStart(2, '0')}</span><small>{minutes ? `${minutes} min · your time budget` : 'Time not set'}</small></div><h3>{day.title}</h3><p className="plan-caption">Topics: {day.title}</p><RichText text={day.details} />{task ? <label className="plan-day-check"><input type="checkbox" checked={task.done} disabled={busy} onChange={e => void act(() => updateTask(courseId, task.id, e.target.checked))} /><span>{task.done ? 'Day complete' : 'Mark this day’s study task complete'}</span></label> : <p className="plan-caption">{day.taskId ? 'This saved task is currently unavailable.' : 'No saved checklist is attached to this day.'}</p>}{refs.length > 0 && <div className="plan-citations" aria-label="Source slides">{[...new Set(refs.map(r => r.slide))].map(slide => <span key={slide}>Slide {slide}</span>)}</div>}<div className="plan-day-actions">{([{ tab: 'Flashcards', text: 'Review flashcards' }, { tab: 'Assessment', text: 'Take a quick quiz' }, { tab: 'Summary', text: 'Read summary' }] as const).map(action => <button type="button" key={action.tab} disabled={!run.source_id} onClick={() => onOpenTool(action.tab, day.title, String(run.source_id))}>{action.text}<span aria-hidden="true"> ↗</span></button>)}</div></article>
        })}</div></div>}
        {!working && !hasContent && <p className="plan-no-content">{early ? 'Aura saved its progress, but no readable plan was ready yet. Try a shorter goal or fewer days.' : run.state === 'cancelled' ? 'Your existing tasks and preferences are still saved. Start again whenever you’re ready.' : run.state === 'failed' ? run.request.skill === 'code_analysis' ? codeFailureMessage(run) : run.request.skill === 'assessment' ? 'Aura could not finish checking this quiz. Try a narrower topic or fewer questions.' : run.request.skill === 'research_brief' ? run.error_code === 'invalid_action' ? 'Aura could not finish formatting this research brief. Try again.' : 'Aura could not finish this research brief. Try a narrower topic or retry.' : 'Your material is safe. Try creating the plan again.' : 'This run did not return a readable plan. You can try creating it again.'}</p>}
        {!working && (early || ['failed', 'cancelled'].includes(run.state)) && <div className="plan-recovery"><button className="plan-primary" type="button" disabled={!canRegenerate} onClick={() => regenerate()}>{run.state === 'failed' ? 'Retry' : run.state === 'cancelled' ? 'Start again' : 'Try again'}</button>{early && <button type="button" disabled={!canRegenerate} onClick={() => regenerate(true)}>Make it simpler</button>}</div>}
        <details className="plan-run-details"><summary>Run details</summary><dl><div><dt>Status</dt><dd>{run.state}</dd></div><div><dt>Duration</dt><dd>{duration(run)}</dd></div><div><dt>Steps</dt><dd>{run.steps.length}</dd></div><div><dt>Tools used</dt><dd>{[...new Set(run.steps.map(s => s.tool))].join(', ') || 'None reported'}</dd></div><div><dt>Models used</dt><dd>Not reported by the API</dd></div><div><dt>Total tokens</dt><dd>{run.tokens_used.toLocaleString()}</dd></div>{webAttempts.length > 0 && <><div><dt>Web searches</dt><dd>{webAttempts.length}</dd></div><div><dt>Reported search credits</dt><dd>{reportedCredits.every(n => n === null) ? 'Not reported' : `${knownCredits}${reportedCredits.some(n => n === null) ? ' (some requests unreported)' : ''}`}</dd></div></>}{run.error_code && <div><dt>Technical reason</dt><dd>{run.error_code}</dd></div>}</dl></details>
      </section>}
    </>}
    {loaded && visible.length > 0 && <section className="plan-recent"><div className="plan-section-heading"><div><h2>Recent plans</h2><p>Pick up a previous plan or research brief.</p></div><button type="button" className="plan-text-button" onClick={() => { setSelected('__new__'); setPane('Plan'); setGoal(''); goalInput.current?.focus() }}>New plan +</button></div><ul>{visible.map(item => <li key={item.id} className={item.id === run?.id ? 'is-open' : ''}><button type="button" className="plan-recent-open" aria-pressed={item.id === run?.id} onClick={() => { setSelected(item.id); setPane('Plan'); requestAnimationFrame(() => resultHeading.current?.focus()) }}><span><strong>{displayGoal(item.request.goal)}</strong><small>{dateLabel(item.created_at)}</small></span><span className="plan-status">{stateLabel(item.state)}</span></button>{!isActive(item) && <button className="plan-remove" type="button" aria-label={`Remove ${displayGoal(item.request.goal)} from recent plans on this browser`} title="Remove from recent plans on this browser" onClick={() => { setHidden(v => [...v, item.id]); setRemoved(item.id); if (selected === item.id) setSelected('__new__') }}>×</button>}</li>)}</ul><p className="plan-caption">Removing a plan hides it on this browser. It does not delete the saved run.</p></section>}
    {removed && <p className="plan-notice" role="status">Removed from recent plans on this browser. <button type="button" onClick={() => { setHidden(v => v.filter(id => id !== removed)); setRemoved(undefined) }}>Undo</button></p>}
    {active && run?.id !== active.id && <div className="plan-notice" role="status">Another plan is in progress. <button type="button" onClick={() => { setSelected(active.id); setPane('Plan') }}>View progress</button></div>}
    {memoryOpen && <MemoryDialog courseId={courseId} onClose={() => { setMemoryOpen(false); setRefresh(v => v + 1); manageMemoryButton.current?.focus() }} />}
  </section>
}
