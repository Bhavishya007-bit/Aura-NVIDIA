import { useEffect, useRef, useState } from 'react'
import type { ToolCitation } from '../services/studyToolsApi'
import type { ViewerInfo } from '../services/sourceViewerApi'
import { getViewerInfo, originalSource, sourceMedia, sourcePreview } from '../services/sourceViewerApi'
import { previewLocation } from '../services/citationDisplay'
import './SourceViewer.css'
import FigurePanel from './FigurePanel'

export default function SourceViewer({ citation, onClose }: { citation: ToolCitation | null; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [info, setInfo] = useState<ViewerInfo | null>(null)
  const [position, setPosition] = useState(1)
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const location = citation ? previewLocation(citation) : null

  useEffect(() => {
    if (citation) dialog.current?.showModal()
    else dialog.current?.close()
  }, [citation])
  useEffect(() => {
    let cancelled = false
    setInfo(null); setError(''); setUrl(''); setLoading(false)
    if (!citation) return
    const target = previewLocation(citation)
    if (!target) { setError('An exact original-file location is unavailable for this excerpt.'); return }
    setPosition(target.value)
    setLoading(true)
    getViewerInfo(citation.source_id).then(value => {
      if (cancelled) return
      const compatible = target.kind === 'timestamp' ? ['video_timestamp', 'audio_timestamp'].includes(value.kind) : value.kind === target.kind
      if (!compatible) throw new Error('The citation location does not match this original file. The excerpt remains available below.')
      if (value.page_count && target.value > value.page_count) throw new Error('The cited page or slide is outside this original file.')
      setInfo(value)
    }).catch(cause => { if (!cancelled) { setError(cause instanceof Error ? cause.message : 'Could not open the source.'); setLoading(false) } })
    return () => { cancelled = true }
  }, [citation])
  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false
    let objectUrl = ''
    if (!citation || !info || info.source_id !== citation.source_id) return
    setLoading(true); setError(''); setUrl('')
    const media = info.kind === 'video_timestamp' || info.kind === 'audio_timestamp'
    const request = media ? sourceMedia(citation.source_id, controller.signal) : sourcePreview(citation.source_id, position, controller.signal)
    request.then(blob => {
      if (cancelled) return
      if (!media && blob.type !== 'image/png') throw new Error('The backend did not return a page image.')
      objectUrl = URL.createObjectURL(blob)
      setUrl(objectUrl)
    }).catch(cause => {
      if (!cancelled) setError(cause instanceof Error ? cause.message : 'Could not load the source preview.')
    }).finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true; controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [citation, info, position])

  function seek(media: HTMLMediaElement) {
    const time = location?.kind === 'timestamp' ? location.value : 0
    if (!Number.isFinite(media.duration) || time > media.duration) {
      setError('The cited timestamp is outside this recording.'); media.pause(); return
    }
    media.currentTime = time
  }
  async function download() {
    if (!citation || downloading) return
    setDownloading(true)
    try {
      const blob = await originalSource(citation.source_id)
      const link = document.createElement('a')
      const downloadUrl = URL.createObjectURL(blob)
      link.href = downloadUrl; link.download = citation.title; link.click()
      setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not download the original.') }
    finally { setDownloading(false) }
  }
  if (!citation) return null
  const documentView = info?.kind === 'pdf_page' || info?.kind === 'slide'
  const label = info?.kind === 'slide' ? 'Slide' : 'Page'
  return <dialog ref={dialog} className="aura-source-viewer" aria-labelledby="source-viewer-title" onCancel={onClose}>
    <header><div><p className="sw-eyebrow">ORIGINAL SOURCE</p><h2 id="source-viewer-title">{citation.title}</h2><span>Cited location: {citation.location}</span></div><button type="button" onClick={onClose} aria-label="Close source viewer">×</button></header>
    <div className="aura-source-actions"><button type="button" disabled={downloading} onClick={() => void download()}>{downloading ? 'Downloading…' : 'Download original'}</button>
      {documentView && info.page_count && <div><button type="button" disabled={loading || position <= 1} onClick={() => setPosition(value => value - 1)}>Previous</button><span>{label} {position} of {info.page_count}</span><button type="button" disabled={loading || position >= info.page_count} onClick={() => setPosition(value => value + 1)}>Next</button>{location && <button type="button" disabled={loading || position === location.value} onClick={() => setPosition(location.value)}>Back to citation</button>}</div>}
    </div>
    {loading && <p role="status">Opening the original source…{location?.kind === 'slide' ? ' The first slide preview may take a moment.' : ''}</p>}
    {error && <p className="sw-error" role="alert">{error}</p>}
    {!error && url && <div className="aura-source-canvas">{documentView ? <img src={url} alt={`${citation.title}, ${label.toLowerCase()} ${position}`} /> : info?.kind === 'video_timestamp' ? <video src={url} controls preload="metadata" onLoadedMetadata={event => seek(event.currentTarget)} onError={() => setError('This browser could not play the recording. Download the original to view it.')} /> : <audio src={url} controls preload="metadata" onLoadedMetadata={event => seek(event.currentTarget)} onError={() => setError('This browser could not play the recording. Download the original to listen.')} />}</div>}
    <details className="aura-source-excerpt"><summary>Extracted supporting text</summary><p>{citation.excerpt || 'No extracted text is available.'}</p></details>
    {documentView && !loading && !error && url && <FigurePanel key={`${citation.source_id}:${position}`} sourceId={citation.source_id} position={position} />}
    {info?.kind === 'slide' && <small>Slide preview rendered from the original presentation; fonts or formatting may differ slightly.</small>}
  </dialog>
}
