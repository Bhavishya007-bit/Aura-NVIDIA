import { requestApi, requestApiBlob, requireRecord, ApiResponseError } from './apiClient'

export type ViewerInfo = { source_id: number; title: string; kind: 'image' | 'pdf_page' | 'slide' | 'video_timestamp' | 'audio_timestamp' | 'download'; page_count: number | null }
export async function getViewerInfo(sourceId: number): Promise<ViewerInfo> {
  return requestApi(`study/sources/${sourceId}/viewer`, { method: 'GET' }, value => {
    const row = requireRecord(value, 'source viewer')
    if (row.source_id !== sourceId || typeof row.title !== 'string' || !['image', 'pdf_page', 'slide', 'video_timestamp', 'audio_timestamp', 'download'].includes(String(row.kind)) || (row.page_count != null && (typeof row.page_count !== 'number' || !Number.isInteger(row.page_count) || row.page_count < 1))) throw new ApiResponseError('Invalid source preview metadata.')
    return row as unknown as ViewerInfo
  })
}
export function sourcePreview(sourceId: number, position: number, signal?: AbortSignal): Promise<Blob> {
  return requestApiBlob(`study/sources/${sourceId}/preview?position=${position}`, signal)
}
export function sourceMedia(sourceId: number, signal?: AbortSignal): Promise<Blob> {
  return requestApiBlob(`study/sources/${sourceId}/media`, signal)
}
export function originalSource(sourceId: number): Promise<Blob> {
  return requestApiBlob(`study/sources/${sourceId}/original`)
}

export type FigureExplanation = { source_id: number; position: number; answerable: boolean; observations: string[]; explanation: string; limitations: string[]; notice: string; verification: string }
export async function explainFigure(sourceId: number, position: number, question: string, signal?: AbortSignal): Promise<FigureExplanation> {
  return requestApi(`study/sources/${sourceId}/figure`, { method: 'POST', signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ position, question }) }, value => {
    const row = requireRecord(value, 'figure explanation')
    if (row.source_id !== sourceId || row.position !== position || typeof row.answerable !== 'boolean' || typeof row.explanation !== 'string' || typeof row.notice !== 'string' || !Array.isArray(row.observations) || !Array.isArray(row.limitations) || [...row.observations, ...row.limitations].some(text => typeof text !== 'string')) throw new ApiResponseError('Invalid figure explanation.')
    return row as unknown as FigureExplanation
  })
}
