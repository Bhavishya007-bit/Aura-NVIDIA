import type { SourceUploadResult } from './studyApi'

export type ChatImage = { key: string; filename: string; stage: 'uploading' | 'embedding' | 'ready' | 'failed'; jobId?: string; source?: SourceUploadResult; error?: string }
export const imageFilename = (name: string) => /\.(png|jpe?g)$/i.test(name)
export function restoreChatImages(raw: unknown, courseId: string, legacy?: SourceUploadResult): ChatImage[] {
  const values = Array.isArray(raw) ? raw : []
  const images = values.slice(0, 5).flatMap((value): ChatImage[] => {
    if (!value || typeof value !== 'object') return []
    const item = value as Partial<ChatImage>
    if (typeof item.key !== 'string' || typeof item.filename !== 'string' || !imageFilename(item.filename)) return []
    const source = item.source && item.source.courseId === courseId && /^\d+$/.test(item.source.sourceId)
      && imageFilename(item.source.filename) ? item.source : undefined
    const jobId = typeof item.jobId === 'string' ? item.jobId : undefined
    const stage = source && item.stage === 'ready' ? 'ready' : jobId && ['uploading', 'embedding'].includes(item.stage ?? '') ? 'embedding' : 'failed'
    return [{ key: item.key, filename: item.filename, source, jobId, stage,
      ...(stage === 'failed' ? { error: 'Upload was interrupted. Remove this screenshot and attach it again.' } : {}) }]
  })
  if (images.length) return images
  return legacy && legacy.courseId === courseId && imageFilename(legacy.filename)
    ? [{ key: `source-${legacy.sourceId}`, filename: legacy.filename, source: legacy, stage: 'ready' }] : []
}
