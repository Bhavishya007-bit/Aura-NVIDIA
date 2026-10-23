/** Optional DOM regression suite. See docs/STUDY_PLAN_REDESIGN.md for test-only jsdom setup. */
import test, { after, beforeEach, afterEach } from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { mkdtemp, writeFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { MessageChannel as NodeMessageChannel } from 'node:worker_threads'
import { pathToFileURL } from 'node:url'
import { build, stop } from '../../node_modules/esbuild/lib/main.js'
const require = createRequire(import.meta.url)
const { JSDOM } = require(require.resolve('jsdom', { paths: [process.env.AURA_UI_TEST_MODULES || process.cwd()] }))
const scratch = await mkdtemp(`${tmpdir()}/aura-plan-dom-`)
const result = await build({ stdin: { contents: `export { createElement, act } from 'react'; export { createRoot } from 'react-dom/client'; export { default as AgentPanel } from './src/components/AgentPanel'; export { default as AccountMenu } from './src/components/AccountMenu'; export { default as StudyWorkspace } from './src/components/StudyWorkspace'; export { default as App } from './src/App';`, resolveDir: process.cwd(), loader: 'tsx' }, bundle: true, platform: 'node', format: 'esm', jsx: 'automatic', loader: { '.css': 'empty' }, define: { 'import.meta.env.VITE_API_BASE_URL': '"http://127.0.0.1:8000"', 'process.env.NODE_ENV': '"test"' }, write: false })
await writeFile(`${scratch}/components.mjs`, result.outputFiles[0].text)
// React inspects input-event support at import time. Give it a real DOM before loading.
const bootstrap = new JSDOM('<!doctype html><div></div>')
globalThis.window = bootstrap.window; globalThis.document = bootstrap.window.document
// Avoid Node MessagePorts keeping React's browser scheduler alive after tests.
const channels = []
globalThis.MessageChannel = class extends NodeMessageChannel { constructor() { super(); channels.push(this) } }
const { createElement: h, act, createRoot, AgentPanel, AccountMenu, StudyWorkspace, App } = await import(pathToFileURL(`${scratch}/components.mjs`))
let dom, root, requests, jobs, tasks, memories, enabled, materials, failLoads, generationUnavailable
const goal = 'Create a 3-day plan'
const baseRun = (overrides = {}) => ({ id: 'run-a', source_id: 7, state: 'completed', request: { skill: 'study_plan', goal }, tokens_used: 1200, created_at: '2026-10-23T08:00:00Z', started_at: '2026-10-23T08:00:01Z', updated_at: '2026-10-23T08:00:21Z', steps: [{ tool: 'document_search', state: 'completed', plan: ['RAW INTERNAL NARRATION'], observation: { passages: [{ reference: 'D9', slide: 18 }] } }], result: { text: 'Review the membrane.\n\nDay 1: Membrane proteins\nRead and recall.\nReferences: D9', references: ['D9'], verified: false, structured_plan: { overview: 'Review the membrane.', days: [{ day: 1, title: 'Membrane proteins', details: 'Read and recall.', references: ['D9'] }] }, task_ids: ['task-a'] }, ...overrides })
const tick = () => new Promise(resolve => setTimeout(resolve, 0))
const button = name => [...document.querySelectorAll('button')].find(b => b.textContent.trim() === name || b.textContent.trim().startsWith(name))
async function click(element) { assert(element, 'control exists'); await act(async () => { element.click(); await tick() }) }
async function input(element, value) {
  await act(async () => { Object.getOwnPropertyDescriptor(element.tagName === 'TEXTAREA' ? dom.window.HTMLTextAreaElement.prototype : element.tagName === 'SELECT' ? dom.window.HTMLSelectElement.prototype : dom.window.HTMLInputElement.prototype, 'value').set.call(element, value); element.dispatchEvent(new dom.window.Event(element.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true })); await tick() })
}
async function mount(component, props = {}) { await act(async () => { root.render(h(component, props)); await tick(); await tick() }) }
const props = (overrides = {}) => ({ courseId: '6', sourceId: '7', materialReady: true, storageKey: 'plan:test:learner:6', onOpenTool: () => {}, ...overrides })
const visibleText = () => { const copy = document.body.cloneNode(true); copy.querySelectorAll('details:not([open])').forEach(d => { const s = d.querySelector('summary'); d.replaceChildren(s) }); return copy.textContent }

