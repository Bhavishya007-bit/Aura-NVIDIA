import { lazy, Suspense, useEffect, useState } from 'react'
import FieldnoteDashboard from './components/FieldnoteDashboard'
import AuthPage from './components/AuthPage'
import { useCurrentLocalDate } from './hooks/useCurrentLocalDate'
import { resolveCourseId } from './services/studyApi'
import { type AuthUser } from './services/authApi'
const MaterialUploader = lazy(() => import('./components/MaterialUploader'))
const StudyDesk = lazy(() => import('./components/StudyDesk'))
const ProgressPage = lazy(() => import('./components/ProgressPage'))
const AssessmentPage = lazy(() => import('./components/AssessmentPage'))
type Page = 'Dashboard' | 'My Courses' | 'Upload Materials' | 'AI Tutor' | 'Quizzes' | 'Progress'
const pages: {name:Page;icon:string}[]=[{name:'Dashboard',icon:'◫'},{name:'My Courses',icon:'▤'},{name:'Upload Materials',icon:'↑'},{name:'AI Tutor',icon:'✳'},{name:'Quizzes',icon:'☷'},{name:'Progress',icon:'↗'}]
const courses=['Foundations of Biology','Chemistry II','Environmental Science']
function initialsFor(name:string){return name.trim().split(/\s+/).slice(0,2).map(part=>part[0]).join('').toUpperCase()||'ST'}
function App(){
 const [page,setPage]=useState<Page>('Dashboard')
 const [course,setCourse]=useState(courses[0])
 const [menuOpen,setMenuOpen]=useState(false)
 const [studentName,setStudentName]=useState(()=>localStorage.getItem('aura.studentName') || 'Student')
 const [palettePreview,setPalettePreview]=useState<'current'>('current')
 const [theme,setTheme]=useState<'light'|'dark'>(()=> {
  const saved=localStorage.getItem('aura.theme')
  if(saved==='light'||saved==='dark') return saved
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
 })
 const [searchQuery,setSearchQuery]=useState('')
 const [currentPath,setCurrentPath]=useState(window.location.pathname)
 const [authUser,setAuthUser]=useState<AuthUser|null>(null)
 const [authError,setAuthError]=useState('')
 const currentDate=useCurrentLocalDate()

 function navigate(path:string,replace=false){
  if(replace) window.history.replaceState(null,'',path)
  else window.history.pushState(null,'',path)
  setCurrentPath(path)
 }
 useEffect(()=>{
  const handlePopState=()=>setCurrentPath(window.location.pathname)
  window.addEventListener('popstate',handlePopState)
  return ()=>window.removeEventListener('popstate',handlePopState)
 },[])
 useEffect(()=>{
  localStorage.setItem('aura.theme',theme)
  document.documentElement.style.colorScheme=theme
 },[theme])
 useEffect(()=>{
  localStorage.setItem('aura.studentName',studentName)
 },[studentName])
 function searchLearning(e:React.FormEvent){e.preventDefault();const query=searchQuery.trim().toLowerCase();if(!query)return;const matchingCourse=courses.find(item=>item.toLowerCase().includes(query));if(matchingCourse){setCourse(matchingCourse);setPage('Dashboard')}else{const matchingPage=pages.find(item=>item.name.toLowerCase().includes(query));setPage(matchingPage?.name||'My Courses')}setSearchQuery('')}
 if(currentPath==='/login'||currentPath==='/signup'){
  const authMode=currentPath==='/signup'?'signup':'login'
  return <AuthPage mode={authMode} theme={theme} initialError={authError} onNavigate={path=>{setAuthError('');navigate(path)}} onSuccess={user=>{setAuthUser(user);setStudentName(user.fullName);setAuthError('');navigate('/',true)}}/>
 }
 return <div className="app-shell" data-palette={palettePreview} data-theme={theme}><aside className={`sidebar ${menuOpen?'sidebar-open':''}`}><a className="brand" href="#dashboard" onClick={e=>{e.preventDefault();setPage('Dashboard')}}><span className="brand-mark">A.</span><span>Aura</span></a><div className="sidebar-label">LEARN</div><nav id="primary-navigation" aria-label="Main navigation">{pages.map(({name,icon})=><button key={name} onClick={()=>{setPage(name);setMenuOpen(false)}} className={`nav-item ${page===name?'active':''}`}><span className="nav-icon">{icon}</span>{name}{name==='AI Tutor'&&<span className="nav-new">NEW</span>}</button>)}</nav><div className="sidebar-bottom"><div className="streak-card"><span className="streak-icon">✳</span><div><strong>4 day streak</strong><small>Keep your momentum going</small></div></div>{authUser?<div className="sidebar-user"><span className="avatar">{initialsFor(studentName)}</span><div><strong>{studentName}</strong><small>Student account</small></div></div>:<button type="button" className="sidebar-login" onClick={()=>navigate('/login')}><span className="avatar">↗</span><span><strong>Sign in</strong><small>Save your learning progress</small></span></button>}<div className="demo-note"><span className="demo-dot"/>Demo workspace</div></div></aside>
 <main className="main-area"><header className="topbar"><button className="mobile-menu" onClick={()=>setMenuOpen(!menuOpen)} aria-label="Toggle navigation" aria-expanded={menuOpen} aria-controls="primary-navigation">☰</button><form className="topbar-search" role="search" onSubmit={searchLearning}><span aria-hidden="true">⌕</span><input aria-label="Search courses and pages" placeholder="Search courses, notes, or anything…" value={searchQuery} onChange={e=>setSearchQuery(e.target.value)}/></form><div className="topbar-right"><button type="button" className="theme-toggle" aria-label={theme==='dark'?'Switch to light mode':'Switch to dark mode'} onClick={()=>setTheme(current=>current==='dark'?'light':'dark')}><span className="theme-toggle-track"><span className="theme-toggle-thumb"><span className="theme-icon theme-icon-sun" aria-hidden="true">☀</span><span className="theme-icon theme-icon-moon" aria-hidden="true">☾</span></span></span></button><span className="topbar-date">{currentDate}</span><label className="course-select"><span className="course-swatch"/><select aria-label="Choose a course" value={course} onChange={e=>setCourse(e.target.value)}>{courses.map(c=><option key={c}>{c}</option>)}</select><span className="chevron">⌄</span></label>{authUser?<ProfileEditor studentName={studentName} onSave={setStudentName}/>:<button type="button" className="header-login" onClick={()=>navigate('/login')}>Log in</button>}</div></header><div className="content"><Suspense fallback={<div className="route-loading" role="status">Loading study workspace…</div>}>{page==='Dashboard'&&<FieldnoteDashboard setPage={setPage} course={course} studentName={studentName} palettePreview={palettePreview} setPalettePreview={setPalettePreview}/>}{page==='My Courses'&&<Courses setPage={setPage} setCourse={setCourse}/ >}{page==='Upload Materials'&&<UploadPage course={course}/>}{page==='AI Tutor'&&<StudyDesk key={course} course={course} courses={courses} studentName={studentName} onCourseChange={setCourse} setPage={setPage}/ >}{page==='Quizzes'&&<AssessmentPage key={course} course={course} setPage={setPage}/ >}{page==='Progress'&&<ProgressPage setPage={setPage}/>}</Suspense></div><footer className="page-footer"><span>Aura</span><span>Made for curious minds</span></footer></main></div>
}
function ProfileEditor({studentName,onSave}:{studentName:string;onSave:(name:string)=>void}){
 const [open,setOpen]=useState(false),[draft,setDraft]=useState(studentName)
 function submit(event:React.FormEvent){event.preventDefault();const name=draft.trim();if(!name)return;localStorage.setItem('aura.studentName',name);onSave(name);setOpen(false)}
 return <div className="profile-control"><button className="top-avatar" type="button" aria-label="Edit student name" aria-expanded={open} onClick={()=>{setDraft(studentName);setOpen(!open)}}>{initialsFor(studentName)}</button>{open&&<form className="profile-popover" onSubmit={submit}><label htmlFor="student-name">Your name</label><input id="student-name" autoFocus maxLength={48} value={draft} onChange={event=>setDraft(event.target.value)} placeholder="Enter your name"/><div className="profile-actions"><button type="button" className="profile-cancel" onClick={()=>setOpen(false)}>Cancel</button><button type="submit" disabled={!draft.trim()}>Save name</button></div><small>Saved in this browser</small></form>}</div>
}
function Heading({eyebrow,title,description}:{eyebrow:string;title:string;description:string}){return <div className="page-heading"><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>}
function Demo(){return <span className="demo-tag">DEMO DATA</span>}
function Courses({setPage,setCourse}:{setPage:(p:Page)=>void;setCourse:(c:string)=>void}){return <><Heading eyebrow="YOUR LEARNING LIBRARY" title="My courses" description="Everything you’re learning, gathered in one place."/><div className="course-list">{courses.map((c,i)=><article className="course-row" key={c}><span className={`subject-mark ${i===0?'green':i===1?'blue':'sand'}`}>{['BIO','CHEM','ECO'][i]}</span><div className="course-row-info"><div className="course-row-title"><h2>{c}</h2>{i===0&&<Demo/>}</div><p>{['5 chapters · 3 materials','8 chapters · 6 materials','4 chapters · 2 materials'][i]}</p></div><div className="course-progress"><div className="tiny-progress"><span style={{width:`${[62,34,78][i]}%`}}/></div><small>{[62,34,78][i]}% complete</small></div><button className="arrow-button" aria-label={`Open ${c}`} onClick={()=>{setCourse(c);setPage('Dashboard')}}>→</button></article>)}</div><button className="add-course-button" onClick={()=>setPage('Upload Materials')}>＋ Add a course or material</button></>}
function UploadPage({course}:{course:string}){return <><Heading eyebrow="BUILD YOUR STUDY LIBRARY" title="Upload materials" description="Bring your own course resources together."/><MaterialUploader courseName={course} courseId={resolveCourseId(course)}/></>}
export function Quiz({choice,setChoice}:{choice:number|null;setChoice:(n:number)=>void}){const options=['It stores genetic information in a stable form.','It provides readily usable energy for cellular processes.','It carries oxygen through the bloodstream.','It forms the outer membrane of every cell.'];return <><Heading eyebrow="RETRIEVAL PRACTICE" title="Quick quiz" description="A short check-in on your recent biology study."/><div className="quiz-layout"><section className="quiz-card"><div className="quiz-meta"><span>FOUNDATIONS OF BIOLOGY</span><span>QUESTION 1 OF 5</span></div><div className="quiz-progress"><span/></div><h2>What is the primary role of ATP in a cell?</h2><p className="quiz-hint">Choose the best answer.</p><div className="quiz-options">{options.map((o,i)=><button key={o} className={`quiz-option ${choice===i?(i===1?'correct':'incorrect'):''}`} onClick={()=>setChoice(i)}><span className="option-letter">{String.fromCharCode(65+i)}</span>{o}{choice===i&&<span className="option-result">{i===1?'✓':'×'}</span>}</button>)}</div>{choice!==null&&<div className={`answer-feedback ${choice===1?'feedback-correct':'feedback-try'}`}><strong>{choice===1?'That’s right.':'Not quite.'}</strong> ATP is the cell’s main short-term energy carrier, powering processes like active transport and muscle contraction.</div>}<div className="quiz-footer"><Demo/><span>Sample question · Chapter 4</span></div></section><aside className="quiz-side"><div className="eyebrow">YOUR PRACTICE</div><h3>Small sessions add up.</h3><p>Short, focused check-ins can help move ideas into long-term memory.</p><div className="quiz-stat"><strong>8</strong><span>questions practiced<br/>this week</span></div><div className="quiz-stat"><strong>80%</strong><span>average accuracy<br/>this week</span></div></aside></div></>}
export default App
