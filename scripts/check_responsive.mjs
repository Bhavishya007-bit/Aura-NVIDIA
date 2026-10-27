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

async function bounds(page, selector, label) {
  const box = await page.locator(selector).boundingBox()
  const viewport = page.viewportSize()
  assert(box && box.width > 0 && box.height > 0, `${label}: visible layout`)
  assert(box.x >= -1 && box.x + box.width <= viewport.width + 1, `${label}: fits viewport horizontally (${JSON.stringify(box)})`)
  return box
}

async function check(page, width, height, theme) {
  await page.goto(base.href)
  await page.locator('.aura-home--conversation').waitFor()
  await page.locator('.aura-using .aura-material-chip').first().waitFor()
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.locator('.aura-home__conversation').evaluate(e => { e.scrollTop = e.scrollHeight })
  const main = await bounds(page, '.aura-home__main', 'Chat main')
  if (width >= 1920) assert(main.width >= 1100, `Desktop chat uses available width (${main.width})`)
  const font = await page.locator('.aura-teaching-text').first().evaluate(e => parseFloat(getComputedStyle(e).fontSize))
  assert(font >= 16, `Readable chat font: ${font}`)
  if (width >= 2560) assert(font >= 17, `Large monitor font: ${font}`)
  const input = await bounds(page, '.aura-home__composer', 'Chat composer')
  if (height > 560) assert(input.y + input.height <= height + 1, 'Chat composer stays on screen')
  else {
    await page.locator('.aura-home__composer').scrollIntoViewIfNeeded()
    const reachable = await page.locator('.aura-home__composer').boundingBox()
    assert(reachable.y >= -1 && reachable.y + reachable.height <= height + 1, 'Short-window chat composer is reachable by scrolling')
  }
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'Chat has no page-wide horizontal scroll')
  await page.locator('.aura-home__materials > summary').click()
  await bounds(page, '.aura-home__materials', 'Expanded materials')
  await page.locator('.aura-home__materials').getByLabel('Select all', { exact: true }).check()
  assert.equal(await page.locator('.aura-using .aura-material-chip').count(), 5, 'All selected materials fit the shared controls')
  if (height > 560) {
    const composer = await page.locator('.aura-home__composer').boundingBox()
    assert(composer.y + composer.height <= height + 1, 'Expanded material controls leave the composer visible')
  }
  await page.locator('.aura-home__materials').evaluate(e => { e.scrollTop = e.scrollHeight })
  await page.locator('.aura-home__materials > summary').click()
  await page.locator('#aura-question').focus()
  assert(await page.locator('#aura-question').evaluate(e => e === document.activeElement), 'Composer accepts keyboard focus')
  if (width === 2560 || width === 390) await page.screenshot({ path: resolve(output, `chat-${width}-${theme}.png`), fullPage: true })

  for (const tab of ['Tutor', 'Overview', 'Notes', 'Summary', 'Flashcards', 'Assessment', 'Progress', 'Agents']) {
    await page.goto(new URL(`?view=study&tab=${tab}&source=7`, base).href)
    await page.locator(`.aura-study[data-tab="${tab}"]`).waitFor()
    await page.locator('.aura-material-chip').first().waitFor()
    await bounds(page, '.sw-main', `${tab} main`)
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `${tab}: no page-wide horizontal scroll`)
    if (tab === 'Tutor') {
      const composer = await bounds(page, '.sw-composer', 'Workspace composer')
      if (height > 560) assert(composer.y + composer.height <= height + 1, `Workspace composer stays on screen (${composer.y + composer.height} vs ${height})`)
      else {
        await page.locator('.sw-composer').scrollIntoViewIfNeeded()
        const reachable = await page.locator('.sw-composer').boundingBox()
        assert(reachable.y >= -1 && reachable.y + reachable.height <= height + 1, 'Short-window workspace composer is reachable by scrolling')
      }
      if (width <= 800) {
        await page.locator('.sw-material-toggle').click()
        await bounds(page, '.sw-materials', 'Mobile materials drawer')
        await page.keyboard.press('Escape')
        assert.equal(await page.locator('.aura-study').getAttribute('data-materials-collapsed'), 'true', 'Keyboard closes the mobile materials drawer')
      }
      if (width === 2560 || width === 390) await page.screenshot({ path: resolve(output, `tutor-${width}-${theme}.png`), fullPage: true })
    }
  }
  report.push({ width, height, theme, chatWidth: main.width, readingFont: font, passed: true })
}

try {
  const signedOut = await browser.newContext()
  const login = await signedOut.newPage()
  await login.goto(new URL('/login', base).href)
  await login.getByRole('button', { name: 'Log in', exact: true }).first().waitFor()
  assert.equal(await login.locator('.aura-home').count(), 0, 'Signed-out users still see authentication')
  await signedOut.close()
  for (const [width, height, theme] of [[3840, 2160, 'light'], [2560, 1440, 'light'], [1920, 1080, 'light'], [1280, 800, 'light'], [768, 1024, 'light'], [390, 844, 'light'], [320, 700, 'light'], [640, 360, 'light'], [2560, 1440, 'dark'], [390, 844, 'dark']]) {
    const context = await browser.newContext({ viewport: { width, height }, reducedMotion: 'reduce' })
    await fixture(context, theme)
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    try { await check(page, width, height, theme) }
    catch (error) {
      await page.screenshot({ path: resolve(output, `failure-${width}.png`), fullPage: true })
      await writeFile(resolve(output, 'failure.html'), await page.content())
      console.error({ width, height, errors, unexpected: [...unexpected] })
      throw error
    }
    assert.deepEqual(errors, [], 'No browser runtime errors')
    await context.close()
  }
  assert.deepEqual([...unexpected], [], 'Layout fixture covers every requested route')
  await writeFile(resolve(output, 'results.json'), JSON.stringify(report, null, 2))
  console.log(JSON.stringify(report, null, 2))
} finally { await browser.close() }
