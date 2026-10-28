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
const result = await build({ stdin: { contents: `export { createElement, act } from 'react'; export { default as StudyToolV2 } from './src/components/StudyToolV2'; export { default as ProgressV2 } from './src/components/ProgressV2'; export { default as TodayV2 } from './src/components/TodayV2'; export { default as PreviousPlansV2 } from './src/components/PreviousPlansV2'; export { createRoot } from 'react-dom/client'; export { default as AgentPanel } from './src/components/AgentPanel'; export { default as AccountMenu } from './src/components/AccountMenu'; export { default as StudyWorkspace } from './src/components/StudyWorkspace'; export { default as App } from './src/App'; export { default as TeachingText } from './src/components/TeachingText'; export { default as TutorReply } from './src/components/TutorReply'; export { default as StudyRhythm } from './src/components/StudyRhythm'; export { default as EvaluationSummary } from './src/components/EvaluationSummary'; export { default as ChatHome } from './src/components/ChatHome';`, resolveDir: process.cwd(), loader: 'tsx' }, bundle: true, platform: 'node', format: 'esm', jsx: 'automatic', loader: { '.css': 'empty' }, define: { 'import.meta.env.VITE_API_BASE_URL': '"http://127.0.0.1:8000"', 'process.env.NODE_ENV': '"test"' }, write: false })
await writeFile(`${scratch}/components.mjs`, result.outputFiles[0].text)
// React inspects input-event support at import time. Give it a real DOM before loading.
const bootstrap = new JSDOM('<!doctype html><div></div>')
globalThis.window = bootstrap.window; globalThis.document = bootstrap.window.document
// Avoid Node MessagePorts keeping React's browser scheduler alive after tests.
const channels = []
globalThis.MessageChannel = class extends NodeMessageChannel { constructor() { super(); channels.push(this) } }
const { createElement: h, act, createRoot, AgentPanel, AccountMenu, StudyWorkspace, App, TeachingText, TutorReply, StudyRhythm, EvaluationSummary, ChatHome, StudyToolV2, ProgressV2, TodayV2, PreviousPlansV2 } = await import(pathToFileURL(`${scratch}/components.mjs`))
let dom, root, requests, jobs, tasks, memories, enabled, materials, failLoads, generationUnavailable, webAvailable, assessmentAvailable, codeAvailable, savedArtifacts, rhythm, rhythmUnavailable, preparationJobs, failedImageFiles, chatReply, holdImagePreparation, legacyImageReply
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
const visibleText = () => { const copy = document.body.cloneNode(true); copy.querySelectorAll('[hidden]').forEach(d => d.remove()); copy.querySelectorAll('details:not([open])').forEach(d => { const s = d.querySelector('summary'); d.replaceChildren(s) }); return copy.textContent }
const homeProps=()=>({courseId:'6',courses:[],coursesLoading:false,coursesError:'',studentName:'Sam Rivera',workspaceKey:'1',onCourseChange(){},onOpenWorkspace(){}})
async function attachScreenshots(names) {
  await click(document.querySelector('[aria-label="Add study material"]'))
  const picker=document.querySelector('#aura-file')
  Object.defineProperty(picker,'files',{configurable:true,value:names.map(name=>new File(['authored image bytes'],name,{type:'image/png'}))})
  await act(async()=>{picker.dispatchEvent(new Event('change',{bubbles:true}));await tick();await tick();await tick()})
}

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
  requests = []; jobs = []; tasks = []; memories = []; enabled = true; failLoads = false; generationUnavailable = false; webAvailable = true; assessmentAvailable = true; codeAvailable = true; savedArtifacts = []
  rhythm = { settings: { enabled: false, timezone: 'UTC', daily_hour: 9 }, reviews: [], digests: [], notice: 'In-app only.' }; rhythmUnavailable = false
  preparationJobs=[];failedImageFiles=new Set();holdImagePreparation=false;legacyImageReply=false;chatReply={answer:'A joint explanation.',sources:[],citation_validation:{valid:false,stage:'visual_interpretation'}}
  materials = [{ source_id: 7, source_name: 'Biological membranes.ppt', source_type: 'pptx', status: 'success' }]
  globalThis.fetch = async (url, options = {}) => {
    const u = new URL(url), method = options.method || 'GET', body = typeof options.body === 'string' ? JSON.parse(options.body) : options.body
    requests.push({ path: u.pathname, query: u.search, method, body })
    if (failLoads && method === 'GET' && u.pathname.startsWith('/agents/')) throw new Error('Internal database_status_code')
    let value
    if (u.pathname.startsWith('/study/rhythm')) {
      if(rhythmUnavailable) throw new Error('Private failure detail')
      if(u.pathname.endsWith('/settings')) rhythm.settings = body
      if(u.pathname.endsWith('/refresh') && !rhythm.digests.length) rhythm.digests = [{id:'digest-a',local_date:'2026-10-23',created_at:'2026-10-23T09:00:00Z',payload:{title:'Your next study session',takeaway:'Review one topic.',tasks:[],reviews:[],method:'Graded practice.'}}]
      if(u.pathname.endsWith('/snooze')) rhythm.reviews = rhythm.reviews.filter(r=>r.source_id!==body.source_id || r.topic_key!==body.topic_key)
      value = rhythm
    }
    else if(u.pathname==='/study/evaluation') value={ mode:'controlled_offline',checked_at:'2026-10-23T09:00:00Z',checks:[{category:'agent_tasks',passed:10,total:10},{category:'injection_boundaries',passed:10,total:10},{category:'provenance',passed:2,total:2}],calibration:{reviewed:0,required:30,agreement:null,false_absence_rate:null,ready:false,notice:'Do not trust an LLM judge yet: collect 30 live outputs and have a person label them.'},your_runs:{completed:2,failed:1},limitations:[] }
    else if (u.pathname === '/auth/me') value = { student_id: 1, name: 'Sam Rivera', email: 'sam@example.test' }
    else if (u.pathname === '/courses') value = { courses: [{ course_id: 6, course_name: 'Biology' }] }
    else if (u.pathname === '/agents/capabilities') value = { web_search: webAvailable, assessment_agent: assessmentAvailable, code_execution: codeAvailable, code_backend: codeAvailable ? 'docker' : null }
    else if (u.pathname.includes('/artifacts/') && u.pathname.startsWith('/agents/runs/')) return new Response('value\n4\n', { headers: { 'Content-Type': 'text/csv' } })
    else if (u.pathname === '/agents/runs' && method === 'GET') value = { items: jobs }
    else if (u.pathname === '/agents/runs' && method === 'POST') { value = baseRun({ id: `run-new-${jobs.length}`, state: 'queued', request: body, steps: [], result: null }); jobs.unshift(value) }
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
    else if (u.pathname === '/study/artifacts') value = { artifacts: savedArtifacts.filter(item => String(item.payload.source_id) === u.searchParams.get('source_id')) }
    else if (u.pathname === '/study/learning') value = { model: 'fixture', topics: [], diagnostic_recommended: true, notice: 'Controlled learning profile.' }
    else if (u.pathname === '/study/progress') value = { assessment_count: 0, question_count: 0, topics: [], recent_results: [] }
    else if (u.pathname === '/preparation-jobs') value = { jobs: [...preparationJobs].reverse() }
    else if (u.pathname === '/courses/6/preparation-jobs' && method === 'POST') {
      const file=body.get('file')
      if(failedImageFiles.has(file.name)) return new Response(JSON.stringify({detail:'Synthetic upload failure'}),{status:503,headers:{'Content-Type':'application/json'}})
      const source=7+preparationJobs.length
      value={id:`prepare-${source}`,course_id:6,source_id:source,filename:file.name,state:'ready',stage:'ready',percentage:100,
        result:{source_id:source,course_id:6,source_name:file.name,source_type:'image',status:'success',content_units:1,warnings:[]},error:null}
      if(holdImagePreparation) value={...value,source_id:null,state:'queued',stage:'queued',percentage:null,result:null}
      preparationJobs.push(value)
    }
    else if (u.pathname === '/chat' && method === 'POST') value={...chatReply,sources:body.source_ids?.length>1 ? (legacyImageReply?body.source_ids.slice(0,1):body.source_ids).map(id=>({source_id:id,chunk_id:`original-image-${id}`,source_name:`authored-${id}.png`,page:1,content:'Visible authored evidence.'})) : chatReply.sources}
    else throw new Error(`Unexpected test request: ${method} ${u.pathname}`)
    return new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } })
  }
})
afterEach(async () => { await act(async () => root.unmount()); dom.window.close() })
after(async () => { bootstrap.window.close(); channels.forEach(c => { c.port1.close(); c.port2.close() }); stop(); await rm(scratch, { recursive: true, force: true }) })