beforeEach(() => {
  dom = new JSDOM('<!doctype html><div id="root"></div>', { url: 'http://localhost:5173/?view=study&tab=Agents&source=7', pretendToBeVisual: true })
  for (const name of ['window', 'document', 'HTMLElement', 'HTMLInputElement', 'HTMLTextAreaElement', 'Event', 'MouseEvent', 'localStorage', 'sessionStorage']) globalThis[name] = dom.window[name]
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: dom.window.navigator })
  window.matchMedia = () => ({ matches: true, addEventListener() {}, removeEventListener() {} })
  window.HTMLElement.prototype.scrollIntoView = () => {}
  window.HTMLDialogElement.prototype.showModal = function () { this.open = true }
  globalThis.requestAnimationFrame = callback => setTimeout(callback, 0)
  globalThis.IS_REACT_ACT_ENVIRONMENT = true
  root = createRoot(document.getElementById('root'))
  requests = []; jobs = []; tasks = []; memories = []; enabled = true; failLoads = false; generationUnavailable = false
  materials = [{ source_id: 7, source_name: 'Biological membranes.ppt', source_type: 'pptx', status: 'success' }]
  globalThis.fetch = async (url, options = {}) => {
    const u = new URL(url), method = options.method || 'GET', body = options.body ? JSON.parse(options.body) : undefined
    requests.push({ path: u.pathname, query: u.search, method, body })
    if (failLoads && method === 'GET' && u.pathname.startsWith('/agents/')) throw new Error('Internal database_status_code')
    let value
    if (u.pathname === '/auth/me') value = { student_id: 1, name: 'Sam Rivera', email: 'sam@example.test' }
    else if (u.pathname === '/courses') value = { courses: [{ course_id: 6, course_name: 'Biology' }] }
    else if (u.pathname === '/agents/runs' && method === 'GET') value = { items: jobs }
    else if (u.pathname === '/agents/runs' && method === 'POST') { value = baseRun({ id: 'run-new', state: 'queued', request: body, steps: [], result: null }); jobs.unshift(value) }
    else if (u.pathname.endsWith('/cancel')) { jobs[0].state = 'cancelled'; value = jobs[0] }
    else if (u.pathname === '/agents/tasks') value = { items: tasks }
    else if (u.pathname.startsWith('/agents/tasks/')) { const t = tasks.find(t => t.id === u.pathname.split('/').at(-1)); t.done = body.done; value = t }
    else if (u.pathname === '/agents/memory' && method === 'GET') value = { enabled, items: memories }
    else if (u.pathname === '/agents/memory/settings') { enabled = body.enabled; value = { enabled } }
    else if (u.pathname.endsWith('/delete')) { memories = memories.filter(m => m.id !== u.pathname.split('/').at(-2)); value = { deleted: true } }
    else if (u.pathname.startsWith('/agents/memory') && method === 'PATCH') { const m = memories.find(m => m.id === u.pathname.split('/').at(-1)); m.record = body; value = m }
    else if (u.pathname === '/agents/memory' && method === 'POST') { value = { id: 'memory-new', record: body, updated_at: '2026-10-23' }; memories.push(value) }
    else if (u.pathname === '/study/materials') value = { sources: materials }
    else if (u.pathname === '/study/tools' && generationUnavailable) return new Response(JSON.stringify({ detail: 'Ollama could not complete question generation or verification. Check that it is running and retry.' }), { status: 503, headers: { 'Content-Type': 'application/json' } })
    else if (u.pathname === '/study/artifacts') value = { artifacts: [] }
    else if (u.pathname === '/study/progress') value = { assessment_count: 0, question_count: 0, topics: [], recent_results: [] }
    else if (u.pathname === '/preparation-jobs') value = { jobs: [] }
    else throw new Error(`Unexpected test request: ${method} ${u.pathname}`)
    return new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } })
  }
})
afterEach(async () => { await act(async () => root.unmount()); dom.window.close() })
after(async () => { bootstrap.window.close(); channels.forEach(c => { c.port1.close(); c.port2.close() }); stop(); await rm(scratch, { recursive: true, force: true }) })

