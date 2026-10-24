import type { Citation } from '../types/study'
import type { ToolCitation } from './studyToolsApi'

export function citedNumbers(text: string): number[] {
  return [...new Set(Array.from(text.matchAll(/\[(\d+)\]|【(\d+)】/g), match => Number(match[1] ?? match[2])))].filter(value => value > 0)
}

export function groupToolCitations(ids: number[], citations: ToolCitation[]): ToolCitation[] {
  const groups = new Map<string, ToolCitation>()
  for (const id of [...new Set(ids)]) {
    const citation = citations.find(item => item.id === id)
    if (!citation) continue
    const known = /^(?:Image|Page [1-9]\d*|Slide [1-9]\d*|\d+:\d{2})$/.test(citation.location)
    const key = `${citation.source_id}:${known ? citation.location : `unknown-${id}`}`
    const previous = groups.get(key)
    if (!previous) groups.set(key, { ...citation, referenceIds: [id] })
    else {
      previous.referenceIds!.push(id)
      if (citation.excerpt && !previous.excerpt.includes(citation.excerpt)) previous.excerpt += `\n\n${citation.excerpt}`
    }
  }
  return [...groups.values()]
}

export function chatCitationGroups(text: string, citations: Citation[], title: (sourceId: string) => string): ToolCitation[] {
  const tools = citations.map((citation, index) => {
    const location = citation.location
    const number = citation.citationNumber ?? index + 1 // Preserve old saved chat entries.
    return { id: number, chunk_id: 0, source_id: Number(citation.sourceId), title: citation.sourceName || title(citation.sourceId), excerpt: citation.excerpt ?? '',
      location: location.kind === 'pdf_page' ? (/\.(png|jpe?g)$/i.test(title(citation.sourceId)) ? 'Image' : `Page ${location.page}`) : location.kind === 'slide' ? `Slide ${location.slide}` : `${Math.floor(location.seconds / 60)}:${String(Math.floor(location.seconds % 60)).padStart(2, '0')}`,
      page: location.kind === 'pdf_page' ? location.page : null,
      slide: location.kind === 'slide' ? location.slide : null,
      seconds: location.kind === 'video_timestamp' ? location.seconds : null,
    }
  })
  return groupToolCitations(citedNumbers(text), tools)
}

export function previewLocation(citation: ToolCitation): { kind: 'pdf_page' | 'slide' | 'timestamp'; value: number } | null {
  if (citation.slide && citation.slide > 0) return { kind: 'slide', value: citation.slide }
  if (citation.page && citation.page > 0) return { kind: 'pdf_page', value: citation.page }
  if (typeof citation.seconds === 'number' && Number.isFinite(citation.seconds) && citation.seconds >= 0) return { kind: 'timestamp', value: citation.seconds }
  const page = /^Page ([1-9]\d*)$/.exec(citation.location)
  const slide = /^Slide ([1-9]\d*)$/.exec(citation.location)
  const time = /^(\d+):(\d{2})$/.exec(citation.location)
  if (page) return { kind: 'pdf_page', value: Number(page[1]) }
  if (slide) return { kind: 'slide', value: Number(slide[1]) }
  if (time && Number(time[2]) < 60) return { kind: 'timestamp', value: Number(time[1]) * 60 + Number(time[2]) }
  return null
}