test('sequential screenshot uploads retain the first image and pasted question in one request', async()=>{
  await mount(ChatHome,homeProps())
  await input(document.querySelector('#aura-question'),'Which department satisfies this SQL condition?')
  await attachScreenshots(['first-table.png'])
  await attachScreenshots(['second-table.png'])
  assert.equal(document.querySelectorAll('.aura-home__image-attachments .aura-home__attachment').length,2)
  assert.equal(document.querySelector('#aura-question').value,'Which department satisfies this SQL condition?')
  assert.deepEqual([...document.querySelectorAll('.aura-home__image-attachments strong')].map(e=>e.textContent),['Image 1: first-table.png','Image 2: second-table.png'])
  await click(document.querySelector('[aria-label="Send question"]'))
  const sent=requests.find(r=>r.path==='/chat'&&r.method==='POST').body
  assert.deepEqual(sent.source_ids,[7,8]);assert.equal(sent.source_id,7)
  assert.equal(sent.question,'Which department satisfies this SQL condition?')
  assert.equal(document.querySelectorAll('.aura-home__sent-images li').length,2)
})
test('batch screenshot completion preserves selection order and survives reopening Chat',async()=>{
  await mount(ChatHome,homeProps());await input(document.querySelector('#aura-question'),'Compare these tables')
  await attachScreenshots(['table-a.png','table-b.png'])
  const before=requests.filter(r=>r.path.endsWith('/preparation-jobs')&&r.method==='POST').length
  await act(async()=>{root.render(null);await tick()})
  await mount(ChatHome,homeProps())
  assert.equal(document.querySelector('#aura-question').value,'Compare these tables')
  assert.equal(document.querySelectorAll('.aura-home__image-attachments .aura-home__attachment').length,2)
  assert.equal(requests.filter(r=>r.path.endsWith('/preparation-jobs')&&r.method==='POST').length,before)
  await click(document.querySelector('[aria-label="Send question"]'))
  assert.deepEqual(requests.find(r=>r.path==='/chat').body.source_ids,[7,8])
})
test('failed second screenshot does not erase the first and can be removed individually',async()=>{
  await mount(ChatHome,homeProps());await input(document.querySelector('#aura-question'),'Read both tables')
  await attachScreenshots(['table.png']);failedImageFiles.add('failed.png')
  await attachScreenshots(['failed.png'])
  assert.equal(document.querySelectorAll('.aura-home__image-attachments .aura-home__attachment').length,2)
  assert(document.querySelector('[aria-label="Send question"]').disabled)
  await click(document.querySelector('[aria-label="Remove failed.png"]'))
  assert.equal(document.querySelectorAll('.aura-home__image-attachments .aura-home__attachment').length,1)
  await click(document.querySelector('[aria-label="Send question"]'))
  const sent=requests.find(r=>r.path==='/chat').body
  assert.equal(sent.source_id,7);assert.equal(sent.source_ids,undefined)
})
test('retrying a failed first upload keeps screenshot order without duplicate attachments',async()=>{
  failedImageFiles.add('first.png');await mount(ChatHome,homeProps())
  await input(document.querySelector('#aura-question'),'Compare both images')
  await attachScreenshots(['first.png','second.png'])
  failedImageFiles.delete('first.png');await click(button('Retry failed uploads only'))
  await act(async()=>{await tick();await tick()})
  assert.equal(document.querySelectorAll('.aura-home__image-attachments .aura-home__attachment').length,2)
  await click(document.querySelector('[aria-label="Send question"]'))
  assert.deepEqual(requests.find(r=>r.path==='/chat').body.source_ids,[8,7])
})
test('pasted screenshots append alongside typed text and removable legacy image attachments',async()=>{
  localStorage.setItem('aura.chat.v1:1:6',JSON.stringify({uploaded:{courseId:'6',sourceId:'50',filename:'legacy.png',fileType:'image',processingStatus:'success',contentUnitCount:1},uploadStage:'ready'}))
  await mount(ChatHome,homeProps());await input(document.querySelector('#aura-question'),'My MCQ text stays here')
  const paste=new Event('paste',{bubbles:true})
  Object.defineProperty(paste,'clipboardData',{value:{files:[new File(['authored image'],'pasted.png',{type:'image/png'})]}})
  await act(async()=>{document.querySelector('#aura-question').dispatchEvent(paste);await tick();await tick();await tick()})
  assert.equal(document.querySelectorAll('.aura-home__image-attachments .aura-home__attachment').length,2)
  assert.equal(document.querySelector('#aura-question').value,'My MCQ text stays here')
  await click(document.querySelector('[aria-label="Remove legacy.png"]'))
  await click(document.querySelector('[aria-label="Remove pasted.png"]'))
  assert.equal(document.querySelectorAll('.aura-home__attachment').length,0)
})
test('pending screenshot preparation resumes after refresh and all images are required before send',async()=>{
  holdImagePreparation=true
  await mount(ChatHome,homeProps());await input(document.querySelector('#aura-question'),'Use both screenshots')
  await attachScreenshots(['pending-a.png','pending-b.png'])
  assert(document.querySelector('[aria-label="Send question"]').disabled)
  const stored=JSON.parse(localStorage.getItem('aura.chat.v1:1:6'))
  assert.equal(stored.imageAttachments.filter(item=>item.jobId).length,2)
  preparationJobs=preparationJobs.map((job,index)=>({...job,state:'ready',source_id:index+7,result:{source_id:index+7,course_id:6,source_name:job.filename,source_type:'image',status:'success',content_units:1,warnings:[]}}))
  await act(async()=>{root.render(null);await tick()});await mount(ChatHome,homeProps())
  assert(!document.querySelector('[aria-label="Send question"]').disabled)
  await click(document.querySelector('[aria-label="Send question"]'))
  assert.deepEqual(requests.find(r=>r.path==='/chat').body.source_ids,[7,8])
})
test('an older backend answering only one screenshot is surfaced as an error',async()=>{
  legacyImageReply=true
  await mount(ChatHome,homeProps());await input(document.querySelector('#aura-question'),'Question with two screenshots')
  await attachScreenshots(['one.png','two.png']);await click(document.querySelector('[aria-label="Send question"]'))
  assert.match(visibleText(),/could not confirm that all attached screenshots were used/)
  assert(!document.querySelector('.aura-home__message--tutor'))
  assert.equal(document.querySelectorAll('.aura-home__image-attachments .aura-home__attachment').length,2)
  assert(button('Retry question'))
})

