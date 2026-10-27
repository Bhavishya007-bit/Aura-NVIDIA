// Optional test-only Playwright. No browser state or credentials are committed.
import { createRequire } from 'node:module'
const require=createRequire(import.meta.url)
const {chromium}=require(require.resolve('playwright',{paths:[process.env.AURA_UI_TEST_MODULES||process.cwd()]}))
const url=new URL(process.argv[2]||'')
if(url.protocol!=='https:'&&!['localhost','127.0.0.1'].includes(url.hostname))throw Error('Use an HTTPS public URL.')
const browser=await chromium.launch({headless:true})
try{
 const context=await browser.newContext()
 const page=await context.newPage()
 await page.goto(url.href,{waitUntil:'networkidle'})
 await page.getByRole('link',{name:'Sign in',exact:true}).first().click()
 await page.getByRole('button',{name:'Log in',exact:true}).first().waitFor()
 const response=await context.request.get(new URL('/api/auth/me',url).href)
 if(response.status()!==401)throw Error('Signed-out account access was not blocked.')
 console.log('PASS: Fresh browser opens the landing page and reaches sign-in and private API rejects anonymous access.')
 await context.close()
}finally{await browser.close()}
