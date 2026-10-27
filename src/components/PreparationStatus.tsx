import { useEffect, useRef, useState } from 'react'
import { listPreparation, preparationLabel, retryPreparation } from '../services/preparationApi'
import type { PreparationJob } from '../services/preparationApi'
import './PreparationStatus.css'

type Props = { simple?: boolean; courseId: string; refreshKey: number; pendingId?: string; pendingIds?: string[]; onReady: (job: PreparationJob) => void; onFailed?: (job: PreparationJob) => void }

export default function PreparationStatus({ courseId, refreshKey, pendingId, pendingIds, onReady, onFailed, simple = false }: Props) {
  const [jobs, setJobs] = useState<PreparationJob[]>([])
  const [error, setError] = useState('')
  const [retrying, setRetrying] = useState('')
  const [dismissed, setDismissed] = useState<string[]>([])
  const observed = useRef<Map<string, string>>(new Map())
  const readyCallback = useRef(onReady)
  const failedCallback = useRef(onFailed)
  const pending = useRef(pendingId)
  const batchPending = useRef<string[]>([])
  batchPending.current = pendingIds ?? []
  pending.current = pendingId
  readyCallback.current = onReady
  failedCallback.current = onFailed
  useEffect(() => {
    observed.current.clear()
    setJobs([]); setDismissed([])
  }, [courseId])
  useEffect(() => {
    if (!courseId) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout>
    async function poll() {
      try {
        const values = await listPreparation(courseId)
        if (cancelled) return
        setJobs(values); setError('')
        for (const job of values) {
          const previous = observed.current.get(job.id)
          observed.current.set(job.id, job.state)
          const tracked = previous || pending.current === job.id || batchPending.current.includes(job.id)
          if (tracked && previous !== 'ready' && job.state === 'ready') readyCallback.current(job)
          if (tracked && previous !== 'failed' && job.state === 'failed') failedCallback.current?.(job)
        }
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : 'Could not check preparation. Retrying…')
      }
      if (!cancelled) timer = setTimeout(() => void poll(), 2000)
    }
    void poll()
    return () => { cancelled = true; clearTimeout(timer) }
  }, [courseId, refreshKey])

  async function retry(id: string) {
    setRetrying(id); setError('')
    try {
      const job = await retryPreparation(id)
      observed.current.set(job.id, 'queued')
      setJobs(current => current.map(item => item.id === id ? job : item))
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not retry preparation.') }
    finally { setRetrying('') }
  }
  const visible = jobs.filter(job => (job.state !== 'ready' || !!job.result?.warnings?.length) && !dismissed.includes(job.id))
    .sort((a, b) => Number(a.state === 'ready') - Number(b.state === 'ready')).slice(0, 5)
  if (!visible.length && !error) return null
  return <section className="aura-preparation" aria-label="Material preparation">
    {error && <p className="aura-preparation-error" role="alert">{simple ? 'Could not check your material yet. Aura will try again.' : error}</p>}
    {visible.map(job => <div key={job.id} className="aura-preparation-item">
      <div><strong>{job.filename}</strong><span role="status">{simple ? job.state === 'ready' ? 'Ready to study' : job.state === 'failed' ? 'Needs attention' : 'Preparing your material' : preparationLabel(job)}{!simple && job.percentage !== null && job.state === 'processing' ? ` · ${job.percentage}% of this step` : ''}</span></div>
      {job.state === 'processing' && <progress max={100} value={job.percentage ?? undefined} aria-label={simple ? 'Preparing your material' : preparationLabel(job)} />}
      {job.state === 'ready' && !!job.result?.warnings?.length && <>
        <p>Ready with reading limitations. Some image or diagram details may be missing.</p>
        {!simple && <details><summary>Reading notices</summary><ul>{job.result.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></details>}
        <button type="button" onClick={() => setDismissed(current => [...current, job.id])}>Dismiss</button>
      </>}
      {job.state === 'failed' && <><p>{simple ? 'This material could not be prepared. Please try again.' : job.error}</p><button type="button" disabled={retrying === job.id} onClick={() => void retry(job.id)}>{retrying === job.id ? 'Retrying…' : 'Retry preparation'}</button><button type="button" onClick={() => setDismissed(current => [...current, job.id])}>Dismiss</button></>}
    </div>)}
  </section>
}

