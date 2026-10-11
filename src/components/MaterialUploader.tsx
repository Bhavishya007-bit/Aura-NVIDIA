import { useRef, useState } from 'react'
import './MaterialUploader.css'
import { removeMaterial, selectMaterials, type SelectedMaterial } from '../lib/materialSelection'
import { uploadCourseSource, type ProcessingStatus, type SourceUploadResponse } from '../services/sourcesApi'

export type UploadStatus = 'selected' | 'uploading' | 'complete' | 'partial' | 'empty' | 'not-configured' | 'failed' | 'error'
type FileState = { status: UploadStatus; sourceId?: string; message?: string }

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / (1024 * 1024)).toFixed(bytes >= 10 * 1024 * 1024 ? 0 : 1)} MB`
}

function fromProcessingStatus(status: ProcessingStatus): UploadStatus {
  if (status === 'success') return 'complete'
  if (status === 'partial') return 'partial'
  if (status === 'empty') return 'empty'
  if (status === 'not_configured') return 'not-configured'
  return 'failed'
}

function statusLabel(state: FileState): string {
  switch (state.status) {
    case 'selected': return 'Selected · not uploaded'
    case 'uploading': return 'Uploading and processing…'
    case 'complete': return 'Uploaded · text extracted'
    case 'partial': return 'Uploaded · partial extraction'
    case 'empty': return 'Uploaded · no text found'
    case 'not-configured': return 'Uploaded · transcription not configured'
    case 'failed': return 'Uploaded · extraction failed'
    case 'error': return 'Upload failed · retry available'
  }
}

function responseMessage(result: SourceUploadResponse): string {
  const count = result.contentUnitCount === 1 ? '1 content unit' : `${result.contentUnitCount} content units`
  if (result.processingStatus === 'success') return `Processing complete · ${count}.`
  if (result.processingStatus === 'partial') return `Some pages or slides had no selectable text · ${count}. ${result.warnings.join(' ')}`
  if (result.processingStatus === 'empty') return 'The source was stored, but no text was extracted.'
  if (result.processingStatus === 'not_configured') return result.warnings.join(' ')
  return result.warnings.join(' ') || 'The source was stored, but extraction failed.'
}

export default function MaterialUploader({ courseId, courseName }: { courseId: string; courseName: string }) {
  const input = useRef<HTMLInputElement>(null)
  const uploadLock = useRef(false)
  const [materials, setMaterials] = useState<SelectedMaterial[]>([])
  const [errors, setErrors] = useState<string[]>([])
  const [fileStates, setFileStates] = useState<Record<string, FileState>>({})
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)

  function addFiles(files: FileList | File[]) {
    const result = selectMaterials(Array.from(files))
    setErrors(result.errors)
    if (result.accepted.length) {
      setMaterials((current) => [...current, ...result.accepted])
      setFileStates((current) => ({ ...current, ...Object.fromEntries(result.accepted.map(({ id }) => [id, { status: 'selected' as const }])) }))
    }
    if (input.current) input.current.value = ''
  }

  function removeFile(id: string) {
    setMaterials((current) => removeMaterial(current, id))
    setFileStates((current) => {
      const { [id]: removed, ...remaining } = current
      void removed
      return remaining
    })
    setErrors([])
  }

  async function uploadSelected() {
    if (uploadLock.current) return
    const pending = materials.filter(({ id }) => !fileStates[id]?.sourceId && fileStates[id]?.status !== 'uploading')
    if (!pending.length) return

    uploadLock.current = true
    setUploading(true)
    setErrors([])
    try {
      for (const material of pending) {
        setFileStates((current) => ({ ...current, [material.id]: { status: 'uploading' } }))
        try {
          const result = await uploadCourseSource(courseId, material.file)
          setFileStates((current) => ({
            ...current,
            [material.id]: {
              status: fromProcessingStatus(result.processingStatus),
              sourceId: result.sourceId,
              message: responseMessage(result),
            },
          }))
        } catch (error) {
          setFileStates((current) => ({
            ...current,
            [material.id]: { status: 'error', message: error instanceof Error ? error.message : 'Upload failed. Please try again.' },
          }))
        }
      }
    } finally {
      uploadLock.current = false
      setUploading(false)
    }
  }

  const uploadedCount = Object.values(fileStates).filter((state) => Boolean(state.sourceId)).length
  const latestStatus = Object.values(fileStates).filter((state) => state.sourceId).at(-1)
  const pendingCount = materials.filter(({ id }) => !fileStates[id]?.sourceId).length
  const processingSummary = uploading
    ? 'Processing after upload'
    : latestStatus
      ? statusLabel(latestStatus)
      : 'Waiting for upload'

  return <div className="upload-layout"><section className="upload-main">
    <div className="upload-course-label">Adding materials to <strong>{courseName}</strong></div>
    <button className={`dropzone ${dragging ? 'dropzone-active' : ''}`} type="button" onClick={() => input.current?.click()}
      onDragOver={(event) => { event.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => { event.preventDefault(); setDragging(false); addFiles(event.dataTransfer.files) }}>
      <span className="upload-icon">↑</span><strong>Drop your materials here</strong><span>or browse files from your device</span><small>PDF, PPTX, DOCX, MP4 · Up to 100 MB each</small>
    </button>
    <input ref={input} className="visually-hidden" type="file" multiple accept=".pdf,.pptx,.docx,.mp4,application/pdf,application/vnd.openxmlformats-officedocument.presentationml.presentation,application/vnd.openxmlformats-officedocument.wordprocessingml.document,video/mp4" onChange={(event) => { if (event.target.files) addFiles(event.target.files) }} />

    {errors.length > 0 && <div className="upload-alert" role="alert"><strong>Some files could not be selected</strong><ul>{errors.map((error, index) => <li key={`${error}-${index}`}>{error}</li>)}</ul></div>}

    {materials.length > 0 && <div className="uploaded-list"><div className="uploaded-heading"><h2>Selected files</h2><span>{materials.length} {materials.length === 1 ? 'file' : 'files'}</span></div>{materials.map(({ id, file }) => {
      const state = fileStates[id] || { status: 'selected' as const }
      return <div className="uploaded-file" key={id}>
        <span className="selected-file-icon">{file.name.split('.').pop()?.toUpperCase()}</span><div className="selected-file-details"><strong>{file.name}</strong><small>{formatBytes(file.size)}</small>{state.message && <small className={`file-result-message file-result-${state.status}`} role={state.status === 'error' || state.status === 'failed' ? 'alert' : undefined}>{state.message}</small>}</div><span className={`file-status file-status-${state.status}`} aria-live="polite">{statusLabel(state)}</span><button type="button" disabled={uploading} onClick={() => removeFile(id)} aria-label={`Remove ${file.name}`}>×</button>
      </div>
    })}
      <button type="button" className="upload-submit" disabled={uploading || pendingCount === 0} onClick={uploadSelected}>{uploading ? 'Uploading…' : pendingCount === 0 ? 'All selected files uploaded' : `Upload ${pendingCount} ${pendingCount === 1 ? 'file' : 'files'}`}</button>
      <div className="pipeline-status"><span className="status-dot"/><div className="pipeline-copy"><strong>Upload and processing status</strong><div className="pipeline-steps"><span><b>Upload</b> {uploading ? 'In progress' : uploadedCount ? `${uploadedCount} uploaded` : 'Not started'}</span><span><b>Processing</b> {processingSummary}</span></div><p>{uploading ? 'The API is saving this file and running the extractor.' : uploadedCount ? 'Status is reported by the API. Demo metadata is kept in memory.' : 'Selected files stay in this browser until you choose Upload.'}</p></div></div>
    </div>}

    <div className="upload-footnote"><span>ⓘ</span><p>Uploads are sent to the configured FastAPI service. Original files use prototype local storage; extracted text is not yet saved to a database.</p></div>
    </section><aside className="upload-side"><div className="eyebrow">SUPPORTED MATERIALS</div><div className="material-type"><span className="type-icon pdf">PDF</span><div><strong>Textbooks &amp; notes</strong><small>PDF</small></div></div><div className="material-type"><span className="type-icon slides">PPT</span><div><strong>Lecture slides</strong><small>PPTX</small></div></div><div className="material-type"><span className="type-icon pdf">DOC</span><div><strong>Study documents</strong><small>DOCX</small></div></div><div className="material-type"><span className="type-icon video">▶</span><div><strong>Recorded lectures</strong><small>MP4</small></div></div><div className="demo-side-note"><span className="demo-tag">LOCAL API PROTOTYPE</span><div className="side-statuses"><span><b>Upload</b> {uploading ? 'In progress' : uploadedCount ? `${uploadedCount} uploaded` : 'Not started'}</span><span><b>Processing</b> {processingSummary}</span></div><p>MP4 transcription needs a provider. No transcript is fabricated.</p></div></aside></div>
}
