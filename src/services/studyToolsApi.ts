import { requestApi, requireRecord, ApiResponseError } from './apiClient'

export type ToolKind = 'notes' | 'summary' | 'flashcards' | 'assessment'
export type Material = { id: string; title: string; type: string; status: string; archived?: boolean }
export type ToolCitation = { id: number; chunk_id: number; source_id: number; title: string; location: string; excerpt: string }
export type ToolItem = {
  id: string; title?: string; text?: string; question?: string; answer?: string
  prompt?: string; kind?: 'mcq' | 'short_answer'; topic?: string; difficulty?: string
  choices?: Array<{ id: string; text: string }>; citation_ids: number[]
}
export type AssessmentFeedback = { question_id: string; prompt: string; correct: boolean; submitted_answer: string; expected_answer: string; explanation: string; topic: string; citation_ids: number[] }
export type TopicPerformance = { topic: string; score: number; correct: number; total: number }
export type AssessmentReport = { score: number; question_count: number; correct_count: number; feedback: AssessmentFeedback[]; topics: TopicPerformance[]; recommended_action: string; completed_at?: string }
export type Artifact = { id: string; kind: ToolKind; created_at: string; result: AssessmentReport | null; payload: { source_id: number; course_id: number; source_title: string; focus: string; items: ToolItem[]; citations: ToolCitation[]; coverage: { selected_passages: number; available_passages: number }; fulfillment?: { requested: number; created: number; partial: boolean }; notice?: string } }
export type ScorePoint = { score: number; question_count: number; correct_count: number; completed_at?: string | null }
export type PracticeProgress = { correct_count?: number; score_history?: ScorePoint[]; assessment_count: number; question_count: number; topics: TopicPerformance[]; recent_results: AssessmentReport[] }

function invalid(resource: string): never { throw new ApiResponseError(`Aura returned an invalid ${resource} response.`) }
function artifact(value: unknown): Artifact {
  const data = requireRecord(value, 'study tool')
  const payload = requireRecord(data.payload, 'study tool content')
  if (typeof data.id !== 'string' || !['notes', 'summary', 'flashcards', 'assessment'].includes(String(data.kind)) ||
      typeof data.created_at !== 'string' || !Array.isArray(payload.items) || !Array.isArray(payload.citations) ||
      typeof payload.source_title !== 'string' || typeof payload.source_id !== 'number') invalid('study tool')
  for (const value of payload.items) {
    const item = requireRecord(value, 'study item')
    if (typeof item.id !== 'string' || !Array.isArray(item.citation_ids) || item.citation_ids.some(id => typeof id !== 'number')) invalid('study item')
  }
  for (const value of payload.citations) {
    const citation = requireRecord(value, 'citation')
    if (typeof citation.id !== 'number' || typeof citation.excerpt !== 'string' || typeof citation.location !== 'string') invalid('citation')
  }
  if (data.result != null) report(data.result)
  return data as unknown as Artifact
}
function report(value: unknown): AssessmentReport {
  const data = requireRecord(value, 'assessment report')
  if (typeof data.score !== 'number' || !Array.isArray(data.feedback) || !Array.isArray(data.topics) || typeof data.recommended_action !== 'string') invalid('assessment report')
  return data as unknown as AssessmentReport
}
export async function listMaterials(courseId: string): Promise<Material[]> {
  return requestApi(`study/materials?course_id=${encodeURIComponent(courseId)}`, { method: 'GET' }, value => {
    const data = requireRecord(value, 'materials')
    if (!Array.isArray(data.sources)) invalid('materials')
    return data.sources.map(value => {
      const source = requireRecord(value, 'material')
      if (typeof source.source_id !== 'number' || typeof source.source_name !== 'string' || typeof source.source_type !== 'string') invalid('material')
      return { id: String(source.source_id), title: source.source_name, type: source.source_type, status: String(source.status ?? ''), archived: source.archived === true }
    })
  })
}
export async function listArtifacts(courseId: string, sourceId: string): Promise<Artifact[]> {
  return requestApi(`study/artifacts?course_id=${encodeURIComponent(courseId)}&source_id=${encodeURIComponent(sourceId)}`, { method: 'GET' }, value => {
    const data = requireRecord(value, 'saved study tools')
    if (!Array.isArray(data.artifacts)) invalid('saved study tools')
    return data.artifacts.map(artifact)
  })
}
export async function generateTool(courseId: string, sourceId: string, kind: ToolKind, settings: { count: number; focus: string; difficulty: string; questionType: string }): Promise<Artifact> {
  return requestApi('study/tools', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ course_id: Number(courseId), source_id: Number(sourceId), kind, count: settings.count, focus: settings.focus, difficulty: settings.difficulty, question_type: settings.questionType }) }, artifact)
}
export async function submitAssessment(id: string, answers: Record<string, string>): Promise<AssessmentReport> {
  return requestApi(`study/assessments/${encodeURIComponent(id)}/submit`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ answers: Object.entries(answers).map(([question_id, answer]) => ({ question_id, answer })) }) }, report)
}
export async function getPracticeProgress(courseId: string): Promise<PracticeProgress> {
  return requestApi(`study/progress?course_id=${encodeURIComponent(courseId)}`, { method: 'GET' }, value => {
    const data = requireRecord(value, 'practice progress')
    if (typeof data.assessment_count !== 'number' || typeof data.question_count !== 'number' || !Array.isArray(data.topics) || !Array.isArray(data.recent_results)) invalid('practice progress')
    return data as unknown as PracticeProgress
  })
}

export async function setMaterialArchived(courseId: string, sourceId: string, archived: boolean): Promise<void> {
  await requestApi(`study/materials/${encodeURIComponent(sourceId)}/visibility`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ course_id: Number(courseId), archived }),
  }, value => {
    const data = requireRecord(value, 'material visibility')
    if (data.source_id !== Number(sourceId) || data.archived !== archived) invalid('material visibility')
  })
}
