import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from '../../node_modules/esbuild/lib/main.js'
const bundled=await build({entryPoints:['src/services/preparationApi.ts'],bundle:true,platform:'node',format:'esm',define:{'import.meta.env.VITE_API_BASE_URL':'"http://127.0.0.1:8000"'},write:false})
const {uploadValidationError,preparationLabel,queueMaterials}=await import('data:text/javascript;base64,'+Buffer.from(bundled.outputFiles[0].text).toString('base64'))
test('upload limit accepts the boundary and explains how to fix oversized videos',()=>{
 assert.equal(uploadValidationError({name:'lesson.mp4',size:100*1024*1024}),null)
 assert.match(uploadValidationError({name:'lesson.mp4',size:100*1024*1024+1}),/Compress it, split it/)
 assert.match(uploadValidationError({name:'empty.pdf',size:0}),/empty/)
})
test('invalid uploads are rejected before contacting the server',async()=>{
 const before=globalThis.fetch;let calls=0;globalThis.fetch=()=>{calls++;throw Error('Unexpected request')}
 try{const entries=await queueMaterials('6',[{name:'large.mp4',size:101*1024*1024}],()=>{},()=>{});assert.equal(calls,0);assert.equal(entries[0].state,'failed');assert.match(entries[0].error,/100 MiB/)}finally{globalThis.fetch=before}
})
test('old and current video progress remain labelled as video',()=>{
 assert.equal(preparationLabel({filename:'lesson.mp4',stage:'reading_image'}),'Reading a video frame')
 assert.equal(preparationLabel({filename:'lesson.mp4',stage:'reading_video_frames'}),'Reading video frames')
 assert.equal(preparationLabel({filename:'diagram.jpg',stage:'reading_image'}),'Reading your image')
})