test('empty screen is goal-first and cannot start without selected ready material', async () => {
  await mount(AgentPanel, props({ sourceId: '', materialReady: false }))
  assert.equal(document.querySelectorAll('.plan-examples button').length, 3)
  assert.equal(document.querySelector('.plan-options').open, false)
  await click(button('3-day plan'))
  assert(button('Create my plan').disabled)
  assert.match(visibleText(), /Choose a material/)
  assert.equal(document.querySelectorAll('.plan-outcomes input[type=radio]').length, 2)
})
test('create action preserves the run POST contract and serializes options only inside goal', async () => {
  await mount(AgentPanel, props())
  await click(button('3-day plan'))
  const fields = document.querySelectorAll('.plan-option-fields input')
  await input(fields[0], '2'); await input(fields[1], '30')
  await click(button('Create my plan'))
  const start = requests.find(r => r.method === 'POST' && r.path === '/agents/runs')
  assert.deepEqual(Object.keys(start.body).sort(), ['course_id', 'source_id', 'goal', 'skill', 'allow_memory_write'].sort())
  assert.equal(start.body.source_id, 7)
  assert.match(start.body.goal, /2-day plan/)
  assert.match(start.body.goal, /30 minutes per day/)
  assert.match(visibleText(), /Getting ready to begin/)
  assert(document.querySelector('[aria-live=polite]'))
})
test('completed daily cards persist checks through the task API and preserve source/topic actions', async () => {
  jobs = [baseRun()]; tasks = [{ id: 'task-a', title: 'Day 1: Membrane proteins', details: 'Read and recall.', done: false }]
  const opened = []
  await mount(AgentPanel, props({ onOpenTool: (...args) => opened.push(args) }))
  assert.equal(document.querySelectorAll('.plan-day').length, 1)
  assert.match(visibleText(), /Slide 18/)
  assert(!visibleText().includes('RAW INTERNAL NARRATION'))
  assert.equal(document.querySelector('.plan-run-details').open, false)
  await click(document.querySelector('.plan-day-check input'))
  assert.equal(tasks[0].done, true)
  assert(requests.some(r => r.path === '/agents/tasks/task-a' && r.method === 'PATCH' && r.body.done === true && r.query === '?course_id=6'))
  await click(button('Review flashcards'))
  assert.deepEqual(opened[0], ['Flashcards', 'Membrane proteins', '7'])
  await click(button('Today'))
  assert(document.querySelector('.plan-task input').checked)
})
test('budget stops show saved partial work and two recovery choices without narration or raw error code', async () => {
  const finished = baseRun()
  jobs = [baseRun({ state: 'budget_exhausted', error_code: 'TOKEN_BUDGET_EXHAUSTED', result: null, steps: [...finished.steps, { tool: 'study_plan_create', state: 'completed', observation: { plan: finished.result.structured_plan, tasks: [{ id: 'task-a' }] } }] })]
  tasks = [{ id: 'task-a', title: 'Day 1: Membrane proteins', done: false }]
  await mount(AgentPanel, props())
  assert.match(visibleText(), /Stopped early. Here is what Aura found so far./)
  assert.equal(document.querySelectorAll('.plan-day').length, 1)
  assert(button('Try again')); assert(button('Make it simpler'))
  assert(!visibleText().includes('budget_exhausted')); assert(!visibleText().includes('RAW INTERNAL NARRATION')); assert(!visibleText().includes('TOKEN_BUDGET_EXHAUSTED'))
  await click(button('Make it simpler'))
  const body = requests.find(r => r.method === 'POST' && r.path === '/agents/runs').body
  assert.match(body.goal, /1-day/); assert.match(body.goal, /20 minutes/)
})
test('refresh reopens active runs; cancel retains completed step checkmarks', async () => {
  jobs = [baseRun({ state: 'running', result: null })]
  await mount(AgentPanel, props())
  assert.match(visibleText(), /Reading your slides/)
  assert.equal(document.querySelectorAll('.plan-progress li').length, 2)
  await act(async () => root.unmount()); root = createRoot(document.getElementById('root'))
  await mount(AgentPanel, props())
  assert.match(visibleText(), /Working on your plan/)
  await click(button('Cancel'))
  assert(requests.some(r => r.path === '/agents/runs/run-a/cancel' && r.method === 'POST'))
  assert(button('Start again'))
})
test('recent runs reopen and browser-local removal is honest and reversible', async () => {
  jobs = [baseRun(), baseRun({ id: 'run-b', request: { skill: 'research_brief', goal: 'Research proteins' } })]
  await mount(AgentPanel, props())
  await click([...document.querySelectorAll('.plan-recent-open')][1])
  assert.match(document.getElementById('plan-result-title').textContent, /research brief/)
  await click([...document.querySelectorAll('.plan-remove')][1])
  assert.match(visibleText(), /Removed from recent plans on this browser/)
  assert.equal(document.querySelectorAll('.plan-recent li').length, 1)
  assert(!requests.some(r => /delete/.test(r.path)))
  await click(button('Undo'))
  assert.equal(document.querySelectorAll('.plan-recent li').length, 2)
})
test('account menu hides student IDs, and memory settings edit/delete/toggle existing endpoints', async () => {
  memories = [{ id: 'memory-a', record: { kind: 'preference', text: 'I prefer examples', depth: 'beginner', examples: true }, updated_at: '2026-10-23' }]
  await mount(AccountMenu, { name: '24F20062@students.example.test', courseId: '6', demo: true })
  assert(!visibleText().includes('24F20062')); assert(!visibleText().includes('@students.example.test')); assert.match(visibleText(), /Learner/); assert.match(visibleText(), /Demo account/)
  await click(document.querySelector('.aura-account summary'))
  await click(button('What Aura remembers'))
  assert(document.querySelector('dialog').open)
  await click(button('Edit'))
  await input(document.querySelector('.aura-memory textarea'), 'I prefer diagrams')
  await click(button('Save changes'))
  assert(requests.some(r => r.path === '/agents/memory/memory-a' && r.method === 'PATCH' && r.body.text === 'I prefer diagrams'))
  await click(document.querySelector('.aura-memory input[role=switch]'))
  assert.equal(enabled, false)
  await click(button('Delete'))
  assert(requests.some(r => r.path === '/agents/memory/memory-a/delete' && r.method === 'POST'))
})
test('workspace keeps Agents identity but shows Study Plan, real extension and working Change focus', async () => {
  materials.push({ source_id: 8, source_name: 'Biology revision.pdf', source_type: 'pdf', status: 'success' })
  await mount(StudyWorkspace, { user: { id: '1', fullName: 'Sam Rivera', email: 'sam@example.test' }, courses: [{ id: '6', title: 'Biology' }], courseId: '6', coursesLoading: false, coursesError: '', theme: 'dark', onCourseChange() {}, onThemeChange() {}, onChatHome() {}, onSignOut() {}, signingOut: false, sessionNotice: '' })
  assert.equal(document.querySelector('h1').textContent, 'Study Plan')
  assert.match(document.querySelector('.sw-using').textContent, /Using: Biological membranes.ppt/)
  assert.equal(document.querySelector('.sw-material-select small').textContent, 'PPT')
  assert(!document.querySelector('.sw-heading .sw-eyebrow').textContent.includes('Biological membranes'))
  await click(button('Change'))
  assert.equal(document.activeElement, document.querySelector('.sw-material-search input'))
  await click(document.querySelectorAll('.sw-material-select')[1])
  assert.equal(new URL(window.location.href).searchParams.get('source'), '8')
  assert.match(document.querySelector('.sw-using').textContent, /Biology revision.pdf/)
})
test('source/topic deep links reach existing tools and retain focus after reload', async () => {
  window.history.replaceState(null, '', '/?view=study&tab=Flashcards&source=7&topic=Membrane%20proteins')
  await mount(StudyWorkspace, { user: { id: '1', fullName: 'Sam Rivera' }, courses: [], courseId: '6', coursesLoading: false, coursesError: '', theme: 'dark', onCourseChange() {}, onThemeChange() {}, onChatHome() {}, onSignOut() {}, signingOut: false, sessionNotice: '' })
  assert.equal(document.querySelector('h1').textContent, 'Flashcards')
  assert.equal(document.querySelector('.sw-focus input').value, 'Membrane proteins')
  assert(document.querySelector('.sw-material-row.is-selected'))
})
test('full app honors the prefilled study goal on a direct link', async () => {
  window.history.replaceState(null, '', '/?view=study&tab=Agents&source=7&goal=Prepare%20for%20my%20exam')
  sessionStorage.setItem('aura.authToken', 'synthetic-test-token')
  await mount(App)
  assert.equal(document.querySelector('h1').textContent, 'Study Plan')
  assert.equal(document.querySelector('#plan-goal').value, 'Prepare for my exam')
})
test('load errors use student-safe copy and permit retry', async () => {
  failLoads = true
  await mount(AgentPanel, props())
  assert.match(visibleText(), /could not be refreshed/)
  assert(!visibleText().includes('database_status_code'))
  failLoads = false
  await click(button('Retry'))
  assert(button('Create my plan'))
})

