import { useCallback, useEffect, useRef, useState } from 'react'

export type GenerationTicket = { signal: AbortSignal; current: () => boolean; cancelRequested: () => boolean }
export function useGeneration() {
  const controller = useRef<AbortController | null>(null)
  const cancelWork = useRef<(() => Promise<void>) | null>(null)
  const pendingCancel = useRef(false)
  const finishedDuringCancel = useRef(false)
  const mounted = useRef(true)
  const [state, setState] = useState<'idle' | 'running' | 'cancelling' | 'stopped' | 'cancelled'>('idle')
  const [slow, setSlow] = useState(false)
  const [notice, setNotice] = useState('')
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const armTimer = useCallback(() => {
    clearTimeout(timer.current); setSlow(false)
    timer.current = setTimeout(() => setSlow(true), 20000)
  }, [])
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; controller.current?.abort(); clearTimeout(timer.current) } }, [])
  const start = useCallback((): GenerationTicket | null => {
    if (controller.current) return null
    const next = new AbortController(); controller.current = next; cancelWork.current = null; pendingCancel.current = false; finishedDuringCancel.current = false
    setState('running'); setNotice(''); armTimer()
    return { signal: next.signal, cancelRequested: () => pendingCancel.current, current: () => mounted.current && controller.current === next && !next.signal.aborted && !pendingCancel.current }
  }, [armTimer])
  const finish = useCallback((ticket: GenerationTicket) => {
    if (controller.current?.signal !== ticket.signal) return
    if (pendingCancel.current) { finishedDuringCancel.current = true; return }
    clearTimeout(timer.current); controller.current = null; cancelWork.current = null
    if (mounted.current) { setState('idle'); setSlow(false) }
  }, [])
  const stop = useCallback(async () => {
    const request = controller.current
    if (!request || request.signal.aborted || pendingCancel.current) return
    const cancel = cancelWork.current
    // For durable work, wait for the server's cancellation acknowledgement.
    if (cancel) {
      pendingCancel.current = true; setState('cancelling'); setNotice('')
      try { await cancel() }
      catch { pendingCancel.current = false; if (mounted.current && controller.current === request) { if (finishedDuringCancel.current) { controller.current = null; setState('idle') } else setState('running'); setNotice('Could not stop this work yet. Please try Stop again.'); armTimer() }; return }
    }
    if (!mounted.current || controller.current !== request) return
    request.abort(); controller.current = null; cancelWork.current = null; clearTimeout(timer.current)
    setSlow(false); setState(cancel ? 'cancelled' : 'stopped')
  }, [armTimer])
  useEffect(() => {
    if (state !== 'running') return
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !event.isComposing) { event.preventDefault(); void stop() }
    }
    window.addEventListener('keydown', escape)
    return () => window.removeEventListener('keydown', escape)
  }, [state, stop])
  return { state, active: state === 'running' || state === 'cancelling', slow, notice, start, finish, stop,
    keepWaiting: armTimer,
    setCancel: (callback: (() => Promise<void>) | null) => { cancelWork.current = callback },
  }
}
