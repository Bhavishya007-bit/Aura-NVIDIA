import { requestApi, requireRecord, ApiResponseError } from './apiClient'

export type MemoryKind = 'preference' | 'decision' | 'event' | 'task_progress' | 'learner_fact'
export type MemoryInput = { kind: MemoryKind; text: string; depth: 'beginner' | 'standard' | 'advanced' | null; examples: boolean | null }
export type MemoryItem = { id: string; record: MemoryInput; updated_at: string }
export type Task = { id: string; title: string; details: string; done: boolean }
export type StructuredPlan = { overview: string; days: { day: number; title: string; details: string; references: string[] }[] }
export type ResearchSection = { kind: 'material' | 'web'; text: string; references: string[] }
export type ResearchSource = { reference: string; kind: 'material' | 'web'; title: string; url?: string; slide?: number | null; page?: number | null; retrieved_at?: string }
export type AgentCapabilities = { web_search: boolean }
export type AgentRun = { id: string; state: string; request: { goal: string; skill: string }; source_id?: number | null; created_at?: string; started_at?: string | null; updated_at?: string; tokens_used: number; error_code?: string; steps: { tool: string; state: string; plan?: string[]; observation?: unknown; error_code?: string }[]; result?: { text: string; references: string[]; verified: boolean; structured_plan?: StructuredPlan; task_ids?: string[]; research_sections?: ResearchSection[]; sources?: ResearchSource[]; limitations?: string[]; web_status?: 'searched' | 'no_results' | 'unavailable' | 'not_configured' } }
export type MemoryState = { enabled: boolean; items: MemoryItem[] }
const decode = (value: unknown) => requireRecord(value, 'agent')
const json = (body: unknown) => ({ headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
const query = (course: string) => `?course_id=${encodeURIComponent(course)}`
function items<T>(value: unknown): T[] {
  const data = decode(value)
  if (!Array.isArray(data.items)) throw new ApiResponseError('Invalid agent list.')
  return data.items as T[]
}
export function getMemories(course: string): Promise<MemoryState> {
  return requestApi(`agents/memory${query(course)}`, { method: 'GET' }, value => {
    const data = decode(value)
    if (typeof data.enabled !== 'boolean' || !Array.isArray(data.items)) throw new ApiResponseError('Invalid memory response.')
    return data as unknown as MemoryState
  })
}
export function saveMemory(course: string, record: MemoryInput, id?: string) {
  return requestApi(`agents/memory${id ? `/${encodeURIComponent(id)}` : ''}${query(course)}`, { method: id ? 'PATCH' : 'POST', ...json(record) }, decode)
}
export function deleteMemory(course: string, id: string) {
  return requestApi(`agents/memory/${encodeURIComponent(id)}/delete${query(course)}`, { method: 'POST' }, decode)
}
export function toggleMemory(course: string, enabled: boolean) {
  return requestApi(`agents/memory/settings${query(course)}`, { method: 'PATCH', ...json({ enabled }) }, decode)
}
export function getTasks(course: string): Promise<Task[]> {
  return requestApi(`agents/tasks${query(course)}`, { method: 'GET' }, items<Task>)
}
export function updateTask(course: string, id: string, done: boolean) {
  return requestApi(`agents/tasks/${encodeURIComponent(id)}${query(course)}`, { method: 'PATCH', ...json({ done }) }, decode)
}
export function getAgentRuns(course: string): Promise<AgentRun[]> {
  return requestApi(`agents/runs${query(course)}`, { method: 'GET' }, items<AgentRun>)
}
export function startAgent(course: string, source: string, goal: string, skill: string, allowMemoryWrite: boolean) {
  return requestApi('agents/runs', { method: 'POST', ...json({ course_id: Number(course), source_id: source ? Number(source) : null, goal, skill, allow_memory_write: allowMemoryWrite }) }, decode)
}
export function cancelAgent(course: string, id: string) {
  return requestApi(`agents/runs/${encodeURIComponent(id)}/cancel${query(course)}`, { method: 'POST' }, decode)
}

export function getAgentCapabilities(): Promise<AgentCapabilities> {
  return requestApi('agents/capabilities', { method: 'GET' }, value => {
    const data = decode(value)
    if (typeof data.web_search !== 'boolean') throw new ApiResponseError('Invalid search capabilities.')
    return { web_search: data.web_search }
  })
}
