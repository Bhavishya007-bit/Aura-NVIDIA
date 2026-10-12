import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { clearAuthToken, getCurrentUser, loginAccount, registerAccount } from '../services/authApi'
import type { AuthUser } from '../services/authApi'
import { ApiHttpError } from '../services/apiClient'
import './AuthPage.css'

type Props = {
  mode: 'login' | 'signup'
  theme: 'light' | 'dark'
  onSuccess: (user: AuthUser) => void
  initialError?: string
  onNavigate: (path: '/' | '/login' | '/signup') => void
}

export default function AuthPage({ mode, theme, onSuccess, initialError, onNavigate }: Props) {
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState(initialError || '')
  const [busy, setBusy] = useState(false)
  const [registered, setRegistered] = useState(false)
  const [newUserPrompt, setNewUserPrompt] = useState(false)
  const signupDialog = useRef<HTMLDialogElement>(null)
  const busyRef = useRef(false)
  const mounted = useRef(true)
  const isSignup = mode === 'signup' && !registered
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  useEffect(() => { setError(initialError || '') }, [initialError])
  useEffect(() => {
    if (newUserPrompt) signupDialog.current?.showModal()
    else signupDialog.current?.close()
  }, [newUserPrompt])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busyRef.current) return
    setError('')
    const cleanEmail = email.trim()
    if (isSignup && username.trim().length < 2) {
      setError('Enter a name with at least 2 characters.'); return
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(cleanEmail)) {
      setError('Enter a valid email address.'); return
    }
    if (!password || (isSignup && password.length < 8)) {
      setError(isSignup ? 'Password must be at least 8 characters.' : 'Enter your password.'); return
    }
    if (isSignup && password !== confirmPassword) {
      setError('Passwords do not match.'); return
    }
    busyRef.current = true
    setBusy(true)
    try {
      if (isSignup) {
        await registerAccount(username, cleanEmail, password)
        if (!mounted.current) return
        setRegistered(true)
      }
      await loginAccount(cleanEmail, password)
      const user = await getCurrentUser()
      if (mounted.current) onSuccess(user)
    } catch (cause) {
      clearAuthToken()
      if (mounted.current && !isSignup && cause instanceof ApiHttpError && cause.status === 404) {
        setNewUserPrompt(true)
      }
      if (mounted.current) setError(cause instanceof Error ? cause.message : 'Could not sign in. Please try again.')
    } finally {
      busyRef.current = false
      if (mounted.current) setBusy(false)
    }
  }

  return <main className="aura-auth" data-theme={theme}>
    <section className="auth-card" aria-labelledby="auth-title">
      <a className="brand auth-brand" href="/" onClick={event => { event.preventDefault(); if (!busy) onNavigate('/') }}>
        <span className="brand-mark">A.</span><span>Aura</span>
      </a>
      <p className="auth-eyebrow">{isSignup ? 'START LEARNING' : 'WELCOME BACK'}</p>
      <h1 id="auth-title">{isSignup ? 'Create your account' : 'Welcome back'}</h1>
      <p className="auth-description">{registered ? 'Account created. Sign in to continue.' : isSignup ? 'Bring your learning materials and progress together.' : 'Sign in to continue to your study workspace.'}</p>
      <form className="auth-form" onSubmit={event => void submit(event)} noValidate aria-busy={busy}>
        {isSignup && <label>Name<input autoComplete="name" value={username} maxLength={100} onChange={event => setUsername(event.target.value)} required disabled={busy} /></label>}
        <label>Email<input type="email" autoComplete="email" value={email} onChange={event => setEmail(event.target.value)} required disabled={busy} /></label>
        <label>Password<input type="password" autoComplete={isSignup ? 'new-password' : 'current-password'} value={password} maxLength={128} onChange={event => setPassword(event.target.value)} required disabled={busy} /></label>
        {isSignup && <label>Confirm Password<input type="password" autoComplete="new-password" value={confirmPassword} maxLength={128} onChange={event => setConfirmPassword(event.target.value)} required disabled={busy} /></label>}
        {error && <p className="auth-error" role="alert">{error}</p>}
        <button className="auth-submit" type="submit" disabled={busy}>{busy ? 'Please wait…' : isSignup ? 'Create account' : 'Log in'}</button>
      </form>
      <p className="auth-switch">{isSignup ? 'Already have an account?' : "Don't have an account?"}{' '}
        <button type="button" disabled={busy} onClick={() => {
          if (registered) { setRegistered(false); setPassword(''); setConfirmPassword(''); setError('') }
          else onNavigate(isSignup ? '/login' : '/signup')
        }}>{isSignup ? 'Log in' : 'Sign up'}</button>
      </p>
      <button className="auth-back" type="button" disabled={busy} onClick={() => onNavigate('/')}>← Continue as guest</button>
      <dialog ref={signupDialog} className="auth-dialog" aria-labelledby="signup-prompt-title" onCancel={() => setNewUserPrompt(false)}>
        <h2 id="signup-prompt-title">New to Aura?</h2>
        <p>We couldn’t find an account for {email.trim()}. Create an account to save your learning progress.</p>
        <button className="auth-submit" type="button" onClick={() => onNavigate('/signup')}>Create an account</button>
        <button className="auth-back" type="button" onClick={() => setNewUserPrompt(false)}>Try another email</button>
      </dialog>
    </section>
  </main>
}
