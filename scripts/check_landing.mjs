// Test-only browser checks; no authentication bypass or provider calls.
import assert from 'node:assert/strict'
import {createRequire} from 'node:module'
import {mkdir,writeFile} from 'node:fs/promises'
const require=createRequire(import.meta.url)
const {chromium}=require(require.resolve('playwright',{paths:[process.env.AURA_UI_TEST_MODULES||process.cwd()]}))
const base=new URL(process.argv[2]);assert(['localhost','127.0.0.1'].includes(base.hostname)||base.protocol==='https:')
const browser=await chromium.launch({headless:true,...(process.env.AURA_LAYOUT_CHROMIUM?{executablePath:process.env.AURA_LAYOUT_CHROMIUM,args:['--no-sandbox','--disable-dev-shm-usage']}: {})})
const output=process.env.AURA_LANDING_OUTPUT||'/tmp/aura-landing-results';await mkdir(output,{recursive:true})
const report=[]
try{
 for(const width of [360,390,768,1280,1920,2560])for(const theme of ['light','dark']){
  const context=await browser.newContext({viewport:{width,height:1000},reducedMotion:'reduce'});await context.addInitScript(theme=>localStorage.setItem('aura.theme',theme),theme)
  const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));const requests=[];page.on('request',r=>{if(r.url().includes('/api/'))requests.push(r.url())})
  await page.goto(base.href);await page.locator('.landing-hero h1').waitFor();await page.evaluate(()=>document.fonts.ready)
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'No horizontal page overflow')
  assert.equal(await page.locator('.aura-home').count(),0)
  await page.getByRole('button',{name:'Watch the 3-minute demo'}).click();await page.getByRole('dialog').waitFor();await page.keyboard.press('Escape');assert.equal(await page.getByRole('dialog').count(),0);assert.equal(await page.evaluate(()=>document.activeElement.textContent.trim()),'Watch the 3-minute demo')
  await page.getByRole('button',{name:'Beyond the material',exact:true}).click();assert(await page.locator('#honesty .landing-background').isVisible());await page.locator('#honesty').getByRole('button',{name:'Sample study notes, slide 12'}).click();await page.getByRole('dialog').waitFor();await page.keyboard.press('Escape')
  if(width<1000){await page.getByRole('button',{name:'Open menu'}).click();await page.getByRole('dialog').waitFor();await page.keyboard.press('Tab');assert(await page.evaluate(()=>!!document.activeElement.closest('dialog')));await page.keyboard.press('Escape')}
  await page.getByRole('button',{name:`Switch to ${theme==='dark'?'light':'dark'} theme`}).click();assert.equal(await page.locator('html').getAttribute('data-theme'),theme==='dark'?'light':'dark');await page.getByRole('button',{name:`Switch to ${theme} theme`}).click()
  await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:`${output}/landing-${width}-${theme}.png`,fullPage:true});if([390,1920].includes(width))await page.screenshot({path:`${output}/hero-${width}-${theme}.png`})
  await page.goto(new URL('/judges',base).href);await page.getByRole('heading',{name:'A minute inside Aura.'}).waitFor()
  await page.goto(new URL('/login',base).href);await page.getByRole('button',{name:'Log in',exact:true}).first().waitFor();assert.equal(await page.locator('.aura-landing').count(),0)
  assert.deepEqual(errors,[]);assert.deepEqual(requests,[],'Public examples do not call private APIs');report.push({width,theme,passed:true});await context.close()
 }
 const animated=await browser.newContext({viewport:{width:1280,height:900},reducedMotion:'no-preference'});const motionPage=await animated.newPage();await motionPage.goto(base.href);await motionPage.locator('#features').scrollIntoViewIfNeeded();await motionPage.waitForFunction(()=>document.querySelector('#features')?.classList.contains('has-entered'));assert.equal(await motionPage.locator('#features').evaluate(e=>getComputedStyle(e).visibility),'visible');await animated.close();
 await writeFile(`${output}/results.json`,JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2))
}finally{await browser.close()}
