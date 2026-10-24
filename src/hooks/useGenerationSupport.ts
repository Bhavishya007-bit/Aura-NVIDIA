import { useEffect, useState } from 'react'
import { generationSupport, legacySupport } from '../services/generationSupport'
export function useGenerationSupport(courseId: string) {
  const [support, setSupport] = useState(legacySupport)
  useEffect(() => {
    const controller = new AbortController()
    setSupport(legacySupport)
    if (courseId) generationSupport(controller.signal).then(value => { if (!controller.signal.aborted) setSupport(value) }).catch(() => {})
    return () => controller.abort()
  }, [courseId])
  return support
}
