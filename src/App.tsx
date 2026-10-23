import { useEffect, useState } from 'react'
import AuthPage from './components/AuthPage'
import ChatHome from './components/ChatHome'
import StudyWorkspace from './components/StudyWorkspace'
import { listCourses } from './services/studyApi'
import type { Course } from './types/study'
import { AUTH_EXPIRED_EVENT, clearAuthToken, getCurrentUser, hasAuthToken, logoutAccount } from './services/authApi'
import type { AuthUser } from './services/authApi'
import { ApiHttpError } from './services/apiClient'
import { navigationKey, readWorkspace, saveWorkspace } from './services/workspaceStorage'

export default function App() {
  const [courses, setCourses] = useState<Course[]>([])
  const [courseId, setCourseId] = useState('')
  const [coursesLoading, setCoursesLoading] = useState(true)
  const [coursesError, setCoursesError] = useState('')
  const [homeOpen, setHomeOpen] = useState(true)
  const [pendingWorkspace, setPendingWorkspace] = useState(false)
  const [user, setUser] = useState<AuthUser | null>(null)
  const [path, setPath] = useState(window.location.pathname)
  const [authChecking, setAuthChecking] = useState(hasAuthToken)
  const [authError, setAuthError] = useState('')
  const [restoreError, setRestoreError] = useState('')
  const [restoreAttempt, setRestoreAttempt] = useState(0)
  const [signingOut, setSigningOut] = useState(false)
  const [sessionNotice, setSessionNotice] = useState('')
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    const saved = localStorage.getItem('aura.theme')
    return saved === 'dark' || saved === 'light' ? saved : window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  })
  function navigate(next: '/' | '/login' | '/signup', replace = false) {
    if (replace) window.history.replaceState(null, '', next)
    else window.history.pushState(null, '', next)
    setPath(next)
  }
  function restoreNavigation(account: AuthUser) {
    setCoursesLoading(true); setCourses([])
    const saved = readWorkspace<{ homeOpen?: boolean; courseId?: string }>(navigationKey(account.id), {})
    if (new URLSearchParams(window.location.search).get('view') === 'study') setHomeOpen(false)
    else if (typeof saved.homeOpen === 'boolean') setHomeOpen(saved.homeOpen)
    if (typeof saved.courseId === 'string') setCourseId(saved.courseId)
  }
  function openWorkspace() {
    if (!user) { setPendingWorkspace(true); setAuthError('Sign in to use your study tools and save progress.'); navigate('/login'); return }
    setHomeOpen(false)
  }
  useEffect(() => {
    let cancelled = false
    setCoursesLoading(true); setCoursesError(''); setCourses([])
    if (!user) { setCoursesLoading(false); setCourseId(''); return }
    listCourses().then(items => {
      if (cancelled) return
      setCourses(items)
      setCourseId(current => items.some(item => item.id === current) ? current : items[0]?.id ?? '')
    }).catch(cause => { if (!cancelled) setCoursesError(cause instanceof Error ? cause.message : 'Could not load courses.') })
      .finally(() => { if (!cancelled) setCoursesLoading(false) })
    return () => { cancelled = true }
  }, [user?.id])
  // A saved course is checked after both authentication and course loading finish.
  useEffect(() => {
    if (!authChecking && !coursesLoading && courses.length && !courses.some(item => item.id === courseId)) setCourseId(courses[0].id)
  }, [authChecking, coursesLoading, courses, courseId])
  useEffect(() => {
    if (user && !authChecking && !coursesLoading) saveWorkspace(navigationKey(user.id), { homeOpen, courseId })
  }, [user, authChecking, coursesLoading, homeOpen, courseId])
  useEffect(() => {
    const pop = () => setPath(window.location.pathname)
    const failed = () => setSessionNotice('Your browser could not save this draft. Free some browser storage and retry.')
    window.addEventListener('popstate', pop); window.addEventListener('aura:workspace-save-failed', failed)
    return () => { window.removeEventListener('popstate', pop); window.removeEventListener('aura:workspace-save-failed', failed) }
  }, [])
  useEffect(() => {
    localStorage.setItem('aura.theme', theme)
    document.documentElement.style.colorScheme = theme
  }, [theme])
  useEffect(() => {
    let cancelled = false
    const expired = () => {
      cancelled = true; setUser(null); setHomeOpen(true); setAuthChecking(false); setRestoreError('')
      setAuthError('Your session expired. Please sign in again.'); navigate('/login', true)
    }
    window.addEventListener(AUTH_EXPIRED_EVENT, expired)
    if (hasAuthToken()) {
      setAuthChecking(true); setRestoreError('')
      getCurrentUser().then(account => {
        if (cancelled) return
        setUser(account); restoreNavigation(account)
        if (['/login', '/signup'].includes(window.location.pathname)) navigate('/', true)
      }).catch(cause => {
        if (cancelled) return
        if (cause instanceof ApiHttpError && cause.status === 401) expired()
        else setRestoreError('Could not restore your session. Check the connection and retry.')
      }).finally(() => { if (!cancelled) setAuthChecking(false) })
    } else setAuthChecking(false)
    return () => { cancelled = true; window.removeEventListener(AUTH_EXPIRED_EVENT, expired) }
  }, [restoreAttempt])
  async function signOut() {
    if (signingOut) return
    setSigningOut(true); setSessionNotice('')
    try { await logoutAccount(); setUser(null); setHomeOpen(true); setPendingWorkspace(false); navigate('/login', true) }
    catch { setSessionNotice('Could not sign out. Please retry.') }
    finally { setSigningOut(false) }
  }
  if (authChecking || restoreError || (user && coursesLoading)) return <main className="aura-auth" data-theme={theme}><section className="auth-card" aria-live="polite"><h1>{authChecking ? 'Signing you in…' : coursesLoading ? 'Loading your workspace…' : 'Connection interrupted'}</h1>{restoreError && <><p role="alert">{restoreError}</p><button type="button" onClick={() => setRestoreAttempt(value => value + 1)}>Retry</button><button type="button" onClick={() => { clearAuthToken(); setRestoreError(''); setUser(null); setHomeOpen(true); navigate('/login', true) }}>Back to sign in</button></>}</section></main>
  if (!user || path === '/login' || path === '/signup') return <AuthPage key={path} mode={path === '/signup' ? 'signup' : 'login'} theme={theme} initialError={authError} onNavigate={next => { setAuthError(''); if (next === '/') { setHomeOpen(true); setPendingWorkspace(false) }; navigate(next) }} onSuccess={account => {
    setUser(account); setAuthError(''); restoreNavigation(account)
    if (pendingWorkspace) { setHomeOpen(false); setPendingWorkspace(false) }
    navigate('/', true)
  }} />
  if (homeOpen) return <ChatHome key={`${courseId}:${user.id}`} courses={courses} courseId={courseId} coursesLoading={coursesLoading} coursesError={coursesError} studentName={user.fullName} workspaceKey={user.id} onCourseChange={setCourseId} onSignOut={() => void signOut()} signingOut={signingOut} sessionNotice={sessionNotice} onOpenWorkspace={openWorkspace} onCreateStudyPlan={(goal, source) => { const url = new URL(window.location.href); url.searchParams.set('view', 'study'); url.searchParams.set('tab', 'Agents'); url.searchParams.set('goal', goal); if (source) url.searchParams.set('source', source); window.history.replaceState(null, '', url); setHomeOpen(false) }} />
  return <StudyWorkspace key={`${user.id}:${courseId}`} user={user} courses={courses} courseId={courseId} coursesLoading={coursesLoading} coursesError={coursesError} theme={theme} onCourseChange={setCourseId} onThemeChange={() => setTheme(value => value === 'light' ? 'dark' : 'light')} onChatHome={() => { window.history.replaceState(null, '', '/'); setHomeOpen(true) }} onSignOut={() => void signOut()} signingOut={signingOut} sessionNotice={sessionNotice} />
}