test('Chat study-goal chip opens Study Plan with the goal and attachment intact', async () => {
  window.history.replaceState(null, '', '/')
  sessionStorage.setItem('aura.authToken', 'synthetic-test-token')
  localStorage.setItem('aura.chat.v1:1:6', JSON.stringify({ entries: [{ message: { id: 'm1', role: 'student', content: 'Create a 3-day study plan for my exam' }, citations: [] }], uploadStage: 'ready', uploaded: { sourceId: '7', courseId: '6', filename: 'Biological membranes.ppt', fileType: 'ppt', processingStatus: 'success', contentUnitCount: 10 } }))
  await mount(App)
  await click(button('Turn this into a study plan'))
  assert.equal(document.querySelector('h1').textContent, 'Study Plan')
  assert.equal(document.querySelector('#plan-goal').value, 'Create a 3-day study plan for my exam')
  assert.equal(new URL(window.location.href).searchParams.get('source'), '7')
})
test('editing a prefilled goal survives leaving the page without restoring the original prefill', async () => {
  window.history.replaceState(null, '', '/?view=study&tab=Agents&source=7&goal=Original%20goal')
  sessionStorage.setItem('aura.authToken', 'synthetic-test-token')
  await mount(App)
  await input(document.querySelector('#plan-goal'), 'My revised goal')
  await click([...document.querySelectorAll('.sw-rail nav button')].find(b => b.textContent === 'Summary'))
  await click([...document.querySelectorAll('.sw-rail nav button')].find(b => b.textContent === 'Study Plan'))
  assert.equal(document.querySelector('#plan-goal').value, 'My revised goal')
})

test('generation failures do not expose stale provider advice and retain material/topic', async () => {
  generationUnavailable = true
  window.history.replaceState(null, '', '/?view=study&tab=Flashcards&source=7&topic=Membrane%20proteins')
  await mount(StudyWorkspace, { user: { id: '1', fullName: 'Sam Rivera' }, courses: [], courseId: '6', coursesLoading: false, coursesError: '', theme: 'dark', onCourseChange() {}, onThemeChange() {}, onChatHome() {}, onSignOut() {}, signingOut: false, sessionNotice: '' })
  await click(button('Generate'))
  assert.match(document.querySelector('[role=alert]').textContent, /could not create and verify/)
  assert(!visibleText().includes('Ollama'))
  assert.equal(document.querySelector('.sw-focus input').value, 'Membrane proteins')
  assert.match(document.querySelector('.sw-using').textContent, /Biological membranes.ppt/)
  assert(button('Generate').disabled === false)
})
