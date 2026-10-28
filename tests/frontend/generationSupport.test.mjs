import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from '../../node_modules/esbuild/lib/main.js'
const result=await build({entryPoints:['src/services/generationSupport.ts'],bundle:true,platform:'node',format:'esm',define:{'import.meta.env.VITE_API_BASE_URL':'"http://127.0.0.1:8000"'},write:false})
const {generationSupport}=await import('data:text/javascript;base64,'+Buffer.from(result.outputFiles[0].text).toString('base64'))
test('only a missing capability endpoint uses legacy compatibility; backend failures stay visible',async()=>{
 const previous=globalThis.fetch
 try{
  globalThis.fetch=async()=>new Response(JSON.stringify({detail:'Not Found'}),{status:404,headers:{'Content-Type':'application/json'}})
  assert.equal((await generationSupport()).study_jobs,false)
  for(const status of [401,403,500,503]){
   globalThis.fetch=async()=>new Response(JSON.stringify({detail:'Unavailable'}),{status,headers:{'Content-Type':'application/json'}})
   await assert.rejects(generationSupport(),error=>error.status===status)
  }
  globalThis.fetch=async()=>{throw Error('offline')}
  await assert.rejects(generationSupport())
 }finally{globalThis.fetch=previous}
})
