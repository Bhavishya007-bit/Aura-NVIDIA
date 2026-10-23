import { requestApi, requireRecord } from './apiClient'
export type RhythmSettings = { enabled: boolean; timezone: string; daily_hour: number }
export type Review = { source_id: number; topic_key: string; topic: string; due_at: string; source_name: string }
export type Digest = { id: string; local_date: string; created_at: string; payload: { title: string; takeaway: string; method: string; tasks: { id: string; title: string }[]; reviews: Review[] } }
export type Rhythm = { settings: RhythmSettings; reviews: Review[]; digests: Digest[]; notice: string }
const route = (course: string, suffix = '') => `study/rhythm${suffix}?course_id=${encodeURIComponent(course)}`
const json = (body: unknown) => ({ headers: { 'Content-Type':'application/json' }, body: JSON.stringify(body) })
const decode = (value: unknown) => {
  const data = requireRecord(value, 'study rhythm'), settings = requireRecord(data.settings, 'study rhythm settings')
  if (typeof settings.enabled !== 'boolean' || typeof settings.timezone !== 'string' || typeof settings.daily_hour !== 'number' || !Array.isArray(data.reviews) || !Array.isArray(data.digests)) throw new Error('Invalid study rhythm response.')
  return data as unknown as Rhythm
}
export const getRhythm = (course: string) => requestApi(route(course), { method:'GET' }, decode)
export const saveRhythm = (course: string, settings: RhythmSettings) => requestApi(route(course,'/settings'), { method:'PATCH', ...json(settings) }, decode)
export const refreshDigest = (course: string) => requestApi(route(course,'/refresh'), { method:'POST' }, decode)
export const snoozeReview = (course: string, review: Review) => requestApi(route(course,'/snooze'), { method:'POST', ...json({ source_id:review.source_id, topic_key:review.topic_key }) }, decode)
export type EvaluationStatus = { checked_at?: string; mode: string; checks: { category: string; passed: number; total: number }[]; calibration: { reviewed: number; required: number; agreement: number | null; false_absence_rate: number | null; ready: boolean; notice: string }; your_runs: Record<string,number>; limitations: string[] }
export const getEvaluationStatus = (course: string) => requestApi(`study/evaluation?course_id=${encodeURIComponent(course)}`, { method:'GET' }, value => requireRecord(value,'evaluation summary') as unknown as EvaluationStatus)
