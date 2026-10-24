import { useEffect, useState } from 'react'
import './StudyControls.css'

export default function GenerationStatus({ active, cancelling = false, stopped, label = 'Creating your answer…', slow: suppliedSlow, notice, onStop, onKeepWaiting, startedAt }: {
  active: boolean; cancelling?: boolean; stopped?: 'stopped' | 'cancelled'; label?: string; slow?: boolean; notice?: string
  onStop: () => void; onKeepWaiting?: () => void
  startedAt?: string | null
}) {
  const [slow, setSlow] = useState(false)
  const [wait, setWait] = useState(0)
  useEffect(() => { setSlow(false); if (!active) return; const elapsed = !wait && startedAt && Number.isFinite(Date.parse(startedAt)) ? Math.max(0, Date.now() - Date.parse(startedAt)) : 0; const timer = setTimeout(() => setSlow(true), Math.max(0, 20000 - elapsed)); return () => clearTimeout(timer) }, [active, wait, startedAt])
  const delayed = suppliedSlow ?? slow
  return <div className="aura-generation-region">
    <div role="status" aria-live="polite" aria-atomic="true">{active ? <div className="aura-generation"><span className="aura-generation-dot" aria-hidden="true" /><span>{cancelling ? 'Cancelling…' : delayed ? 'Taking longer than usual' : label}</span>{!cancelling && <div>{delayed && <button type="button" onClick={() => { setWait(v => v + 1); onKeepWaiting?.() }}>Keep waiting</button>}<button type="button" className="aura-stop" onClick={onStop}><span aria-hidden="true">■</span> Stop <kbd>Esc</kbd></button></div>}</div> : stopped ? <p className="aura-generation-ended">{stopped === 'cancelled' ? 'Cancelled' : 'Stopped'} · Any received content is kept.</p> : null}</div>
    {notice && <p role="alert">{notice}</p>}
  </div>
}
