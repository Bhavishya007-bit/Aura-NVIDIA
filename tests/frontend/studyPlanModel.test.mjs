import test from 'node:test'
import assert from 'node:assert/strict'
import { planContent, taskForDay, slideReferences, stateLabel, stepLabel, isActive, goalWithOptions, displayGoal, cleanDisplayName, fileType } from '../../src/components/studyPlanModel.ts'
const run = (overrides = {}) => ({ id: 'r1', state: 'completed', request: { skill: 'study_plan', goal: 'Study' }, tokens_used: 42, steps: [], ...overrides })

test('internal model narration never becomes a result or a stopped-run heading', () => {
  const stopped = run({ state: 'budget_exhausted', steps: [{ tool: 'document_search', state: 'completed', plan: ['Need gather evidence then invoke tool.'], observation: { passages: [{ text: 'Internal retrieved text' }] } }] })
  assert.deepEqual(planContent(stopped), { overview: '', days: [], markdown: '' })
  assert.equal(stateLabel(stopped.state), 'Stopped early')
  assert(!stateLabel(stopped.state).includes('_'))
})
test('structured daily plans retain their exact task IDs and returned markdown', () => {
  const value = run({ result: { text: 'The returned markdown with D1.', structured_plan: { overview: 'Ready for your exam.', days: [{ day: 1, title: 'Membranes', details: 'Review the lipid bilayer.', references: ['D1'] }] }, task_ids: ['task-a'] } })
  const plan = planContent(value)
  assert.equal(plan.days[0].taskId, 'task-a')
  assert.equal(plan.markdown, value.result.text)
  assert.equal(taskForDay(plan.days[0], [{ id: 'other', title: 'Day 1: Membranes' }, { id: 'task-a', title: 'Day 1: Membranes', done: true }]).done, true)
})
test('a saved partial plan is recoverable even when final result is absent', () => {
  const value = run({ state: 'cancelled', steps: [{ tool: 'study_plan_create', state: 'completed', observation: { plan: { overview: 'Partial plan', days: [{ day: 1, title: 'Review', details: 'Read your slides', references: ['D2'] }] }, tasks: [{ id: 'persisted-task' }] } }] })
  const plan = planContent(value)
  assert.equal(plan.days[0].taskId, 'persisted-task')
  assert.match(plan.markdown, /References: D2/)
})
test('uncommitted or rejected observations cannot create a fake checklist', () => {
  assert.equal(planContent(run({ steps: [{ tool: 'study_plan_create', state: 'failed', observation: { plan: { days: [{ day: 1, title: 'Bad', details: 'No', references: [] }] } } }] })).days.length, 0)
})
test('legacy markdown day headings become cards without borrowing tasks from another run', () => {
  const value = run({ result: { text: 'A clear goal.\n\n## Day 1: Membranes\n- Read slides\nReferences: D1\n\n**Day 2: Recall**\nQuiz yourself.' } })
  const plan = planContent(value)
  assert.equal(plan.overview, 'A clear goal.')
  assert.equal(plan.days.length, 2)
  assert.equal(plan.days[1].title, 'Recall')
  assert.deepEqual(plan.days[0].references, ['D1'])
  assert.equal(taskForDay(plan.days[0], [{ id: 'old', title: 'Day 1: Membranes' }]), undefined)
})
test('research markdown without day headings remains a complete brief', () => {
  const markdown = '# Membranes\n\nA research brief with **evidence**.'
  assert.deepEqual(planContent(run({ result: { text: markdown } })), { overview: markdown, days: [], markdown })
})
test('slide chips use only explicit retrieved slide metadata for cited references', () => {
  const value = run({ steps: [{ tool: 'document_search', state: 'completed', observation: { passages: [{ reference: 'D1', slide: 18 }, { reference: 'D2', page: 9 }, { reference: 'D3', slide: 0 }, { reference: 'D4', slide: 20 }] } }] })
  assert.deepEqual(slideReferences(value, ['D1', 'D2', 'D3']), [{ reference: 'D1', slide: 18 }])
})
test('friendly state mappings cover all persisted server states', () => {
  for (const state of ['queued', 'running', 'completed', 'budget_exhausted', 'failed', 'cancelled', 'timed_out', 'interrupted']) assert(!stateLabel(state).includes('_'))
  assert(isActive(run({ state: 'running' })))
  assert(isActive(run({ state: 'queued' })))
  assert(!isActive(run({ state: 'cancelled' })))
  assert.equal(stepLabel('document_search'), 'Reading your slides')
  assert.equal(stepLabel('memory_read'), 'Checking what you’ve studied')
  assert.equal(stepLabel('web_search'), 'Looking up sources')
  assert.equal(stepLabel('study_plan_create'), 'Building your plan')
  assert.equal(stepLabel('verification'), 'Checking the plan')
  assert.equal(stepLabel('internal_new_tool'), 'Working on your plan')
})
test('options use the existing goal string and avoid conflicting day counts', () => {
  const output = goalWithOptions('Create a three-day plan', { days: '1', minutes: '20', depth: 'quick' })
  assert(!output.includes('three-day'))
  assert.match(output, /Create a 1-day plan/)
  assert.match(output, /20 minutes per day/)
  assert.equal(displayGoal(output), 'Create a 1-day plan')
})
test('account labels hide IDs and file badges use the actual extension', () => {
  for (const name of ['1234567', 'Student 1234567', 'HN116WS', '22BCE1166', '24F20062...', '24F20062…', '24F20062@students.example.test', '24F20062 Account', '']) assert.equal(cleanDisplayName(name), 'Learner')
  assert.equal(cleanDisplayName('Sam Rivera'), 'Sam Rivera')
  assert.equal(fileType('Biological membranes.ppt', 'PPTX'), 'PPT')
  assert.equal(fileType('lecture.PpTx', '.ppt'), 'PPTX')
})
test('secondary text and accent design tokens meet at least 4.5:1 in both themes', () => {
  const luminance = hex => hex.match(/[a-f\d]{2}/gi).map(s => parseInt(s, 16) / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4).reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0)
  const contrast = (a, b) => (Math.max(luminance(a), luminance(b)) + .05) / (Math.min(luminance(a), luminance(b)) + .05)
  for (const [text, surfaces] of [['#bdc3bc', ['#252a28', '#1e2221', '#3c3027', '#191d1c']], ['#f3b184', ['#252a28', '#1e2221', '#3c3027']], ['#62665f', ['#fffefa', '#f7f6f2', '#f6e6d9']], ['#a34b24', ['#fffefa', '#f7f6f2', '#f6e6d9']], ['#2c1b10', ['#efac7e']]]) for (const surface of surfaces) assert(contrast(text, surface) >= 4.5, `${text} on ${surface}`)
})
