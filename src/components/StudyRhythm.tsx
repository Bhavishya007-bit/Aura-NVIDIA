import { useEffect, useRef, useState } from 'react'
import { getRhythm, saveRhythm, refreshDigest, snoozeReview } from '../services/rhythmApi'
import type { Rhythm } from '../services/rhythmApi'
import './StudyRhythm.css'

type Props = { courseId: string; onPractice: (topic: string, sourceId: string) => void }
export default function StudyRhythm({ courseId, onPractice }: Props) {
  const [data,setData]=useState<Rhythm>(); const [busy,setBusy]=useState(false); const [error,setError]=useState('')
  const [zone,setZone]=useState(()=>Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'); const [hour,setHour]=useState(9)
  const [reload,setReload]=useState(0); const lock=useRef(false)
  const identity=useRef(courseId); identity.current=courseId
  const revision=useRef(0)
  const mounted=useRef(false)
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false}},[])
  useEffect(()=>{
    let disposed=false
    revision.current++; setData(undefined); setError(''); setBusy(false); lock.current=false
    setZone(Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'); setHour(9)
    async function load(syncSettings=true){const expected=revision.current;try{const value=await getRhythm(courseId);if(!disposed&&expected===revision.current){setData(value);if(syncSettings&&value.settings.enabled){setZone(value.settings.timezone);setHour(value.settings.daily_hour)}setError('')}}catch{if(!disposed&&expected===revision.current)setError('Your study rhythm could not be loaded.')}}
    void load(); const timer=setInterval(()=>void load(false),60000)
    return()=>{disposed=true;clearInterval(timer)}
  },[courseId,reload])
  async function act(work:()=>Promise<Rhythm>){if(lock.current)return;const requestedCourse=courseId;const expected=++revision.current;lock.current=true;setBusy(true);setError('');try{const value=await work();if(mounted.current&&identity.current===requestedCourse&&expected===revision.current)setData(value)}catch{if(mounted.current&&identity.current===requestedCourse&&expected===revision.current)setError('Could not save this change. Please try again.')}finally{if(mounted.current&&identity.current===requestedCourse&&expected===revision.current){lock.current=false;setBusy(false)}}}
  const digest=data?.digests[0], enabled=data?.settings.enabled===true
  return <section className="study-rhythm" aria-label="Daily study rhythm">
    <header><div><span className="rhythm-kicker">A LITTLE EVERY DAY</span><h2>☀️ Your study rhythm</h2><p>A daily brief and timely review, built from your saved work.</p></div><label className="rhythm-switch"><input type="checkbox" role="switch" aria-label="Daily digest and review reminders" checked={enabled} disabled={!data||busy} onChange={e=>void act(()=>saveRhythm(courseId,{enabled:e.target.checked,timezone:zone,daily_hour:hour}))}/><span>{enabled?'On':'Paused'}</span></label></header>
    {error&&<p role="alert">{error} <button type="button" disabled={busy} onClick={()=>setReload(v=>v+1)}>Retry</button></p>}
    {!data&&!error&&<p role="status">Loading your study rhythm…</p>}
    {data&&!enabled&&<p className="rhythm-note">Turn this on to create an in-app daily brief and schedule review from graded quizzes. No email, push notifications or background AI calls.</p>}
    {data&&<details><summary>Schedule &amp; how it works</summary><div className="rhythm-settings"><label>Daily brief at<select aria-label="Daily digest hour" value={hour} disabled={busy} onChange={e=>setHour(Number(e.target.value))}>{Array.from({length:24},(_,h)=><option key={h} value={h}>{String(h).padStart(2,'0')}:00</option>)}</select></label><label>Timezone<input aria-label="Digest timezone" maxLength={80} value={zone} disabled={busy} onChange={e=>setZone(e.target.value)}/></label><button type="button" disabled={busy} onClick={()=>void act(()=>saveRhythm(courseId,{enabled,timezone:zone,daily_hour:hour}))}>Save schedule</button></div><p className="rhythm-note">Review intervals grow after successful graded sessions: 1, 3, 7, 14 and 30 days. A mistake brings the topic back sooner. Reading alone does not count as mastery. Digests are created while Aura's backend is running; the next startup catches up to today.</p></details>}
    {enabled&&<><div className="rhythm-actions"><button type="button" disabled={busy} onClick={()=>void act(()=>refreshDigest(courseId))}>Update due topics</button><small>Daily brief is a saved snapshot · {data.settings.timezone}</small></div>{digest?<article className="rhythm-digest"><span className="rhythm-kicker">{digest.local_date}</span><h3>{digest.payload.title}</h3><p>{digest.payload.takeaway}</p>{digest.payload.tasks.length>0&&<><h4>From your checklist</h4><ul>{digest.payload.tasks.map(task=><li key={task.id}>{task.title}</li>)}</ul><small>Snapshot when this brief was created. Open Today for current checkmarks.</small></>}</article>:<p>Your first brief will appear after the scheduled hour. Use Update due topics to create it now.</p>}<div className="rhythm-reviews" aria-live="polite"><h3>🔁 Ready to revisit</h3>{!data.reviews.length?<p>No topics are due. Complete a graded quiz to start a review schedule.</p>:data.reviews.map(review=><article key={`${review.source_id}:${review.topic_key}`}><div><h4>{review.topic}</h4><p>{review.source_name}</p></div><div><button type="button" disabled={busy} onClick={()=>onPractice(review.topic,String(review.source_id))}>Practice this topic ↗</button><button type="button" disabled={busy} onClick={()=>void act(()=>snoozeReview(courseId,review))}>Tomorrow</button></div></article>)}</div></>}
  </section>
}
