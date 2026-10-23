import { useEffect, useState } from 'react'
import { cancelAgent, deleteMemory, getAgentRuns, getMemories, getTasks, saveMemory, startAgent, toggleMemory, updateTask } from '../services/agentApi'
import type { AgentRun, MemoryInput, MemoryKind, MemoryState, Task } from '../services/agentApi'
import './AgentPanel.css'

const fresh = (): MemoryInput => ({ kind: 'preference', text: '', depth: null, examples: null })
const active = (run: AgentRun) => ['queued', 'running'].includes(run.state)
const readable = (value: string) => value.replaceAll('_', ' ')
const toolNames: Record<string, string> = { document_search: 'Search your material', memory_read: 'Read preferences and memories', memory_write: 'Save a memory', task_list: 'Review your tasks', task_create: 'Create a study task', finish: 'Prepare the result', validation: 'Check the next action' }
export default function AgentPanel({ courseId, sourceId, materialReady }: { courseId: string; sourceId: string; materialReady: boolean }) {
  const [pane, setPane] = useState<'Agents' | 'Memory' | 'Tasks'>('Agents')
  const [memory, setMemory] = useState<MemoryState>({ enabled: true, items: [] })
  const [tasks, setTasks] = useState<Task[]>([])
  const [runs, setRuns] = useState<AgentRun[]>([])
  const [selected, setSelected] = useState('')
  const [record, setRecord] = useState<MemoryInput>(fresh)
  const [editing, setEditing] = useState<string>()
  const [goal, setGoal] = useState('')
  const [skill, setSkill] = useState('study_plan')
  const [allowMemory, setAllowMemory] = useState(false)
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')
  const [refresh, setRefresh] = useState(0)
  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    async function load() {
      try {
        const [mem, jobs, todo] = await Promise.all([getMemories(courseId), getAgentRuns(courseId), getTasks(courseId)])
        if (cancelled) return
        setMemory(mem); setRuns(jobs); setTasks(todo); setLoaded(true)
        if (jobs.some(active)) timer = setTimeout(() => void load(), 2000)
      } catch (e) { if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load your saved work.') }
    }
    void load()
    return () => { cancelled = true; if (timer) clearTimeout(timer) }
  }, [courseId, refresh])
  async function act(work: () => Promise<unknown>) {
    if (busy) return
    setBusy(true); setError('')
    try { await work(); setRefresh(v => v + 1) }
    catch (e) { setError(e instanceof Error ? e.message : 'Please retry this action.') }
    finally { setBusy(false) }
  }
  const run = runs.find(r => r.id === selected) ?? runs[0]
  return <section className="sw-agents">
    <nav aria-label="Agent workspace">{(['Agents', 'Memory', 'Tasks'] as const).map(p => <button type="button" key={p} aria-pressed={p === pane} onClick={() => setPane(p)}>{p}</button>)}</nav>
    {error && <p role="alert" className="sw-error">{error} <button type="button" onClick={() => { setError(''); setRefresh(v => v + 1) }}>Retry</button></p>}
    {!loaded && !error && <p role="status">Loading your saved work…</p>}
    {pane === 'Memory' && <>
      <h2>What Aura remembers</h2><p>Saved for this workspace. Turn memory off to stop using it in new answers and future memory reads. Existing records stay available to edit or delete.</p>
      <label className="agent-check"><input type="checkbox" checked={memory.enabled} disabled={busy || !loaded} onChange={e => void act(() => toggleMemory(courseId, e.target.checked))} />Use saved memory</label>
      <form onSubmit={e => { e.preventDefault(); void act(async () => { await saveMemory(courseId, record, editing); setRecord(fresh()); setEditing(undefined) }) }}>
        <label>Type<select value={record.kind} onChange={e => setRecord({ kind: e.target.value as MemoryKind, text: record.text, depth: null, examples: null })}>{['preference', 'decision', 'event', 'task_progress', 'learner_fact'].map(k => <option key={k} value={k}>{readable(k)}</option>)}</select></label>
        <label>Memory<textarea value={record.text} maxLength={1000} required onChange={e => setRecord({ ...record, text: e.target.value })} placeholder="e.g. I learn best with concrete examples" /></label>
        {record.kind === 'preference' && <><label>Preferred depth<select value={record.depth ?? ''} onChange={e => setRecord({ ...record, depth: (e.target.value || null) as MemoryInput['depth'] })}><option value="">No preference</option><option value="beginner">Beginner</option><option value="standard">Standard</option><option value="advanced">Advanced</option></select></label><label>Examples<select value={record.examples === null ? '' : String(record.examples)} onChange={e => setRecord({ ...record, examples: e.target.value === '' ? null : e.target.value === 'true' })}><option value="">No preference</option><option value="true">Use supported examples</option><option value="false">No example preference</option></select></label></>}
        <div><button className="sw-primary" disabled={busy || !loaded || !record.text.trim()} type="submit">{editing ? 'Save changes' : 'Save memory'}</button>{editing && <button type="button" onClick={() => { setEditing(undefined); setRecord(fresh()) }}>Cancel edit</button>}</div>
      </form>
      <div className="agent-records">{memory.items.map(item => <article key={item.id}><small>{readable(item.record.kind)}</small><p>{item.record.text}</p>{item.record.depth && <span>Depth: {item.record.depth}</span>}<div><button type="button" disabled={busy} onClick={() => { setRecord(item.record); setEditing(item.id) }}>Edit</button><button type="button" disabled={busy} onClick={() => void act(() => deleteMemory(courseId, item.id))}>Delete</button></div></article>)}{loaded && !memory.items.length && <p>No memories saved yet.</p>}</div>
    </>}
    {pane === 'Tasks' && <><h2>Your study tasks</h2><p>Study-plan agents can create these tasks. Mark them complete as you work.</p>{tasks.map(task => <article className="agent-task" key={task.id}><label className="agent-check"><input type="checkbox" checked={task.done} disabled={busy} onChange={e => void act(() => updateTask(courseId, task.id, e.target.checked))} /><strong>{task.title}</strong></label><p>{task.details}</p></article>)}{loaded && !tasks.length && <p>Your study tasks will appear here.</p>}</>}
    {pane === 'Agents' && <>
      <h2>Give Aura a study task</h2><p>Build a study plan or research your uploaded material. Runs keep their progress if you leave this page.</p>
      <p>{sourceId ? materialReady ? 'Uses your selected material.' : 'Wait until the selected material is ready before starting a run.' : 'Uses the materials in this workspace.'}</p>
      <form onSubmit={e => { e.preventDefault(); void act(async () => { const value = await startAgent(courseId, sourceId, goal, skill, allowMemory); setSelected(String(value.id)) }) }}>
        <label>Skill<select value={skill} onChange={e => setSkill(e.target.value)}><option value="study_plan">Study plan</option><option value="research_brief">Research brief from your material</option></select></label>
        <label>Your goal<textarea value={goal} maxLength={3000} required onChange={e => setGoal(e.target.value)} placeholder="Create a three-day revision plan and save tasks for each day." /></label>
        <label className="agent-check"><input type="checkbox" checked={allowMemory} onChange={e => setAllowMemory(e.target.checked)} />Allow this run to save memories I ask it to remember</label>
        <button className="sw-primary" disabled={busy || !loaded || !goal.trim() || (!!sourceId && !materialReady) || runs.filter(active).length >= 2} type="submit">Start agent</button>
      </form>
      <div className="agent-history">{runs.map(job => <button type="button" key={job.id} aria-pressed={run?.id === job.id} onClick={() => setSelected(job.id)}>{job.request.goal.slice(0, 70)} <small>{readable(job.state)}</small></button>)}</div>
      {run && <article className="agent-run"><div className="agent-run-heading"><h3>{readable(run.state)}</h3>{active(run) && <button type="button" disabled={busy} onClick={() => void act(() => cancelAgent(courseId, run.id))}>Cancel run</button>}</div>
        {!!run.steps[0]?.plan?.length && <ol>{run.steps[0].plan.map((step, i) => <li key={i}>{step}</li>)}</ol>}
        <ol className="agent-timeline" aria-label="Agent progress">{run.steps.map((step, i) => <li key={i}><strong>{toolNames[step.tool] ?? step.tool}</strong><span>{step.state}</span>{step.error_code && <small>{readable(step.error_code)}</small>}</li>)}</ol>
        {run.error_code && <p role="status">Run stopped: {readable(run.error_code)}. Saved progress and previously created tasks remain available.</p>}
        {run.result && <div className="agent-result"><small>Agent draft — review its sources</small><p>{run.result.text}</p>{run.result.references.length > 0 && <p>Document references: {run.result.references.join(', ')}</p>}</div>}
        {run.steps.filter(step => step.tool === 'document_search' && step.observation).map((step, i) => {
          const observation = step.observation as { passages?: { reference: string; title: string; page?: number; slide?: number; text: string }[] }
          return <details key={i}><summary>Material consulted</summary>{observation.passages?.map(p => <article key={p.reference}><strong>{p.title} · {p.slide ? `Slide ${p.slide}` : p.page ? `Page ${p.page}` : 'Material'} · {p.reference}</strong><p>{p.text}</p></article>)}</details>
        })}
      </article>}
    </>}
  </section>
}
