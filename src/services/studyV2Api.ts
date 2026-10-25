import { requestApi, requireRecord } from './apiClient'
import { generationRequest } from './generationJobs'
import type { JobOptions } from './generationJobs'
import { artifact } from './studyToolsApi'
import type { Artifact } from './studyToolsApi'
export type V2Settings = {generation_version:2;course_id:number;source_id?:number;material_ids:number[];kind:'assessment'|'flashcards'|'notes';count:number;focus:string;difficulty:'easy'|'mixed'|'hard';type_mix:Record<string,number>;scoring:'partial'|'all_or_nothing';card_type:'term_definition'|'question_answer'|'cloze';append_to_deck?:string;depth:'concise'|'standard'|'comprehensive';style:'outline'|'study_guide'|'cornell';include:string[]}
export type Capacity = {max_supported:number;reason:string}
export type Attempt = {id:string;scoring?:string;resume_token?:string;revision:number;answers:Record<string,string|string[]>;position:number;result?:AttemptResult|null}
export type AttemptResult = {score:number;correct_count:number;question_count:number;feedback:{question_id:string;prompt:string;score:number;correct:boolean;expected_answer:string|string[];explanation:string;options?:{id:string;text:string;explanation:string;correct:boolean;selected:boolean}[]}[]}
const json=(body:unknown)=>({headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
const record=(value:unknown)=>requireRecord(value,'study workspace')
export function capacity(course:string,ids:string[],kind:'assessment'|'flashcards',signal?:AbortSignal):Promise<Capacity>{
 return requestApi(`study/capacity?course_id=${encodeURIComponent(course)}&kind=${kind}&${ids.map(id=>`material_ids=${encodeURIComponent(id)}`).join('&')}`,{method:'GET',signal},v=>{const r=record(v);if(typeof r.max_supported!=='number'||typeof r.reason!=='string')throw new Error('Could not read material capacity.');return r as unknown as Capacity})
}
export const generate=(settings:V2Settings,options:JobOptions):Promise<Artifact>=>generationRequest('generate',settings,artifact,{...options,course:String(settings.course_id)})
export const saveNotes=(id:string,revision:number,sections:{id:string;text:string}[])=>requestApi(`study/notes/${encodeURIComponent(id)}`,{method:'PATCH',...json({revision,sections})},artifact)
export const renameMaterial=(course:string,id:string,name:string)=>requestApi(`study/materials/${encodeURIComponent(id)}/name`,{method:'PATCH',...json({course_id:Number(course),name})},record)
export const createAttempt=(id:string,scoring:string)=>requestApi('study/attempts',{method:'POST',...json({artifact_id:id,scoring})},v=>record(v) as unknown as Attempt)
export const readAttempt=(id:string,token:string)=>requestApi(`study/attempts/${encodeURIComponent(id)}`,{method:'GET',headers:{'X-Aura-Resume-Token':token}},v=>record(v) as unknown as Attempt)
export const saveAttempt=(attempt:Attempt,token:string)=>requestApi(`study/attempts/${encodeURIComponent(attempt.id)}`,{method:'PATCH',...json({...attempt,resume_token:token,result:undefined})},v=>record(v) as unknown as Attempt)
export const submitAttempt=(attempt:Attempt,token:string,seconds:number)=>requestApi(`study/attempts/${encodeURIComponent(attempt.id)}/submit`,{method:'POST',...json({...attempt,resume_token:token,duration_seconds:seconds})},v=>record(v) as unknown as AttemptResult)
export const reviewCard=(course:string,deck:string,card:string,correct:boolean)=>requestApi(`study/decks/${encodeURIComponent(deck)}/cards/${encodeURIComponent(card)}/review`,{method:'POST',...json({course_id:Number(course),correct})},record)
export type ProgressTopic={topic:string;mastery:number;evidence_count:number;last_practiced_at:string}
export type ProgressEvent={id:string;kind:string;title:string;created_at:string;result?:{score?:number};duration_seconds:number}
export type ProgressSummary={range:string;scope:string;overall_mastery:number|null;study_streak:number;quiz_average:number|null;time_this_week_seconds:number|null;cards_due:number;topics:ProgressTopic[];recommended_next:{topic:string;mastery:number;reason:string}|null;quizzes:ProgressEvent[];history:{label:string;items:ProgressEvent[]}[];notice:string}
export const getProgress=(course:string,range:string)=>requestApi(`study/progress/summary?course_id=${encodeURIComponent(course)}&range=${range}&timezone_name=${encodeURIComponent(Intl.DateTimeFormat().resolvedOptions().timeZone)}`,{method:'GET'},v=>record(v) as unknown as ProgressSummary)
export type DatedTask={id:string;title:string;details:string;done:boolean;scheduled_for:string|null}
export const getDatedTasks=(course:string,day:string)=>requestApi(`agents/tasks/by-date?course_id=${encodeURIComponent(course)}&day=${day}`,{method:'GET'},v=>record(v) as unknown as {date:string;items:DatedTask[]})
export const getTaskWeek=(course:string,end:string)=>requestApi(`agents/tasks/week?course_id=${encodeURIComponent(course)}&end=${end}`,{method:'GET'},v=>record(v) as unknown as {days:{date:string;completed:number}[]})
export const moveTask=(course:string,id:string,day:string)=>requestApi(`agents/tasks/${encodeURIComponent(id)}/date?course_id=${encodeURIComponent(course)}`,{method:'PATCH',...json({scheduled_for:day})},record)
export const getPlans=(course:string,q:string,status:string,cursor:string|null)=>requestApi(`agents/plans?course_id=${encodeURIComponent(course)}&q=${encodeURIComponent(q)}&limit=5${status?`&status=${status}`:''}${cursor?`&cursor=${encodeURIComponent(cursor)}`:''}`,{method:'GET'},record)
export const archivePlan=(course:string,id:string)=>requestApi(`agents/runs/${encodeURIComponent(id)}/archive?course_id=${encodeURIComponent(course)}`,{method:'PATCH',...json({archived:true})},record)

export const deleteMaterial=(course:string,id:string)=>requestApi(`study/materials/${encodeURIComponent(id)}/delete?course_id=${encodeURIComponent(course)}`,{method:'POST'},record)
