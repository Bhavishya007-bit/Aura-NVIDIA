import { useEffect, useState } from 'react'
import { generationSupport, legacySupport } from '../services/generationSupport'
export function useGenerationSupport(courseId: string) {
  const [support, setSupport] = useState(legacySupport)
  const [setupNotice, setSetupNotice] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    setSupport(legacySupport); setSetupNotice('')
    if (courseId) generationSupport(controller.signal).then(value => { if (!controller.signal.aborted) setSupport(value) }).catch(() => { if (!controller.signal.aborted) setSetupNotice('Some study tools are unavailable. Check your connection and refresh Aura. Your saved work is kept.') })
    return () => controller.abort()
  }, [courseId])
  return { ...support, setupNotice }
}
