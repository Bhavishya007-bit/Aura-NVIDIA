import { useEffect, useId, useState } from 'react'
import { readWorkspace, saveWorkspace } from '../services/workspaceStorage'
import type { Material } from '../services/studyToolsApi'
import { fileType } from './studyPlanModel'
import './StudyControls.css'

export const materialReady = (item: Material) => !item.archived && ['success', 'partial', 'ready'].includes(item.status)
export function cleanSelection(value: unknown): string[] {
  return Array.isArray(value) ? [...new Set(value.filter((id): id is string => typeof id === 'string' && /^[1-9]\d*$/.test(id)))].slice(0, 5) : []
}
type StudySet = { id: string; name: string; materialIds: string[] }
type Props = { materials: Material[]; selected: string[]; onChange: (ids: string[]) => void; storageKey: string; disabled?: boolean; loading?: boolean }
export function MaterialChips({ materials, selected, onChange, disabled, onChangeOpen }: Omit<Props, 'storageKey'> & { onChangeOpen?: () => void }) {
  return <div className="aura-using" role="group" aria-label="Materials used for this work"><span className="aura-using-label">Using</span>
    {selected.length ? selected.map(id => <span className="aura-material-chip" key={id}><span title={materials.find(item => item.id === id)?.title}>{materials.find(item => item.id === id)?.title ?? 'Material unavailable'}</span><button type="button" disabled={disabled} aria-label={`Remove ${materials.find(item => item.id === id)?.title ?? 'material'} from selection`} onClick={() => onChange(selected.filter(value => value !== id))}>×</button></span>) : <span className="aura-control-hint">Choose a ready material to begin</span>}
    {onChangeOpen && <button className="aura-control-link" type="button" onClick={onChangeOpen}>Change</button>}
  </div>
}
export default function MaterialPicker({ materials, selected, onChange, storageKey, disabled = false, loading = false }: Props) {
  const [sets, setSets] = useState<StudySet[]>(() => {
    const data = readWorkspace<{ sets?: StudySet[] }>(storageKey, {})
    return Array.isArray(data.sets) ? data.sets.filter(item => typeof item?.id === 'string' && typeof item.name === 'string' && cleanSelection(item.materialIds).length).map(item => ({ ...item, materialIds: cleanSelection(item.materialIds) })).slice(0, 30) : []
  })
  const [notice, setNotice] = useState('')
  const [name, setName] = useState('')
  const [editing, setEditing] = useState<string | null>(null)
  const [deleteId, setDeleteId] = useState<string | null>(null)
  const inputId = useId()
  const ready = materials.filter(materialReady)
  const all = ready.length > 0 && ready.slice(0, 5).every(item => selected.includes(item.id))
  useEffect(() => saveWorkspace(storageKey, { sets }), [storageKey, sets])
  function toggle(id: string) {
    if (selected.includes(id)) onChange(selected.filter(value => value !== id))
    else if (selected.length < 5) { onChange([...selected, id]); setNotice('') }
    else setNotice('5 materials selected. Remove one before adding another.')
  }
  return <div className="aura-material-picker">
    <div className="aura-selection-toolbar"><label><input type="checkbox" checked={all} disabled={disabled || loading || !ready.length} onChange={() => { onChange(all ? [] : ready.slice(0, 5).map(item => item.id)); setNotice(ready.length > 5 && !all ? 'Selected the first 5 ready materials. You can swap them below.' : '') }} />Select all{ready.length > 5 ? ' (up to 5)' : ''}</label><span aria-live="polite" aria-atomic="true">{selected.length} / 5 selected</span></div>
    <p className="aura-control-hint">Use up to 5 materials together to keep your study session focused.</p>
    <div className="aura-material-options">{materials.filter(item => !item.archived).map(item => <label key={item.id} className={`aura-material-option ${selected.includes(item.id) ? 'is-selected' : ''}`}><input type="checkbox" checked={selected.includes(item.id)} disabled={disabled || !materialReady(item)} onChange={() => toggle(item.id)} /><span><strong>{item.title}</strong><small>{fileType(item.title, item.type)}{!materialReady(item) ? ['queued', 'processing', 'uploaded'].includes(item.status) ? ' · Preparing…' : ' · Needs attention' : ''}</small></span></label>)}</div>
    {notice && <p role="status" className="aura-control-hint">{notice}</p>}
    <details className="aura-study-sets"><summary>Study sets <span>{sets.length}</span></summary><p className="aura-control-hint">Save a group for one-tap selection. Sets are kept on this browser for this account.</p>
      <ul>{sets.map(set => <li key={set.id}><button type="button" className="aura-set-select" disabled={disabled || loading} onClick={() => {
        const available = set.materialIds.filter(id => ready.some(item => item.id === id))
        if (available.length !== set.materialIds.length) { setNotice('Some materials in this set are preparing, archived or unavailable. Restore them before using the full set.'); return }
        onChange(available); setNotice(`Using ${set.name}.`)
      }}>{set.name}<small>{set.materialIds.length} materials</small></button><button type="button" disabled={disabled} aria-label={`Rename ${set.name}`} onClick={() => { setEditing(set.id); setName(set.name) }}>✎</button><button type="button" disabled={disabled} aria-label={`Delete ${set.name}`} onClick={() => setDeleteId(set.id)}>×</button>{deleteId === set.id && <div className="aura-set-confirm"><span>Delete this set? Materials stay saved.</span><button type="button" onClick={() => { setSets(current => current.filter(item => item.id !== set.id)); setDeleteId(null); setNotice('Study set deleted.') }}>Delete set</button><button type="button" onClick={() => setDeleteId(null)}>Keep set</button></div>}</li>)}</ul>
      <div className="aura-set-editor"><label htmlFor={inputId}>{editing ? 'Rename study set' : 'Name this selection'}<input id={inputId} value={name} maxLength={60} disabled={disabled} onChange={event => setName(event.target.value)} placeholder="e.g. DBMS · Week 1" /></label><button type="button" disabled={disabled || !name.trim() || !editing && (!selected.length || sets.length >= 30)} onClick={() => {
        const title = name.trim()
        if (sets.some(item => item.id !== editing && item.name.toLocaleLowerCase() === title.toLocaleLowerCase())) { setNotice('A study set already uses that name. Choose a different name.'); return }
        setSets(current => editing ? current.map(item => item.id === editing ? { ...item, name: title } : item) : [...current, { id: crypto.randomUUID(), name: title, materialIds: [...selected] }]); setEditing(null); setName(''); setNotice('Study set saved.')
      }}>{editing ? 'Save name' : 'Save set'}</button>{editing && <button type="button" onClick={() => { setEditing(null); setName('') }}>Cancel rename</button>}</div>
    </details>
  </div>
}
