import type { AgentRun, Task } from '../services/agentApi'

export type PlanDay = { day: number; title: string; details: string; references: string[]; taskId?: string }
export type PlanContent = { overview: string; days: PlanDay[]; markdown: string }
export const isActive = (run?: AgentRun) => !!run && ['queued', 'running'].includes(run.state)
export function stateLabel(state: string): string {
  return ({ completed: 'Done', budget_exhausted: 'Stopped early', failed: 'Something went wrong', cancelled: 'Cancelled', queued: 'Getting ready', running: 'In progress', timed_out: 'Stopped early', interrupted: 'Stopped early' } as Record<string, string>)[state] ?? 'Unavailable'
}
export function stepLabel(tool: string): string {
  return ({ code_execute: 'Running your Python code', document_search: 'Reading your slides', memory_read: "Checking what you’ve studied", web_search: 'Looking up sources', study_plan_create: 'Building your plan', assessment_create: 'Creating your quiz', task_create: 'Saving your study checklist', task_list: 'Checking your study checklist', memory_write: 'Remembering your preferences', verification: 'Checking the plan', verify: 'Checking the plan', finish: 'Putting it all together' } as Record<string, string>)[tool] ?? 'Working on your plan'
}
const record = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
const strings = (value: unknown): string[] => Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : []
export function planContent(run: AgentRun): PlanContent {
  // Only explicit result fields and saved plan observations are content. Never render steps[].plan.
  const saved = [...run.steps].reverse().find(s => s.tool === 'study_plan_create' && s.state === 'completed')
  const observation = record(saved?.observation)
  const structured = record(run.result?.structured_plan ?? observation.plan)
  const taskIds = run.result?.task_ids ?? (Array.isArray(observation.tasks) ? observation.tasks.map(t => String(record(t).id ?? '')) : [])
  if (Array.isArray(structured.days)) {
    const days = structured.days.flatMap((value, index): PlanDay[] => {
      const d = record(value)
      return typeof d.day === 'number' && typeof d.title === 'string' && typeof d.details === 'string'
        ? [{ day: d.day, title: d.title, details: d.details, references: strings(d.references), taskId: taskIds[index] }] : []
    })
    const overview = typeof structured.overview === 'string' ? structured.overview : ''
    return { overview, days, markdown: run.result?.text || [overview, ...days.map(d => `## Day ${d.day}: ${d.title}\n\n${d.details}${d.references.length ? '\n\nReferences: ' + d.references.join(', ') : ''}`)].join('\n\n') }
  }
  const markdown = typeof run.result?.text === 'string' ? run.result.text : ''
  const lines = markdown.split('\n'), days: PlanDay[] = [], intro: string[] = []
  for (const line of lines) {
    const heading = line.match(/^\s*(?:#{1,6}\s*)?(?:\*\*)?Day\s+(\d+)\b\s*(?:[:–—-]\s*)?(.*?)(?:\*\*)?\s*$/i)
    if (heading) days.push({ day: Number(heading[1]), title: heading[2] || 'Study and review', details: '', references: [] })
    else if (days.length) {
      const refs = line.match(/^\s*References:\s*(.*)/i)
      if (refs) days.at(-1)!.references.push(...(refs[1].match(/D\d+/g) ?? []))
      else days.at(-1)!.details += `${line}\n`
    } else intro.push(line)
  }
  return { overview: days.length ? intro.join('\n').trim() : markdown, days, markdown }
}
export function taskForDay(day: PlanDay, tasks: Task[]): Task | undefined {
  // Legacy markdown has no task IDs; never match similarly named tasks from another run.
  return day.taskId ? tasks.find(t => t.id === day.taskId) : undefined
}
export function slideReferences(run: AgentRun, refs: string[]): { reference: string; slide: number }[] {
  const found = new Map<string, number>()
  for (const step of run.steps) {
    if (step.tool !== 'document_search') continue
    const passages = record(step.observation).passages
    if (!Array.isArray(passages)) continue
    for (const value of passages) {
      const p = record(value)
      if (typeof p.reference === 'string' && typeof p.slide === 'number' && p.slide > 0 && refs.includes(p.reference)) found.set(p.reference, p.slide)
    }
  }
  return [...found].map(([reference, slide]) => ({ reference, slide }))
}
export function fileType(title: string, type: string): string {
  const extension = title.match(/\.([a-z0-9]{1,8})$/i)?.[1]
  return (extension ?? type.replace(/^\./, '')).toUpperCase()
}
export type PlanOptions = { days: string; minutes: string; depth: 'quick' | 'standard' | 'deep' }
export function goalWithOptions(goal: string, options: PlanOptions): string {
  // These are natural-language constraints in the existing goal field, not new payload fields.
  const main = options.days ? goal.replace(/\b(?:\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen)\s*[-–]?\s*days?\b/gi, `${options.days}-day`) : goal
  return [main.trim(), '\nStudy preferences:', options.days && `Create a ${options.days}-day plan.`, options.minutes && `Available study time: ${options.minutes} minutes per day.`, `Explanation depth: ${options.depth}.`].filter(Boolean).join('\n')
}
export const displayGoal = (goal: string) => goal.split('\nStudy preferences:')[0].trim()
export function cleanDisplayName(name: string): string {
  const trimmed = name.trim()
  // Auth names can contain an institutional email or an ID followed by extra text.
  // Never derive or guess a person's name from their account identifier.
  const firstToken = trimmed.split(/[\s@]/, 1)[0].replace(/[.…]+$/, '')
  const identifier = /^(?=.*[a-z])(?=.*\d)[a-z\d_-]{6,}$/i.test(firstToken)
  return !trimmed || trimmed.includes('@') || /^(?:student[\s:_-]*)?\d+$/i.test(trimmed) || identifier ? 'Learner' : trimmed
}

export function savedAssessment(run: AgentRun) {
  if (run.result?.assessment) return run.result.assessment
  // A saved artifact checkpoint is safe content; model planning text is never a result.
  const saved = [...run.steps].reverse().find(step => step.tool === 'assessment_create' && step.state === 'completed')
  const value = record(saved?.observation)
  return typeof value.artifact_id === 'string' && typeof value.title === 'string' && typeof value.question_count === 'number'
    ? { artifact_id: value.artifact_id, title: value.title, question_count: value.question_count, difficulty: String(value.difficulty ?? ''), focus: String(value.focus ?? ''), verification: 'model_checked' as const } : undefined
}
