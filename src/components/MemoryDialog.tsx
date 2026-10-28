import { Skeleton } from './ui'
import { useEffect, useRef, useState } from 'react'
import { ApiHttpError, ApiUnavailableError } from '../services/apiClient'
import { createPortal } from 'react-dom'
import { deleteMemory, getMemories, saveMemory, toggleMemory } from '../services/agentApi'
import type { MemoryInput, MemoryKind, MemoryState } from '../services/agentApi'
import './AccountMenu.css'
const fresh = (): MemoryInput => ({ kind: 'preference', text: '', depth: null, examples: null })
const kinds: Record<MemoryKind, string> = { preference: 'Learning preference', decision: 'Decision', event: 'Milestone', task_progress: 'Study progress', learner_fact: 'About your learning' }
export default function MemoryDialog({ courseId, onClose }: { courseId: string; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const textInput = useRef<HTMLTextAreaElement>(null)
  const [memory, setMemory] = useState<MemoryState>({ enabled: false, items: [] })
  const [record, setRecord] = useState<MemoryInput>(fresh)
  const [editing, setEditing] = useState<string>()
  const [loaded, setLoaded] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState<{ text: string; undo: () => Promise<unknown> }>()
  const [reload, setReload] = useState(0)
  useEffect(() => {
    const node = dialog.current
    const before = document.activeElement as HTMLElement | null
    if (node && !node.open) node.showModal()
    // React autofocus runs before showModal; focus after entering the top layer.
    textInput.current?.focus()
    return () => { if (node?.open) node.close?.(); before?.focus() }
  }, [])
  useEffect(() => {
    let cancelled = false
    setLoaded(false); setError('')
    getMemories(courseId).then(value => { if (!cancelled) { setMemory(value); setLoaded(true); setError('') } }).catch(cause => { if (!cancelled) setError(cause instanceof ApiHttpError && cause.status === 404 ? 'Memory is unavailable for this workspace. Update Aura, then retry.' : cause instanceof ApiHttpError && cause.status === 401 ? 'Your session expired. Sign in again.' : cause instanceof ApiUnavailableError ? 'Aura could not be reached. Check your connection, then retry.' : 'Memory could not be loaded. Your saved records have not been changed. Please retry.') })
    return () => { cancelled = true }
  }, [courseId, reload])
  async function act(work: () => Promise<unknown>) {
    if (busy) return
    setBusy(true); setError('')
    try { await work(); setReload(v => v + 1) }
    catch { setError('Could not save this change. Please try again.') }
    finally { setBusy(false) }
  }
  return createPortal(<dialog ref={dialog} className="aura-memory" aria-labelledby="memory-title" onCancel={e => { e.preventDefault(); onClose() }} onClick={e => { if (e.target === dialog.current) { const b = dialog.current.getBoundingClientRect(); if (e.clientX < b.left || e.clientX > b.right || e.clientY < b.top || e.clientY > b.bottom) onClose() } }}>
    <header><div><span className="aura-memory__eyebrow">PERSONAL TO YOU</span><h2 id="memory-title">What Aura remembers</h2></div><button type="button" aria-label="Close memory settings" onClick={onClose}>✕</button></header>
    <p>Help Aura understand how you learn. You can change or delete anything saved here.</p>
    <label className="aura-memory__toggle"><span><strong>Use saved memory</strong><small>Applies to this study workspace. Turning it off keeps your records but stops Aura using or adding them here.</small></span><input type="checkbox" role="switch" checked={memory.enabled} disabled={busy || !loaded} onChange={e => void act(() => toggleMemory(courseId, e.target.checked))} /></label>
    {error && <p role="alert">{error} <button type="button" onClick={() => { setError(''); setReload(v => v + 1) }}>Retry</button></p>}
    {!loaded && !error && <Skeleton label="Loading your memories" />}
    {notice && <p className="aura-memory__notice" role="status">{notice.text} <button type="button" disabled={busy} onClick={() => void act(async () => { await notice.undo(); setNotice(undefined) })}>Undo</button></p>}
    <div className="aura-memory__list">{memory.items.map(item => <article key={item.id}><small>{kinds[item.record.kind]}</small><p>{item.record.text}</p>{item.record.depth && <small>Explanation level: {item.record.depth}</small>}<div><button type="button" disabled={busy} onClick={() => { setEditing(item.id); setRecord(item.record); textInput.current?.focus() }}>Edit</button><button type="button" disabled={busy} onClick={() => void act(async () => { await deleteMemory(courseId, item.id); if (editing === item.id) { setEditing(undefined); setRecord(fresh()) }; setNotice({ text: 'Memory deleted.', undo: () => saveMemory(courseId, item.record) }) })}>Delete</button></div></article>)}{loaded && !memory.items.length && <div className="aura-memory__empty">A little understanding goes a long way.<p>Your saved preferences and learning milestones will appear here.</p></div>}</div>
    <form onSubmit={e => { e.preventDefault(); void act(async () => {
      const snapshot = memory.items
      const value = await saveMemory(courseId, record, editing)
      const id = String(value.id ?? '')
      const before = snapshot.find(m => m.id === id)
      setNotice({ text: `Noted: ${record.text}`, undo: () => before ? saveMemory(courseId, before.record, before.id) : deleteMemory(courseId, id) })
      setRecord(fresh()); setEditing(undefined)
    }) }}>
      <h3>{editing ? 'Edit a memory' : 'Tell Aura what helps'}</h3>
      <label>Type<select value={record.kind} onChange={e => setRecord({ ...fresh(), text: record.text, kind: e.target.value as MemoryKind })}>{Object.entries(kinds).map(([value, title]) => <option key={value} value={value}>{title}</option>)}</select></label>
      <label>What should Aura remember?<textarea ref={textInput} required rows={3} maxLength={1000} value={record.text} placeholder="I understand best with worked examples." onChange={e => setRecord({ ...record, text: e.target.value })} /></label>
      {record.kind === 'preference' && <div className="aura-memory__fields"><label>Explanation level<select value={record.depth ?? ''} onChange={e => setRecord({ ...record, depth: (e.target.value || null) as MemoryInput['depth'] })}><option value="">No preference</option><option value="beginner">Beginner</option><option value="standard">Standard</option><option value="advanced">Advanced</option></select></label><label>Examples<select value={record.examples === null ? '' : String(record.examples)} onChange={e => setRecord({ ...record, examples: e.target.value === '' ? null : e.target.value === 'true' })}><option value="">No preference</option><option value="true">Include examples</option><option value="false">Keep examples minimal</option></select></label></div>}
      <small className="aura-memory__hint">Type your preference above, then choose Save memory.</small>
      <div className="aura-memory__actions"><button type="submit" disabled={!loaded || busy || !record.text.trim()}>{editing ? 'Save changes' : 'Save memory'}</button>{editing && <button type="button" onClick={() => { setRecord(fresh()); setEditing(undefined) }}>Cancel edit</button>}</div>
    </form>
  </dialog>, document.body)
}
