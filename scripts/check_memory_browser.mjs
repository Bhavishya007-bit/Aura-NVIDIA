// Authored browser fixtures only: never calls a live account or model.
// Browser-only layout fixtures. Routes are intercepted in this test context;
// production authentication and the real backend are never bypassed or changed.
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
const require = createRequire(import.meta.url)
const { chromium } = require(require.resolve('playwright', { paths: [process.env.AURA_UI_TEST_MODULES || process.cwd()] }))
const base = new URL(process.argv[2] || '')
assert(base.protocol === 'https:' || base.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(base.hostname), 'Use HTTPS or a local test server.')
const output = resolve(process.env.AURA_LAYOUT_OUTPUT || '/tmp/aura-layout-results')
await mkdir(output, { recursive: true })
const launch = process.env.AURA_LAYOUT_CHROMIUM ? { executablePath: process.env.AURA_LAYOUT_CHROMIUM, args: ['--no-sandbox', '--disable-dev-shm-usage'] } : {}
const browser = await chromium.launch({ headless: true, ...launch })
const materials = Array.from({ length: 5 }, (_, i) => ({ source_id: i + 7, source_name: i ? `Additional study notes ${i}.pdf` : 'Aura Demo Study Notes.pdf', source_type: 'pdf', status: 'success' }))
const lesson = '### From your material\n\n**Separate chaining** stores colliding entries together. **Open addressing** probes other slots. This is authored layout test text, not a generated answer.\n\n' +
  'A readable explanation with a clear sequence of steps and an example. '.repeat(18) +
  '\n\n```python\n' + 'long_variable_name_'.repeat(45) + '\n```\n\n| Method | Storage |\n| --- | --- |\n| Separate chaining | Collection at a slot |\n| Open addressing | Other slots |'
const entries = Array.from({ length: 10 }, (_, i) => ({ message: { id: `layout-${i}`, role: i % 2 ? 'tutor' : 'student', content: i % 2 ? lesson : 'Compare separate chaining and open addressing with an example.', citationIds: [], isDemo: false }, citations: [], scope: '7' }))
const report = []
const unexpected = new Set()

async function fixture(context, theme) {
  await context.addInitScript(({ entries, theme }) => {
    sessionStorage.setItem('aura.authToken', 'synthetic-layout-test-token')
    localStorage.setItem('aura.theme', theme)
    localStorage.setItem('aura.navigation.v1:1', JSON.stringify({ homeOpen: true, courseId: '6' }))
    localStorage.setItem('aura.chat.v1:1:6', JSON.stringify({ entries, materialIds: ['7'] }))
    localStorage.setItem('aura.study.v1:1:6', JSON.stringify({ tab: 'Tutor', materialIds: ['7'], sourceId: '7', chats: { '7': entries.map(e => ({ role: e.message.role === 'student' ? 'user' : 'assistant', text: e.message.content })) } }))
  }, { entries, theme })
  await context.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api/, '')
    let value
    if (route.request().method() !== 'GET') { unexpected.add(`${route.request().method()} ${path}`); return route.fulfill({ status: 405, json: { detail: 'Layout fixture is read-only.' } }) }
    if (path === '/auth/me') value = { student_id: 1, name: 'Aura Demo Learner', email: 'judge@example.test', is_demo: true }
    else if (path === '/courses') value = { courses: [{ course_id: 6, course_name: 'Demo study workspace' }] }
    else if (path === '/study/capabilities') value = { multi_chat: true, multi_study: true, multi_agents: true, study_jobs: true, study_v2: true }
    else if (path.startsWith('/study/materials')) value = { sources: materials }
    else if (path === '/study/artifacts') value = { artifacts: [] }
    else if (path === '/preparation-jobs') value = { jobs: [] }
    else if (path === '/agents/capabilities') value = { web_search: false, assessment_agent: true, code_execution: false, code_backend: null }
    else if (path === '/agents/memory') value = { enabled: true, items: [] }
    else if (path === '/agents/runs' || path === '/agents/tasks') value = { items: [] }
    else if (path === '/agents/plans') value = { items: [], next_cursor: null }
    else if (path === '/study/progress') value = { assessment_count: 0, question_count: 0, topics: [], recent_results: [] }
    else if (path === '/study/progress/summary') value = { overall_mastery: null, study_streak: 0, quiz_average: null, time_this_week_seconds: null, cards_due: 0, recommended_next: null, topics: [], quizzes: [], history: [], notice: 'Authored layout fixture.' }
    else if (path === '/study/capacity') value = { max_supported: 20, reason: 'Authored layout fixture.' }
    else if (path === '/study/learning') value = { model: 'fixture', topics: [], diagnostic_recommended: false, notice: 'Authored layout fixture.' }
    else if (path === '/study/rhythm') value = { settings: { enabled: false, timezone: 'UTC', daily_hour: 9 }, reviews: [], digests: [], notice: 'In-app reminders.' }
    else if (path === '/study/evaluation') value = { mode: 'controlled_offline', checks: [], calibration: { reviewed: 0, required: 30, ready: false }, your_runs: { completed: 0, failed: 0 }, limitations: [] }
    else { unexpected.add(path); return route.fulfill({ status: 404, json: { detail: 'No layout fixture for this route.' } }) }
    await route.fulfill({ json: value })
  })
}


try {
 for (const width of [390, 1280, 2560]) {
  const context=await browser.newContext({viewport:{width,height:1000},reducedMotion:'reduce'});
  await fixture(context,'dark');
  let saved;
  await context.route('**/api/agents/memory*',async route=>{
   if(route.request().method()==='POST') {saved=route.request().postDataJSON();return route.fulfill({json:{id:'fixture-memory',record:saved,updated_at:'2026-10-28'}})}
   return route.fulfill({json:{enabled:true,items:[]}})
  });
  const page=await context.newPage();
  await page.goto(new URL('/?view=study',base).href);
  const account=page.locator('.aura-account summary:visible').first();
  await account.click();
  await page.getByRole('button',{name:'What Aura remembers',exact:true}).click({timeout:3000});
  const field=page.locator('.aura-memory textarea');
  await field.waitFor();
  assert(await field.evaluate(el=>document.activeElement===el),'Memory opens with an editable text caret');
  await field.click();await field.pressSequentially('Explain listeners with examples');
  assert.equal(await field.inputValue(),'Explain listeners with examples');
  assert(await field.evaluate(el=>getComputedStyle(el).cursor==='text'),'Text cursor is visible');
  await page.locator('.aura-memory__fields select').first().selectOption('beginner');
  await page.getByRole('button',{name:'Save memory',exact:true}).click();
  await page.getByRole('status').filter({hasText:'Noted:'}).waitFor();
  assert.equal(saved.text,'Explain listeners with examples');assert.equal(saved.depth,'beginner');
  await page.keyboard.press('Escape');
  await page.locator('.aura-memory').waitFor({state:'detached'});
  await page.waitForFunction(()=>document.activeElement?.matches('.aura-account summary'));
  assert(await account.evaluate(el=>document.activeElement===el),'Focus returns to account menu');
  console.log(`Memory click/type/save/Escape: ${width}px OK`);
  await context.close();
 }
} finally {await browser.close()}
