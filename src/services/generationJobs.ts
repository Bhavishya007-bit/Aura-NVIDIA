import { ApiResponseError, requestApi, requireRecord } from './apiClient'
import { readWorkspace, saveWorkspace } from './workspaceStorage'
export type SavedGeneration = { id: string; course: string; operation: 'chat' | 'generate' | 'grade'; payload: Record<string, unknown> }
export type JobOptions = { enabled?: boolean; course?: string; storageKey?: string; signal?: AbortSignal; setCancel?: (cancel: (() => Promise<void>) | null) => void }
export function savedGeneration(key: string): SavedGeneration | undefined {
  const row = readWorkspace<{ job?: SavedGeneration }>(key, {}).job
  return row && typeof row.id === 'string' && typeof row.course === 'string' && ['chat','generate','grade'].includes(row.operation) && row.payload && typeof row.payload === 'object' ? row : undefined
}
function job(value: unknown) {
  const row = requireRecord(value, 'saved generation')
  if (typeof row.id !== 'string' || !['queued','running','completed','cancelled','failed'].includes(String(row.state))) throw new ApiResponseError('Could not read the saved work.')
  return row
}
const pause = (signal?: AbortSignal) => new Promise<void>((resolve, reject) => {
  const abort = () => { clearTimeout(timer); reject(new DOMException('Stopped', 'AbortError')) }
  const timer = setTimeout(() => { signal?.removeEventListener('abort', abort); resolve() }, 1000)
  if (signal?.aborted) abort(); else signal?.addEventListener('abort', abort, {once:true})
})
export async function resumeGeneration<T>(saved: SavedGeneration, decode: (value: unknown) => T, options: JobOptions): Promise<T> {
  const path = `study/generation-jobs/${encodeURIComponent(saved.id)}`
  const query = `?course_id=${encodeURIComponent(saved.course)}`
  options.setCancel?.(async () => { const row = await requestApi(`${path}/cancel${query}`, {method:'POST'}, job); if (row.id !== saved.id) throw new ApiResponseError('Could not confirm cancellation.'); if (options.storageKey) saveWorkspace(options.storageKey,{}) })
  while (true) {
    options.signal?.throwIfAborted()
    const row = await requestApi(`${path}${query}`, {method:'GET',signal:options.signal}, job)
    if (row.id !== saved.id || String(row.course_id) !== saved.course) throw new ApiResponseError('Could not confirm this saved work.')
    if (['completed','failed','cancelled'].includes(String(row.state))) {
      if (options.storageKey) saveWorkspace(options.storageKey, {})
      if (row.state === 'completed') return decode(row.result)
      if (row.state === 'cancelled') throw new DOMException('Cancelled', 'AbortError')
      throw new ApiResponseError('Aura could not finish this work. Your earlier results are kept; please retry.')
    }
    await pause(options.signal)
  }
}
export async function generationRequest<T>(operation: SavedGeneration['operation'], payload: Record<string, unknown>, decode: (value: unknown) => T, options: JobOptions): Promise<T> {
  const launch = requestApi('study/generation-jobs', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({course_id:Number(options.course),operation,payload})}, job)
  // Cancellation waits for a known server ID, including Stop pressed during creation.
  options.setCancel?.(async () => { const row = await launch; await requestApi(`study/generation-jobs/${encodeURIComponent(String(row.id))}/cancel?course_id=${encodeURIComponent(options.course!)}`, {method:'POST'}, job) })
  const row = await launch
  const saved: SavedGeneration = {id:String(row.id),course:options.course!,operation,payload}
  if (options.storageKey) saveWorkspace(options.storageKey, {job:saved})
  return resumeGeneration(saved, decode, options)
}