test('empty screen is goal-first and cannot start without selected ready material', async () => {
  await mount(AgentPanel, props({ sourceId: '', materialReady: false }))
  assert.equal(document.querySelectorAll('.plan-examples button').length, 3)
  assert.equal(document.querySelector('.plan-options').open, false)
  await click(button('3-day plan'))
  assert(button('Create my plan').disabled)
  assert.match(visibleText(), /Choose a material/)
  assert.equal(document.querySelectorAll('.plan-outcomes input[type=radio]').length, 4)
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
test('Today renders saved paragraph schedules as session cards while preserving task completion', async () => {
  const details = 'Morning (2h): Review the selected lesson. Focus on: 1) Arrays 2) Hash tables. Afternoon (1.5h): Practice a small example. Evening (1h): Make flashcards.'
  tasks = [{ id: 'task-a', title: 'Day 1: Dictionary revision', details, done: false }]
  await mount(AgentPanel, props())
  await click(button('Today'))
  assert.deepEqual([...document.querySelectorAll('.plan-task .plan-session-heading h4')].map(e => e.textContent), ['Morning', 'Afternoon', 'Evening'])
  assert.deepEqual([...document.querySelectorAll('.plan-task .plan-session-time')].map(e => e.textContent), ['2h', '1.5h', '1h'])
  assert.equal(document.querySelectorAll('.plan-task .plan-action-list>li').length, 5)
  assert.equal(document.querySelectorAll('.plan-task input[type=checkbox]').length, 1)
  await click(document.querySelector('.plan-task input'))
  assert(requests.some(r => r.path === '/agents/tasks/task-a' && r.method === 'PATCH' && r.body.done === true))
  assert.equal(tasks[0].details, details)
  assert(document.querySelector('.plan-task').classList.contains('is-done'))
})
test('plan day cards use the same session layout and only total explicit durations', async () => {
  const details = 'Morning (30 min): Read the lesson. Afternoon (1h): Work through an example.'
  const saved = baseRun()
  saved.result.structured_plan.days[0].details = details
  jobs = [saved]; tasks = [{id:'task-a', title:'Day 1: Membrane proteins',details,done:false}]
  const opened=[]
  await mount(AgentPanel, props({onOpenTool:(...args)=>opened.push(args)}))
  assert.equal(document.querySelectorAll('.plan-day .plan-session').length, 2)
  assert.match(document.querySelector('.plan-day-top').textContent, /90 min planned/)
  assert.match(document.querySelector('.plan-day').textContent, /Slide 18/)
  await click(button('Read summary'))
  assert.deepEqual(opened[0], ['Summary', 'Membrane proteins', '7'])
})
test('legacy task prose becomes readable action bullets without interpreting HTML', async () => {
  tasks = [{id:'task-old',title:'Review fundamentals',details:'Review O(1) lookup. Read for 1.5 hours. Compare <img src=x onerror=alert(1)> with a code sample.',done:false}]
  await mount(AgentPanel,props())
  await click(button('Today'))
  assert.equal(document.querySelectorAll('.plan-task .plan-action-list>li').length,3)
  assert.equal(document.querySelectorAll('.plan-task img').length,0)
  assert.match(document.querySelector('.plan-task').textContent,/1.5 hours/)
  assert.equal(document.querySelectorAll('.plan-task .plan-session-time').length,0)
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
  await click(button('Stop'))
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
test('memory retry clears the failed state and restores usable controls', async () => {
  failLoads = true
  await mount(AccountMenu, { name: 'Sam Rivera', courseId: '6' })
  await click(document.querySelector('.aura-account summary'))
  await click(button('What Aura remembers'))
  assert(document.querySelector('.aura-memory [role=alert]'))
  assert(document.querySelector('.aura-memory input[role=switch]').disabled)
  failLoads = false
  await click(button('Retry'))
  assert(!document.querySelector('.aura-memory [role=alert]'))
  assert(!document.querySelector('.aura-memory input[role=switch]').disabled)
})
test('workspace keeps Agents identity but shows Study Plan, real extension and working Change focus', async () => {
  materials.push({ source_id: 8, source_name: 'Biology revision.pdf', source_type: 'pdf', status: 'success' })
  await mount(StudyWorkspace, { user: { id: '1', fullName: 'Sam Rivera', email: 'sam@example.test' }, courses: [{ id: '6', title: 'Biology' }], courseId: '6', coursesLoading: false, coursesError: '', theme: 'dark', onCourseChange() {}, onThemeChange() {}, onChatHome() {}, onSignOut() {}, signingOut: false, sessionNotice: '' })
  assert.equal(document.querySelector('h1').textContent, 'Study Plan')
  assert.match(document.querySelector('.aura-using').textContent, /Using.*Biological membranes.ppt/)
  assert.equal(document.querySelector('.aura-material-option small').textContent, 'PPT')
  assert(!document.querySelector('.sw-heading .sw-eyebrow').textContent.includes('Biological membranes'))
  await click(button('Change'))
  assert.equal(document.activeElement, document.querySelector('.sw-material-search input'))
  await click(document.querySelectorAll('.aura-material-option input')[0]); await click(document.querySelectorAll('.aura-material-option input')[1])
  assert.equal(new URL(window.location.href).searchParams.get('source'), '8')
  assert.match(document.querySelector('.aura-using').textContent, /Biology revision.pdf/)
})
test('source/topic deep links reach existing tools and retain focus after reload', async () => {
  window.history.replaceState(null, '', '/?view=study&tab=Flashcards&source=7&topic=Membrane%20proteins')
  await mount(StudyWorkspace, { user: { id: '1', fullName: 'Sam Rivera' }, courses: [], courseId: '6', coursesLoading: false, coursesError: '', theme: 'dark', onCourseChange() {}, onThemeChange() {}, onChatHome() {}, onSignOut() {}, signingOut: false, sessionNotice: '' })
  assert.equal(document.querySelector('h1').textContent, 'Flashcards')
  assert.equal(document.querySelector('.sw-focus input').value, 'Membrane proteins')
  assert(document.querySelector('.aura-material-option.is-selected'))
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
  assert([...document.querySelectorAll('[role=alert]')].some(node => /could not create and verify/.test(node.textContent)))
  assert(!visibleText().includes('Ollama'))
  assert.equal(document.querySelector('.sw-focus input').value, 'Membrane proteins')
  assert.match(document.querySelector('.aura-using').textContent, /Biological membranes.ppt/)
  assert(button('Generate').disabled === false)
})

test('research results keep web findings separate and link only observed safe URLs', async () => {
  jobs = [baseRun({ request: { skill: 'research_brief', goal: 'Research membrane proteins' }, result: {
    text: 'Research draft', verified: false, references: ['D9', 'Wabc123'], web_status: 'searched',
    research_sections: [
      { kind: 'material', text: 'Your slides explain membrane proteins [D9].', references: ['D9'] },
      { kind: 'web', text: 'Additional findings [Wabc123]. Untrusted Markdown [click](javascript:alert(1)).', references: ['Wabc123'] }
    ], sources: [
      { reference: 'D9', kind: 'material', title: 'Biological membranes.ppt', slide: 18 },
      { reference: 'Wabc123', kind: 'web', title: 'Public reference', url: 'https://www.ncbi.nlm.nih.gov/books/' }
    ], limitations: ['Search snippets have not been independently verified.']
  } })]
  await mount(AgentPanel, props())
  assert(document.querySelector('[aria-label="From your material"]'))
  assert(document.querySelector('[aria-label="From the web"]'))
  const links = [...document.querySelectorAll('.research-result a')]
  assert(links.length > 0)
  assert(links.every(a => a.href === 'https://www.ncbi.nlm.nih.gov/books/' && a.rel.includes('noopener')))
  assert(!document.querySelector('a[href^="javascript:"]'))
  assert.match(visibleText(), /not been independently verified/)
})
test('a failed research lookup is shown as a limitation without a web-backed section', async () => {
  jobs = [baseRun({ request: { skill: 'research_brief', goal: 'Research' }, result: {
    text: 'Findings', verified: false, references: ['D9'], web_status: 'unavailable',
    research_sections: [{ kind: 'material', text: 'Material findings.', references: ['D9'] }],
    sources: [{ reference: 'D9', kind: 'material', title: 'Slides', slide: 18 }],
    limitations: ['Web search was unavailable; this brief uses uploaded material only.']
  } })]
  await mount(AgentPanel, props())
  assert(!document.querySelector('[aria-label="From the web"]'))
  assert.match(visibleText(), /Web search was unavailable/)
})

test('research does not inherit day-plan instructions from saved study options', async () => {
  localStorage.setItem('plan:test:learner:6', JSON.stringify({ skill: 'research_brief', goal: 'Research membrane proteins', options: { days: '3', minutes: '45', depth: 'deep' } }))
  await mount(AgentPanel, props())
  assert(!visibleText().includes('Days available'))
  assert.match(visibleText(), /public topic keywords/)
  await click(button('Start research'))
  const body = requests.find(r => r.method === 'POST' && r.path === '/agents/runs').body
  assert.equal(body.skill, 'research_brief')
  assert(!body.goal.includes('3-day'))
  assert.match(body.goal, /Explanation depth: deep/)
})
test('unconfigured web is disclosed while material research remains available', async () => {
  webAvailable = false
  localStorage.setItem('plan:test:learner:6', JSON.stringify({ skill: 'research_brief', goal: 'Research membrane proteins' }))
  await mount(AgentPanel, props())
  assert.match(visibleText(), /Web search is unavailable/)
  assert(!button('Start research').disabled)
})

const quizRun = () => baseRun({ request: { skill: 'assessment', goal: 'Quiz me on membrane proteins' }, result: {
  text: 'Your quiz is ready.', verified: false, references: ['D9'], assessment: { artifact_id: 'quiz-a', title: 'Membrane knowledge check', question_count: 3, difficulty: 'beginner', focus: 'membrane proteins', verification: 'model_checked' }
} })
const quizArtifact = (id, source = 7) => ({ id, kind: 'assessment', created_at: '2026-10-23T08:00:00Z', result: null, payload: {
  source_id: source, course_id: 6, source_title: 'Biological membranes.ppt', focus: 'membrane proteins',
  items: [{ id: 'item-1', kind: 'mcq', difficulty: 'beginner', topic: 'Membranes', prompt: id === 'quiz-a' ? 'Which component forms the bilayer?' : 'A different saved quiz?', choices: [{ id: 'A', text: 'Lipids' }, { id: 'B', text: 'DNA' }, { id: 'C', text: 'Cellulose' }, { id: 'D', text: 'RNA' }], citation_ids: [] }], citations: [], coverage: { selected_passages: 1, available_passages: 1 }
} })
test('quiz outcome uses its own goals and preserves the existing start payload', async () => {
  await mount(AgentPanel, props())
  await click(document.querySelector('input[value=assessment]'))
  assert.match(visibleText(), /Check the fundamentals/)
  assert(!visibleText().includes('3-day plan'))
  assert(!visibleText().includes('Days available'))
  await click(button('Check the fundamentals'))
  await input(document.getElementById('plan-goal'), 'Create 5 questions about membrane proteins')
  await click(document.querySelector('[aria-label="2 questions"]'))
  await click(document.querySelector('[aria-label="Quiz difficulty"]'))
  await click([...document.querySelectorAll('[role=option]')].find(item => item.textContent.startsWith('Advanced')))
  await click(button('Create my quiz'))
  const body = requests.find(r => r.method === 'POST' && r.path === '/agents/runs').body
  assert.deepEqual(Object.keys(body).sort(), ['course_id', 'source_id', 'goal', 'skill', 'allow_memory_write'].sort())
  assert.equal(body.skill, 'assessment'); assert.equal(body.source_id, 7)
  assert.match(body.goal, /exactly 2 multiple-choice questions/)
  assert.match(body.goal, /Difficulty: advanced/)
  assert(!body.goal.includes('5 questions'))
})
test('quiz capability is disabled on an older backend', async () => {
  assessmentAvailable = false
  await mount(AgentPanel, props())
  assert(document.querySelector('input[value=assessment]').disabled)
})
test('research examples retain research selection instead of creating a plan goal', async () => {
  await mount(AgentPanel, props())
  await click(document.querySelector('input[value=research_brief]'))
  await click(button('Explore a key concept'))
  assert(document.querySelector('input[value=research_brief]').checked)
  assert(!document.getElementById('plan-goal').value.includes('Create a study plan'))
  await click(button('Start research'))
  assert.equal(requests.find(r => r.method === 'POST' && r.path === '/agents/runs').body.skill, 'research_brief')
})
test('saved quiz CTA opens the exact artifact with its original selected material', async () => {
  jobs = [quizRun()]
  const opened = []
  await mount(AgentPanel, props({ sourceId: '8', onOpenTool: (...args) => opened.push(args) }))
  assert.match(visibleText(), /Your quiz is ready/)
  assert.match(visibleText(), /3 multiple-choice questions/)
  assert(!button('Download .md'))
  assert(!visibleText().includes('RAW INTERNAL NARRATION'))
  await click(button('Open my quiz'))
  assert.deepEqual(opened[0], ['Assessment', 'membrane proteins', '7', 'quiz-a'])
})
test('workspace refreshes saved artifacts and opens the requested quiz rather than the newest quiz', async () => {
  jobs = [quizRun()]
  savedArtifacts = [quizArtifact('quiz-other'), quizArtifact('quiz-a')]
  await mount(StudyWorkspace, { user: { id: 'learner-1', fullName: 'Sam Rivera', email: 'sam@example.test' }, courses: [{ id: '6', title: 'Biology' }], courseId: '6', coursesLoading: false, coursesError: '', theme: 'dark', onCourseChange() {}, onThemeChange() {}, onChatHome() {}, onSignOut() {}, signingOut: false, sessionNotice: '' })
  const before = requests.filter(r => r.path === '/study/artifacts').length
  await click(button('Open my quiz'))
  assert.match(document.body.textContent, /Which component forms the bilayer/)
  assert(!document.body.textContent.includes('A different saved quiz?'))
  assert.equal(new URL(window.location.href).searchParams.get('artifact'), 'quiz-a')
  assert.equal(new URL(window.location.href).searchParams.get('source'), '7')
  assert(requests.filter(r => r.path === '/study/artifacts').length > before)
  assert(document.querySelector('.sw-assessment'))
})
test('direct quiz link restores the exact saved assessment after refresh', async () => {
  window.history.replaceState(null, '', '/?view=study&tab=Assessment&source=7&artifact=quiz-a')
  savedArtifacts = [quizArtifact('quiz-other'), quizArtifact('quiz-a')]
  await mount(StudyWorkspace, { user: { id: 'learner-1', fullName: 'Sam Rivera', email: 'sam@example.test' }, courses: [{ id: '6', title: 'Biology' }], courseId: '6', coursesLoading: false, coursesError: '', theme: 'dark', onCourseChange() {}, onThemeChange() {}, onChatHome() {}, onSignOut() {}, signingOut: false, sessionNotice: '' })
  assert.match(document.body.textContent, /Which component forms the bilayer/)
  assert(!document.body.textContent.includes('A different saved quiz?'))
})


test('code analysis can start without material and sends only the additive input field', async () => {
  await mount(AgentPanel, props({ sourceId: '', materialReady: false }))
  await click(document.querySelector('input[value=code_analysis]'))
  await click(button('Calculate and explain'))
  assert(!button('Run analysis').disabled)
  assert(!document.querySelector('.plan-options'))
  await click(button('Run analysis'))
  const start = requests.find(r => r.method === 'POST' && r.path === '/agents/runs')
  assert.equal(start.body.skill, 'code_analysis'); assert.equal(start.body.source_id, null)
  assert.deepEqual(start.body.inputs, []); assert.equal(start.body.allow_memory_write, false)
  assert.match(start.body.goal, /fixed seed/)
})
test('code capability is off until the server advertises an execution backend', async () => {
  codeAvailable = false
  await mount(AgentPanel, props())
  assert(document.querySelector('input[value=code_analysis]').disabled)
  assert.match(visibleText(), /Execution needs to be enabled/)
})
test('code results are observed text with authenticated artifact downloads and recover after refresh', async () => {
  const observation = { status: 'succeeded', exit_code: 0, stdout: '<img src=x onerror=alert(1)>\n4', stderr: '', stdout_truncated: false, stderr_truncated: false, missing_outputs: [], artifacts: [{ name: 'result.csv', mime: 'text/csv', size: 8, sha256: 'a'.repeat(64) }] }
  jobs = [baseRun({ source_id: null, request: { skill: 'code_analysis', goal: 'Calculate four' }, steps: [{ tool: 'code_execute', state: 'completed', action: { code: 'print(4)' }, observation }], result: { text: 'The calculation returned four.', code_result: observation, verified: false } })]
  const downloads = [], urls = []
  const previousCreate = URL.createObjectURL, previousRevoke = URL.revokeObjectURL
  URL.createObjectURL = blob => { urls.push(blob); return 'blob:test-code' }; URL.revokeObjectURL = () => {}
  window.HTMLAnchorElement.prototype.click = function () { downloads.push({ href: this.href, name: this.download }) }
  try {
    await mount(AgentPanel, props({ sourceId: '', materialReady: false }))
    assert.match(visibleText(), /Python finished successfully/)
    assert.equal(document.querySelector('.plan-code-result img'), null)
    assert.match(document.querySelector('.plan-code-result pre').textContent, /print\(4\)/)
    assert(!button('Download .md'))
    await click(document.querySelector('.plan-code-files button'))
    assert.equal(downloads[0].name, 'result.csv'); assert.equal(urls[0].size, 8)
    assert(requests.some(r => r.path === '/agents/runs/run-a/artifacts/result.csv' && r.query === '?course_id=6'))
    await act(async () => root.unmount()); root = createRoot(document.getElementById('root'))
    await mount(AgentPanel, props({ sourceId: '', materialReady: false }))
    assert.match(visibleText(), /calculation returned four/)
    assert(!button('Regenerate').disabled)
  } finally { URL.createObjectURL = previousCreate; URL.revokeObjectURL = previousRevoke }
})
test('CSV inputs remain out of local storage and regenerate uses the saved attachment', async () => {
  await mount(AgentPanel, props({ sourceId: '', materialReady: false }))
  await click(document.querySelector('input[value=code_analysis]'))
  await click(button('Analyze my CSV'))
  const field = document.getElementById('plan-code-files')
  const csv = new TextEncoder().encode('x\n4\n')
  Object.defineProperty(field, 'files', { configurable: true, value: [{ name: 'data.csv', size: csv.length, arrayBuffer: async () => csv.buffer }] })
  await act(async () => { field.dispatchEvent(new dom.window.Event('change', { bubbles: true })); await tick() })
  assert.match(visibleText(), /data.csv/)
  assert(!localStorage.getItem('plan:test:learner:6').includes('x\\n4'))
  await click(button('Run analysis'))
  assert.deepEqual(requests.find(r => r.method === 'POST' && r.path === '/agents/runs').body.inputs, [{ name: 'data.csv', text: 'x\n4\n' }])
  jobs[0].state = 'completed'; jobs[0].result = { text: 'Four.', references: [], verified: false }
  await act(async () => root.unmount()); root = createRoot(document.getElementById('root'))
  await mount(AgentPanel, props({ sourceId: '', materialReady: false }))
  await click(button('Regenerate'))
  assert.deepEqual(requests.filter(r => r.method === 'POST' && r.path === '/agents/runs').at(-1).body.inputs, [{ name: 'data.csv', text: 'x\n4\n' }])
})
test('CSV path and size checks prevent run submission without affecting other skills', async () => {
  await mount(AgentPanel, props())
  await click(document.querySelector('input[value=code_analysis]'))
  await click(button('Analyze my CSV'))
  const field = document.getElementById('plan-code-files')
  Object.defineProperty(field, 'files', { configurable: true, value: [{ name: '../data.csv', size: 4, arrayBuffer: async () => new ArrayBuffer(4) }] })
  await act(async () => { field.dispatchEvent(new dom.window.Event('change', { bubbles: true })); await tick() })
  assert(button('Run analysis').disabled)
  assert(document.querySelector('[role=alert]'))
  await click(document.querySelector('input[value=study_plan]'))
  assert(!button('Create my plan').disabled)
})

test('a stopped code run retains observed output and Make it simpler narrows the retry', async () => {
  const output = { status: 'succeeded', exit_code: 0, stdout: '4', stderr: '', stdout_truncated: false, stderr_truncated: false, missing_outputs: [], artifacts: [] }
  jobs = [baseRun({ state: 'budget_exhausted', source_id: null, request: { skill: 'code_analysis', goal: 'Calculate four' }, result: null, steps: [{ tool: 'code_execute', state: 'completed', observation: output }] })]
  await mount(AgentPanel, props({ sourceId: '', materialReady: false }))
  assert.match(visibleText(), /Stopped early/)
  assert.match(visibleText(), /Python finished successfully/)
  await click(button('Make it simpler'))
  const body = requests.find(r => r.method === 'POST' && r.path === '/agents/runs').body
  assert.equal(body.skill, 'code_analysis')
  assert.match(body.goal, /one small calculation/)
  assert.match(body.goal, /skip output files/)
})


test('sandbox setup failures give actionable copy without exposing internal codes', async () => {
  jobs = [baseRun({ state: 'failed', source_id: null, request: { skill: 'code_analysis', goal: 'Teach me bubble sort' }, error_code: 'docker_image_missing', result: null, steps: [{ tool: 'code_execute', state: 'failed', error_code: 'docker_image_missing' }] })]
  await mount(AgentPanel, props())
  assert.match(visibleText(), /Python image is missing/)
  assert.match(visibleText(), /Build it from sandbox\/Dockerfile/)
  assert(!visibleText().includes('docker_image_missing'))
  assert(!visibleText().includes('SandboxUnavailable'))
  assert(button('Retry'))
})
test('older failed runs with a saved step reason still show Docker connection guidance', async () => {
  jobs = [baseRun({ state: 'failed', request: { skill: 'code_analysis', goal: 'Teach me bubble sort' }, error_code: 'model_or_tool_unavailable', result: null, steps: [{ tool: 'code_execute', state: 'failed', error_code: 'docker_daemon_unavailable' }] })]
  await mount(AgentPanel, props())
  assert.match(visibleText(), /Start Docker Desktop/)
  assert(!visibleText().includes('docker_daemon_unavailable'))
})

test('a Windows executable-format failure explains native docker.exe selection', async () => {
  jobs = [baseRun({ state: 'failed', request: { skill: 'code_analysis', goal: 'Teach me bubble sort' }, error_code: 'docker_bad_executable', result: null, steps: [] })]
  await mount(AgentPanel, props())
  assert.match(visibleText(), /Windows could not launch/)
  assert.match(visibleText(), /Get-Command docker.exe/)
  assert(!visibleText().includes('docker_bad_executable'))
  assert(button('Retry'))
})

test('teaching text renders clear headings, examples, lists, code and tables while escaping HTML', async () => {
  await mount(TeachingText,{text:'## 🧠 Key idea\nA **membrane** surrounds the cell [2].\n\n1. Read the evidence.\n2. Check the example.\n\n```python\nprint("<script>bad()</script>")\n```\n\n| Term | Meaning |\n| --- | --- |\n| Lipid | Bilayer component |\n\n<img src=x onerror=bad()>\n[Open](javascript:bad())'})
  assert.match(document.querySelector('h3').textContent,/Key idea/)
  assert.equal(document.querySelector('strong').textContent,'membrane')
  assert.equal(document.querySelectorAll('ol li').length,2)
  assert.match(document.querySelector('pre code').textContent,/<script>/)
  assert.equal(document.querySelectorAll('table tbody tr').length,1)
  assert.equal(document.querySelectorAll('img,script,a').length,0)
  assert.match(document.body.textContent,/\[2\]/)
  await mount(TeachingText,{text:'**Unclosed emphasis must retain the final letters\n\n`Unclosed code must stay intact'})
  assert.match(document.body.textContent,/\*\*Unclosed emphasis must retain the final letters/)
  assert.match(document.body.textContent,/`Unclosed code must stay intact/)
})
test('tutor replies separate source and background, deduplicate clarification and offer follow-ups', async () => {
  const picked=[]
  await mount(TutorReply,{text:'From your material:\nA bilayer has lipids [2].\n\nBeyond your material — model knowledge, not web verified:\nGeneral explanation.\n\nWhich part is hardest?',clarification:'Which part is hardest?',followUps:['Show an example','Go deeper'],onFollowUp:v=>picked.push(v)})
  assert.equal(document.querySelectorAll('.aura-teaching-provenance').length,2)
  assert(document.querySelector('.is-background'))
  assert.equal(document.body.textContent.split('Which part is hardest?').length-1,1)
  assert(document.querySelector('aside'))
  await click(button('Go deeper'))
  assert.deepEqual(picked,['Go deeper'])
  await mount(TutorReply,{text:'Clear answer.',followUps:null,onFollowUp:()=>{}})
  assert.equal(document.querySelectorAll('.aura-tutor-followups').length,0)
})
test('daily rhythm is opt-in, persists settings and briefs after remount, and makes no model requests', async () => {
  await mount(StudyRhythm,{courseId:'6',onPractice:()=>{}})
  assert.equal(document.querySelector('[role=switch]').checked,false)
  assert.match(visibleText(),/No email/)
  assert.equal(document.querySelector('.study-rhythm details').open,false)
  await input(document.querySelector('[aria-label="Digest timezone"]'),'Asia/Calcutta')
  await input(document.querySelector('[aria-label="Daily digest hour"]'),'8')
  await click(document.querySelector('[role=switch]'))
  const saved=requests.find(r=>r.path==='/study/rhythm/settings')
  assert.deepEqual(saved.body,{enabled:true,timezone:'Asia/Calcutta',daily_hour:8})
  assert.equal(saved.query,'?course_id=6')
  await click(button('Update due topics'))
  assert.match(visibleText(),/Your next study session/)
  await act(async()=>root.unmount());root=createRoot(document.getElementById('root'))
  await mount(StudyRhythm,{courseId:'6',onPractice:()=>{}})
  assert(document.querySelector('[role=switch]').checked)
  assert.match(visibleText(),/2026-10-23/)
  assert(requests.every(r=>r.path.startsWith('/study/rhythm')))
  await click(document.querySelector('[role=switch]'))
  assert.equal(rhythm.settings.enabled,false)
  assert(!button('Update due topics'))
})
test('due practice preserves its original material and Tomorrow uses the persisted scoped API', async () => {
  rhythm.settings.enabled=true
  rhythm.reviews=[{source_id:12,topic_key:'lipid-bilayer',topic:'Lipid bilayer',source_name:'Membrane slides.pptx',due_at:'2026-10-22T09:00:00Z'}]
  const opened=[]
  await mount(StudyRhythm,{courseId:'6',onPractice:(...args)=>opened.push(args)})
  await click(button('Practice this topic'))
  assert.deepEqual(opened,[['Lipid bilayer','12']])
  await click(button('Tomorrow'))
  assert(requests.some(r=>r.path==='/study/rhythm/snooze'&&r.query==='?course_id=6'&&r.body.source_id===12&&r.body.topic_key==='lipid-bilayer'))
  assert.equal(document.querySelectorAll('.rhythm-reviews article').length,0)
})
test('rhythm load failure is recoverable and course changes discard prior workspace content', async () => {
  rhythmUnavailable=true
  await mount(StudyRhythm,{courseId:'6',onPractice:()=>{}})
  assert.match(document.querySelector('[role=alert]').textContent,/could not be loaded/)
  assert(!visibleText().includes('Private failure detail'))
  rhythmUnavailable=false
  await click(button('Retry'))
  assert(document.querySelector('[role=switch]'))
  rhythm.settings.enabled=true
  rhythm.digests=[{id:'private',local_date:'2026-10-23',created_at:'2026-10-23T09:00:00Z',payload:{title:'Previous workspace private brief',takeaway:'Only in course 6',tasks:[],reviews:[],method:'Graded'}}]
  await act(async()=>root.unmount());root=createRoot(document.getElementById('root'))
  await mount(StudyRhythm,{courseId:'6',onPractice:()=>{}})
  assert.match(visibleText(),/Previous workspace/)
  rhythm={settings:{enabled:false,timezone:'UTC',daily_hour:9},digests:[],reviews:[],notice:''}
  await mount(StudyRhythm,{courseId:'8',onPractice:()=>{}})
  assert(!visibleText().includes('Previous workspace'))
  assert(requests.some(r=>r.path==='/study/rhythm'&&r.query==='?course_id=8'))
})
test('quality summary is collapsed and distinguishes offline passes from unmeasured human agreement', async () => {
  await mount(EvaluationSummary,{courseId:'6'})
  assert.equal(document.querySelector('details').open,false)
  await click(document.querySelector('summary'))
  assert.match(visibleText(),/10 \/ 10/)
  assert.match(visibleText(),/2 \/ 2/)
  assert.match(visibleText(),/0 \/ 30 outputs reviewed/)
  assert.match(visibleText(),/Not measured/)
  assert.match(visibleText(),/3 total · 2 completed · 1 failed/)
  assert.match(visibleText(),/completion is not a correctness score/)
  assert(requests.some(r=>r.path==='/study/evaluation'&&r.query==='?course_id=6'))
})

test('web-only research has a readable result without an empty material section', async () => {
  jobs=[baseRun({request:{skill:'research_brief',goal:'Teach me bubble sort'},result:{
    text:'Web research brief',verified:false,references:['Wabc123'],web_status:'searched',
    research_sections:[{kind:'web',text:'## 🧠 Key idea\nCompare **adjacent values** [Wabc123].\n\n1. Compare the pair.\n2. Swap if out of order.\n\n```python\nprint([1, 2])\n```',references:['Wabc123']}],
    sources:[{reference:'Wabc123',kind:'web',title:'Bubble sort reference',url:'https://example.org/bubble-sort'}],
    limitations:['No relevant findings in the uploaded passages checked.']
  }})]
  await mount(AgentPanel,props())
  assert(document.querySelector('[aria-label="From the web"]'))
  assert(!document.querySelector('[aria-label="From your material"]'))
  assert.match(visibleText(),/Compare adjacent values/)
  assert.match(document.querySelector('[aria-label=\"From the web\"] h3').textContent,/From the web/)
  assert.equal(document.querySelector('.research-result strong').textContent,'adjacent values')
  assert.equal(document.querySelectorAll('.research-result ol li').length,2)
  assert.match(document.querySelector('.research-result pre code').textContent,/print/)
  assert.match(visibleText(),/No relevant findings/)
  assert(!visibleText().includes('Something went wrong'))
  assert(document.querySelector('.research-result a[href="https://example.org/bubble-sort"]'))
})
test('failed research uses research-specific recovery and Retry preserves the chosen skill', async () => {
  jobs=[baseRun({state:'failed',request:{skill:'research_brief',goal:'Teach me bubble sort'},error_code:'invalid_action',result:null})]
  await mount(AgentPanel,props())
  assert.match(visibleText(),/could not finish formatting this research brief/)
  assert(!visibleText().includes('Try creating the plan again'))
  assert(!visibleText().includes('invalid_action'))
  await click(button('Retry'))
  const start=requests.find(r=>r.path==='/agents/runs'&&r.method==='POST')
  assert.equal(start.body.skill,'research_brief')
  assert.match(start.body.goal,/Teach me bubble sort/)
})

test('code decision-format failures give retry guidance without blaming execution setup', async () => {
  jobs=[baseRun({state:'failed',source_id:null,request:{skill:'code_analysis',goal:'Compare linear and binary search'},error_code:'invalid_action',result:null,steps:[{tool:'validation',state:'rejected',error_code:'invalid_action'}]})]
  await mount(AgentPanel,props())
  assert.match(visibleText(),/could not format a valid code request/)
  assert(!visibleText().includes('Check that execution is enabled'))
  assert(!visibleText().includes('invalid_action'))
  await click(button('Retry'))
  const start=requests.find(r=>r.method==='POST'&&r.path==='/agents/runs')
  assert.equal(start.body.skill,'code_analysis')
  assert.match(start.body.goal,/Compare linear and binary search/)
})

test('model connection failures explain recovery for every outcome without blaming Docker', async () => {
  for (const skill of ['code_analysis','study_plan','research_brief','assessment']) {
    jobs=[baseRun({id:`network-${skill}`,state:'failed',request:{skill,goal:'Explain this topic'},error_code:'model_connection_failed',result:null,steps:[]})]
    await mount(AgentPanel,props({storageKey:`network-${skill}`}))
    assert.match(visibleText(),/could not connect to the AI service/)
    assert(!visibleText().includes('model_connection_failed'))
    assert(!visibleText().includes('Docker'))
    assert(!visibleText().includes('Check that execution is enabled'))
    assert(button('Retry'))
    await act(async()=>{root.unmount();await tick()})
    root=createRoot(document.getElementById('root'))
  }
})

test('a failed explanation retains successful Python output and names the connection problem', async () => {
  jobs=[baseRun({state:'failed',source_id:null,request:{skill:'code_analysis',goal:'Compare searches'},error_code:'model_timeout',result:null,steps:[{tool:'code_execute',state:'completed',action:{tool:'code_execute',code:'print(4)'},observation:{status:'succeeded',stdout:'4\n',stderr:'',artifacts:[],missing_outputs:[],stdout_truncated:false,stderr_truncated:false}}]})]
  await mount(AgentPanel,props())
  assert.match(visibleText(),/AI service took too long/)
  assert.match(visibleText(),/captured Python output is saved below/)
  assert.match(document.querySelector('[aria-label="Python output"]').textContent,/4/)
  assert(!visibleText().includes('model_timeout'))
  assert(!document.querySelector('.plan-run-details').open)
  await click(button('Retry'))
  assert.equal(requests.find(r=>r.method==='POST'&&r.path==='/agents/runs').body.skill,'code_analysis')
})

test('a saved formatted code lesson renders sections and results without changing captured output', async () => {
  jobs=[baseRun({request:{skill:'code_analysis',goal:'Explain search results'},steps:[],result:{text:'## 🧠 Main idea\n\n**Binary search** halves a sorted range.\n\n## Worked example\n\nFor target 7, the first midpoint has index 3 and value 7.\n\n## Results\n\n| Target | Index |\n|---|---|\n| 4 | -1 |\n\n## Limitations\n\nThese counts apply to this implementation.',code_result:{status:'succeeded',stdout:'target=4,index=-1\n',stderr:'',artifacts:[],missing_outputs:[]}}})]
  await mount(AgentPanel,props())
  assert.match(document.querySelector('.plan-code-result h3').textContent,/Main idea/)
  assert.equal(document.querySelector('.plan-code-result strong').textContent,'Binary search')
  assert.match(document.querySelector('.plan-code-result table').textContent,/4.*-1/s)
  assert.equal(document.querySelector('[aria-label="Python output"] pre').textContent,'target=4,index=-1\n')
})

test('a withheld code explanation keeps output and files with a clear recovery message', async () => {
  const output={status:'succeeded',stdout:'23,6,3\n',stderr:'',stdout_truncated:false,stderr_truncated:false,artifacts:[{name:'search_results.json',size:523,mime:'application/json',sha256:'a'.repeat(64)}],missing_outputs:[]}
  jobs=[baseRun({state:'failed',request:{skill:'code_analysis',goal:'Compare search algorithms'},error_code:'code_explanation_not_supported',steps:[{tool:'code_execute',state:'completed',observation:output},{tool:'verification',state:'failed'}],result:{text:'',verified:false,references:[],code_result:output}})]
  await mount(AgentPanel,props())
  assert.match(visibleText(),/withheld that text/)
  assert.match(visibleText(),/search_results.json/)
  assert.match(document.querySelector('[aria-label="Python output"]').textContent,/23,6,3/)
  assert(!visibleText().includes('code_explanation_not_supported'))
  assert(!visibleText().includes('AI review checked'))
  assert(button('Retry'))
})

test('code explanation review has a friendly progress label and does not promise perfect accuracy', async () => {
  jobs=[baseRun({state:'running',request:{skill:'code_analysis',goal:'Explain searches'},result:null,steps:[{tool:'code_execute',state:'completed'},{tool:'verification',state:'running'}]})]
  await mount(AgentPanel,props())
  assert.match(document.querySelector('[aria-current="step"]').textContent,/Checking your explanation/)
  jobs=[baseRun({request:{skill:'code_analysis',goal:'Explain searches'},steps:[{tool:'verification',state:'completed'}],result:{text:'The captured output contains four.',code_result:{status:'succeeded',stdout:'4\n',stderr:'',artifacts:[],missing_outputs:[]},verified:false}})]
  await mount(AgentPanel,props({courseId:'7'}))
  assert.match(visibleText(),/AI review checked the explanation/)
  assert.match(visibleText(),/can still miss mistakes/)
})


const workspaceProps = () => ({ user: { id: '1', fullName: 'Sam Rivera' }, courses: [{ id: '6', title: 'Biology' }], courseId: '6', coursesLoading: false, coursesError: '', theme: 'dark', onCourseChange() {}, onThemeChange() {}, onChatHome() {}, onSignOut() {}, signingOut: false, sessionNotice: '' })
async function openOverview() {
  window.history.replaceState(null, '', '/?view=study&tab=Overview&source=7')
  await mount(StudyWorkspace, workspaceProps())
}
test('Overview starts calmly without mastery panels, reminders or hidden-tool clutter', async () => {
  await openOverview()
  assert.equal(document.querySelector('h1').textContent, 'Your study space')
  assert.equal(document.querySelector('.study-home-cards').children.length, 2)
  assert.equal(document.querySelector('#study-home-tools').hidden, true)
  assert.equal(document.querySelector('#sw-extra-tools').hidden, true)
  assert.equal(document.querySelector('.sw-material-manage').open, false)
  assert.equal(document.querySelector('.sw-learning'), null)
  assert.equal(document.querySelector('.study-rhythm'), null)
  assert(!requests.some(r => r.path === '/study/learning'))
  assert(!requests.some(r => r.method === 'POST'))
  assert(!visibleText().includes('Your understanding of this material'))
  assert(!visibleText().includes('Summary'))
})
test('Overview primary action and secondary tools preserve the selected material', async () => {
  await openOverview()
  await click(button('Ask Aura'))
  assert.equal(document.querySelector('h1').textContent, 'Ask Aura')
  assert.equal(new URL(window.location.href).searchParams.get('source'), '7')
  await click(button('Overview'))
  await click(button('More tools +'))
  assert.equal(document.querySelector('#study-home-tools').hidden, false)
  await click(document.querySelector('#study-home-tools button:nth-child(2)'))
  assert.equal(document.querySelector('h1').textContent, 'Summary')
  assert.equal(new URL(window.location.href).searchParams.get('source'), '7')
  assert.equal(document.querySelector('#sw-extra-tools').hidden, false)
  assert(!requests.some(r => r.method === 'POST'))
})
test('Progress retains mastery and optional reminders after their removal from Overview', async () => {
  await openOverview()
  await click(button('More study tools'))
  await click(document.querySelector('#sw-extra-tools button:last-child'))
  assert.equal(document.querySelector('h1').textContent, 'Progress')
  assert.match(visibleText(), /Your understanding of this material/)
  assert(button('Start diagnostic'))
  assert.equal(document.querySelector('.sw-disclosure').open, false)
  assert(!visibleText().includes('Your study rhythm'))
  assert(requests.some(r => r.path === '/study/learning' && r.query.includes('source_id=7')))
})
test('Overview opens the exact saved artifact without generating new output', async () => {
  savedArtifacts = [{ id: 'notes-a', kind: 'notes', created_at: '2026-10-24T08:00:00Z', result: null,
    payload: { source_id: 7, course_id: 6, source_title: 'Biological membranes.ppt', focus: 'Membrane structure', items: [{ id: 'n1', text: 'Membranes contain lipids.', citation_ids: [1] }], citations: [] } }]
  await openOverview()
  assert.match(document.querySelector('.study-home-saved').textContent, /Membrane structure/)
  await click(document.querySelector('.study-home-saved>div>button'))
  assert.equal(document.querySelector('h1').textContent, 'Notes')
  assert.match(document.querySelector('.sw-reading').textContent, /Membranes contain lipids/)
  assert.equal(document.querySelector('[aria-label="Saved version"]').getAttribute('role'), 'combobox')
  assert(!requests.some(r => r.method === 'POST'))
})
test('Overview disables study actions until the selected upload is ready', async () => {
  materials[0].status = 'processing'
  await openOverview()
  assert(button('Ask Aura').disabled)
  assert(button('Make a study plan').disabled)
  assert.match(document.querySelector('.study-home-hint').textContent, /being prepared/)
})


test('Stop aborts Chat, restores the editable question and ignores a late answer', async()=>{
  const original=globalThis.fetch;let resolveAnswer,signal
  globalThis.fetch=async(url,options={})=>new URL(url).pathname==='/chat' ? new Promise(resolve=>{resolveAnswer=resolve;signal=options.signal}) : original(url,options)
  await mount(ChatHome,homeProps());await input(document.querySelector('#aura-question'),'Explain hash tables')
  await click(document.querySelector('[aria-label="Send question"]'))
  assert(document.querySelector('[aria-label="Stop generation"]'))
  await click(document.querySelector('[aria-label="Stop generation"]'));assert(signal.aborted)
  await act(async()=>{resolveAnswer(new Response(JSON.stringify({answer:'LATE ANSWER',sources:[]})));await tick();await tick()})
  assert(!visibleText().includes('LATE ANSWER'));assert.match(visibleText(),/Stopped/)
  assert.equal(document.querySelector('#aura-question').value,'Explain hash tables')
})
test('Esc stops a study request without removing the previous saved artifact',async()=>{
  const original=globalThis.fetch;let signal,resolveWork
  globalThis.fetch=async(url,options={})=>new URL(url).pathname==='/study/tools' ? new Promise(resolve=>{signal=options.signal;resolveWork=resolve}) : original(url,options)
  window.history.replaceState(null,'','/?view=study&tab=Notes&source=7')
  await mount(StudyWorkspace,{user:{id:'1',fullName:'Sam'},courses:[],courseId:'6',theme:'dark',onCourseChange(){},onThemeChange(){},onChatHome(){},onSignOut(){}})
  await click(button('Generate'))
  await act(async()=>{window.dispatchEvent(new window.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));await tick()})
  assert(signal.aborted);assert.match(visibleText(),/Stopped/)
  await act(async()=>{resolveWork(new Response('{}'));await tick()})
  assert(!visibleText().includes('invalid JSON'))
})
test('material selection keeps five-item limit, disables processing and saves reusable study sets',async()=>{
  materials=Array.from({length:7},(_,i)=>({source_id:7+i,source_name:`Lecture ${i+1}.pdf`,source_type:'pdf',status:i===6?'processing':'success'}))
  await mount(ChatHome,homeProps())
  assert(document.querySelectorAll('.aura-material-option input')[6].disabled)
  await click(document.querySelector('.aura-selection-toolbar input'))
  assert.equal(document.querySelectorAll('.aura-material-option input:checked').length,5)
  await input(document.querySelector('.aura-set-editor input'),'DBMS revision');await click(button('Save set'))
  assert.match(document.querySelector('.aura-study-sets').textContent,/DBMS revision/)
  await click(document.querySelector('.aura-selection-toolbar input'))
  await click(document.querySelector('.aura-set-select'));assert.equal(document.querySelectorAll('.aura-material-option input:checked').length,5)
  assert.match(visibleText(),/one material at a time/)
  assert(!requests.some(r=>r.path==='/chat'))
})
test('styled menus support arrows, Enter and Escape without changing a value on dismissal',async()=>{
  await mount(AgentPanel,props())
  const trigger=document.querySelector('[aria-label="Plan depth"]')
  await click(trigger)
  await act(async()=>{trigger.dispatchEvent(new window.KeyboardEvent('keydown',{key:'End',bubbles:true}));await tick()});
  await act(async()=>{trigger.dispatchEvent(new window.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));await tick()})
  assert.match(trigger.textContent,/Deep/)
  await click(trigger)
  await act(async()=>{trigger.dispatchEvent(new window.KeyboardEvent('keydown',{key:'Home',bubbles:true}));trigger.dispatchEvent(new window.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));await tick()})
  assert.match(trigger.textContent,/Deep/);assert.equal(trigger.getAttribute('aria-expanded'),'false')
})

test('advertised generation jobs use server cancellation and keep material arrays',async()=>{
  const original=globalThis.fetch;let launch,stopped=false
  globalThis.fetch=async(url,options={})=>{
    const path=new URL(url).pathname
    if(path==='/study/capabilities')return new Response(JSON.stringify({multi_chat:true,multi_study:true,multi_agents:true,study_jobs:true}))
    if(path==='/study/generation-jobs') {launch=JSON.parse(options.body);return new Response(JSON.stringify({id:'job-a',course_id:6,state:'queued',result:null}))}
    if(path==='/study/generation-jobs/job-a/cancel'){stopped=true;return new Response(JSON.stringify({id:'job-a',course_id:6,state:'cancelled',result:null}))}
    if(path==='/study/generation-jobs/job-a')return new Response(JSON.stringify({id:'job-a',course_id:6,state:stopped?'cancelled':'running',result:null}))
    return original(url,options)
  }
  materials.push({source_id:8,source_name:'Transcript.pdf',source_type:'pdf',status:'success'})
  await mount(ChatHome,homeProps())
  await click(document.querySelector('.aura-selection-toolbar input'))
  await input(document.querySelector('#aura-question'),'Compare the two materials')
  await click(document.querySelector('[aria-label="Send question"]'))
  assert.deepEqual(launch.payload.material_ids,[7,8]);assert.equal(launch.operation,'chat')
  await click(document.querySelector('[aria-label="Stop generation"]'))
  assert(stopped);assert.match(visibleText(),/Cancelled/)
  assert(!requests.some(r=>r.path==='/chat'))
})

test('refresh resumes a saved generation by ID without starting a second job',async()=>{
  localStorage.setItem('aura.chat.v1:1:6:generation',JSON.stringify({job:{id:'saved-job',course:'6',operation:'chat',payload:{question:'Saved question',course_id:6,source_id:7,material_ids:[7]}}}))
  const original=globalThis.fetch;let reads=0,creates=0
  globalThis.fetch=async(url,options={})=>{
    const path=new URL(url).pathname
    if(path==='/study/capabilities')return new Response(JSON.stringify({multi_chat:true,study_jobs:true}))
    if(path==='/study/generation-jobs') {creates++;throw new Error('Must not create a duplicate job')}
    if(path==='/study/generation-jobs/saved-job'){reads++;return new Response(JSON.stringify({id:'saved-job',course_id:6,state:'completed',result:{answer:'Restored explanation',sources:[],citation_validation:{valid:false}}}))}
    return original(url,options)
  }
  await mount(ChatHome,homeProps());await act(async()=>{await tick();await tick()})
  assert.equal(creates,0);assert.equal(reads,1);assert.match(visibleText(),/Restored explanation/)
  assert.match(document.querySelector('.aura-using').textContent,/Biological membranes/)
})

test('a stopped streamed answer preserves received text with no invented citations',async()=>{
  const original=globalThis.fetch
  globalThis.fetch=async(url,options={})=>{
    if(new URL(url).pathname==='/chat')return new Response(new ReadableStream({start(controller){controller.enqueue(new TextEncoder().encode('event: delta\r\ndata: {"text":"A hash table maps keys to positions."}\r\n\r\n'))}}),{headers:{'Content-Type':'text/event-stream'}})
    return original(url,options)
  }
  await mount(ChatHome,homeProps());await input(document.querySelector('#aura-question'),'Explain hash tables')
  await click(document.querySelector('[aria-label="Send question"]'))
  assert.match(visibleText(),/A hash table maps keys to positions/)
  await click(document.querySelector('[aria-label="Stop generation"]'))
  assert.match(visibleText(),/Stopped/);assert.match(visibleText(),/A hash table maps keys to positions/)
  assert.equal(document.querySelectorAll('.aura-home__citation').length,0)
  assert.match(localStorage.getItem('aura.chat.v1:1:6'),/A hash table maps keys to positions/)
})


// Study v2 additive contracts use authored API fixtures, never a real learner/model.
const v2Artifact=(kind,items,extra={})=>({id:'v2-artifact',kind,created_at:'2026-10-24T10:00:00Z',payload:{generation_version:2,source_id:7,material_ids:[7,9],source_title:'Membranes.pdf',items,citations:[{id:1,source_id:7,title:'Membranes.pdf',location:'Page 2',excerpt:'Authored source facts'}],coverage:{covered:1,total:1,missing_sections:[]},...extra}})
const v2Props=(kind,active)=>({courseId:'6',materialIds:['7','9'],kind,ready:true,storageKey:'v2:test',focus:'',active,onArtifact(){},onOpen(){},onUpdated(){}})
const respond=value=>new Response(JSON.stringify(value),{status:200,headers:{'Content-Type':'application/json'}})
const settleV2=()=>act(async()=>{await new Promise(resolve=>setTimeout(resolve,290));await tick()})
test('v2 notes have section controls instead of an item count, with editing and export',async()=>{
 let saved
 const active=v2Artifact('notes',[{id:'section-1',title:'Membrane structure',text:'Source-backed notes about membrane structure and proteins.',citation_ids:[1]}])
 globalThis.fetch=async(url,options={})=>{saved=JSON.parse(options.body);return respond(active)}
 await mount(StudyToolV2,v2Props('notes',active))
 assert.equal(document.querySelector('input[type=number]'),null)
 assert.match(document.body.textContent,/Covers all sections/)
 assert(button('Download Markdown'));assert(button('Print / Save PDF'))
 await click(button('Edit notes'));await input(document.querySelector('textarea'),'My revised study notes about the membrane.')
 await click(button('Save notes'));assert.equal(saved.sections[0].text,'My revised study notes about the membrane.')
 assert.match(document.body.textContent,/Notes saved/)
})
test('v2 assessment uses multiple-select checkboxes, question navigation and saved attempts',async()=>{
 const questions=[1,2].map(n=>({id:'q'+n,kind:'multiple_select',prompt:'Select supported facts '+n,topic:'Membranes',citation_ids:[1],options:['A','B','C','D'].map(id=>({id,text:'Statement '+id}))}))
 let draft={id:'attempt-a',revision:0,answers:{},position:0,scoring:'partial',resume_token:'authored-token'},saved
 globalThis.fetch=async(url,options={})=>{
  if(String(url).includes('capacity'))return respond({max_supported:6,reason:'Authored topics'})
  if(options.method==='PATCH'){saved=JSON.parse(options.body);draft={...draft,...saved,revision:1};return respond(draft)}
  return respond(draft)
 }
 await mount(StudyToolV2,v2Props('assessment',v2Artifact('assessment',questions)))
 await settleV2();assert.match(document.body.textContent,/Select all that apply/)
 assert.equal(document.querySelectorAll('.v2-test input[type=checkbox]').length,4)
 await click(document.querySelector('.v2-test input[type=checkbox]'))
 await click(button('Next'));assert.match(document.querySelector('.v2-test h2').textContent,/facts 2/)
 await click(button('Save & resume later'));assert.deepEqual(saved.answers.q1,['A']);assert.equal(saved.position,1)
 assert.equal(saved.resume_token,'authored-token');assert.equal(saved.scoring,'partial')
 assert.equal(document.querySelector('input[type=number]').max,'50')
 assert.match(document.body.textContent,/supports about 6 distinct questions/)
 await mount('div');await mount(StudyToolV2,v2Props('assessment',v2Artifact('assessment',questions)))
 assert.match(document.querySelector('.v2-test h2').textContent,/facts 2/)
 await click(button('Previous'));assert.equal(document.querySelector('.v2-test input[type=checkbox]').checked,true)
})
test('v2 flashcards have 100-card cap, cloze reveal, source names and append action',async()=>{
 globalThis.fetch=async()=>respond({max_supported:8,reason:'Authored estimate'})
 await mount(StudyToolV2,v2Props('flashcards',v2Artifact('flashcards',[{id:'c1',card_type:'cloze',question:'Membranes contain a {{c1::bilayer}}.',answer:'bilayer',citation_ids:[1]}])))
 assert.equal(document.querySelector('input[type=number]').max,'100')
 assert(button('100'));assert(button('Generate more'));assert.match(document.querySelector('.v2-cards h2').textContent,/_____/)
 assert(button('Membranes.pdf · Page 2'))
 await click(button('Reveal answer'));assert.match(document.body.textContent,/bilayer/)
 assert(button('Study again'));assert(button('I remembered'))
})
test('v2 Progress shows unknown metrics honestly and renders measured heatmap/history',async()=>{
 const data={overall_mastery:null,study_streak:0,quiz_average:null,time_this_week_seconds:null,cards_due:0,topics:[{topic:'Hashing',mastery:.32,evidence_count:3,last_practiced_at:'2026-10-24'}],recommended_next:null,quizzes:[],history:[{label:'Today',items:[{id:'quiz-a',kind:'quiz',title:'Hashing practice',created_at:'2026-10-24T10:00:00Z',result:{score:50}}]}],notice:'Estimated from checked answers.'}
 globalThis.fetch=async()=>respond(data)
 let selected
 await mount(ProgressV2,{courseId:'6',onPractice:(...args)=>{selected=args}})
 assert.match(document.body.textContent,/Not measured yet/);assert.match(document.body.textContent,/Not recorded/)
 assert.match(document.querySelector('.v2-topic-tile').textContent,/32%/)
 await click(document.querySelector('.v2-topic-tile'));assert.deepEqual(selected,['Assessment','Hashing'])
 await click(button('History'));assert.match(document.body.textContent,/Today.*Hashing practice/);assert.match(document.body.textContent,/50%/)
})
test('v2 Today shows seven real completion dots and moves unfinished tasks to today',async()=>{
 let moved
 globalThis.fetch=async(url,options={})=>{
  if(String(url).includes('/date?')){moved=JSON.parse(options.body);return respond({})}
  if(String(url).includes('/week?'))return respond({days:Array.from({length:7},(_,i)=>({date:'2026-10-'+String(18+i),completed:i===3?2:0}))})
  return respond({items:[{id:'task-a',title:'Review hashing',details:'Recall one idea.',done:false,scheduled_for:null}]})
 }
 await mount(TodayV2,{courseId:'6'})
 assert.equal(document.querySelectorAll('.v2-week-strip button').length,7)
 await click(button('Move to today'));assert.match(moved.scheduled_for,/^\d{4}-\d{2}-\d{2}$/)
 assert(button('Yesterday'));assert(button('Tomorrow'))
})
test('v2 Previous plans are collapsed, paginated and can be archived',async()=>{
 let archived=false
 globalThis.fetch=async(url,options={})=>{
  if(options.method==='PATCH'){archived=true;return respond({})}
  const more=String(url).includes('cursor=5')
  return respond({current:baseRun({id:'current'}),items:[baseRun({id:more?'older-b':'older-a',request:{goal:more?'Older plan B':'Older plan A'}})],next_cursor:more?null:'5'})
 }
 await mount(PreviousPlansV2,{courseId:'6',selectedId:'current',onOpen(){},onNew(){}})
 await settleV2();assert.equal(document.querySelector('details').open,false)
 document.querySelector('details').open=true
 await click(button('Show more'));await settleV2();assert.match(document.body.textContent,/Older plan B/)
 await click(document.querySelector('[aria-label="Archive Older plan A"]'));assert(archived)
})
