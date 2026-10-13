import { ApiResponseError, requestApi, requireRecord } from './apiClient'

export type PreparationJob = {
  id: string
  course_id: number
  source_id: number | null
  filename: string
  state: 'queued' | 'processing' | 'ready' | 'failed'
  stage: string
  percentage: number | null
  result: { source_id: number; course_id: number; source_name: string; source_type: string; status: 'success' | 'partial'; content_units: number } | null
  error: string | null
}

function decodeJob(value: unknown): PreparationJob {
  const row = requireRecord(value, 'preparation')
  if (typeof row.id !== 'string' || typeof row.course_id !== 'number' || typeof row.filename !== 'string'
      || !['queued', 'processing', 'ready', 'failed'].includes(String(row.state)) || typeof row.stage !== 'string'
      || !(row.source_id === null || typeof row.source_id === 'number')
      || !(row.percentage === null || (typeof row.percentage === 'number' && row.percentage >= 0 && row.percentage <= 100))) {
    throw new ApiResponseError('Aura returned an invalid preparation status.')
  }
  if (row.result !== null) {
    const result = requireRecord(row.result, 'prepared material')
    if (result.course_id !== row.course_id || result.source_id !== row.source_id || typeof result.source_name !== 'string'
        || typeof result.source_type !== 'string' || typeof result.content_units !== 'number'
        || !['success', 'partial', 'empty', 'error', 'not_configured'].includes(String(result.status))) {
      throw new ApiResponseError('Aura returned an invalid prepared material.')
    }
  }
  return row as unknown as PreparationJob
}

export async function startPreparation(courseId: string, file: File, signal?: AbortSignal): Promise<PreparationJob> {
  const form = new FormData()
  form.append('file', file, file.name)
  return requestApi(`courses/${encodeURIComponent(courseId)}/preparation-jobs`, { method: 'POST', body: form, signal }, value => {
    const job = decodeJob(value)
    if (String(job.course_id) !== courseId) throw new ApiResponseError('Preparation belongs to a different workspace.')
    return job
  })
}

export type UploadEntry = { file: File; state: 'waiting' | 'uploading' | 'queued' | 'failed'; error?: string; job?: PreparationJob }
export async function queueMaterials(courseId: string, files: File[], onUpdate: (entries: UploadEntry[]) => void, onQueued: (job: PreparationJob, first: boolean) => void, signal?: AbortSignal): Promise<UploadEntry[]> {
  if (!files.length || files.length > 5) throw new Error('Choose between 1 and 5 files per batch.')
  const entries: UploadEntry[] = files.map(file => ({ file, state: 'waiting' }))
  const emit = () => { if (!signal?.aborted) onUpdate(entries.map(entry => ({ ...entry }))) }
  let first = true
  emit()
  for (const entry of entries) {
    if (signal?.aborted) break
    try {
      if (!/\.(pdf|docx|ppt|pptx|mp4|mp3|wav|m4a|ogg|flac|aac|mpeg|mpga)$/i.test(entry.file.name)) throw new Error('Unsupported file type. Choose a PDF, DOCX, presentation, supported audio file or MP4.')
      if (entry.file.size === 0) throw new Error('This file is empty.')
      if (entry.file.size > 100 * 1024 * 1024) throw new Error('This file exceeds 100 MiB.')
      entry.state = 'uploading'; emit()
      const job = await startPreparation(courseId, entry.file, signal)
      if (signal?.aborted) break
      entry.state = 'queued'; entry.job = job; onQueued(job, first); first = false
    } catch (cause) {
      if (signal?.aborted) break
      entry.state = 'failed'; entry.error = cause instanceof Error ? cause.message : 'Could not upload this file.'
    }
    emit()
  }
  return entries
}

export async function listPreparation(courseId: string): Promise<PreparationJob[]> {
  return requestApi(`preparation-jobs?course_id=${encodeURIComponent(courseId)}`, { method: 'GET' }, value => {
    const row = requireRecord(value, 'preparation list')
    if (!Array.isArray(row.jobs)) throw new ApiResponseError('Aura returned an invalid preparation list.')
    const jobs = row.jobs.map(decodeJob)
    if (jobs.some(job => String(job.course_id) !== courseId)) throw new ApiResponseError('Preparation belongs to a different workspace.')
    return jobs
  })
}

export async function retryPreparation(id: string): Promise<PreparationJob> {
  return requestApi(`preparation-jobs/${encodeURIComponent(id)}/retry`, { method: 'POST' }, decodeJob)
}

export const preparationLabels: Record<string, string> = {
  queued: 'File uploaded · Waiting to prepare', reading: 'Reading your material',
  reading_pages: 'Reading pages and images', reading_slides: 'Reading slides and images',
  saving: 'Saving your material', loading_model: 'Getting the tutor ready',
  indexing: 'Making your material searchable', ready: 'Ready', failed: 'Needs attention',
}
