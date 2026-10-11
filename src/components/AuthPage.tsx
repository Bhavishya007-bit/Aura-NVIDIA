import { useState } from 'react'
import type { AuthUser } from '../services/authApi'
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
  const isSignup = mode === 'signup'

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')

    const cleanEmail = email.trim()
    if (username.trim().length < 2) {
      setError('Enter a username with at least 2 characters.')
      return
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(cleanEmail)) {
      setError('Enter a valid email address.')
      return
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }
    if (isSignup && password !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }

    onSuccess({
      id: `demo-user-${Date.now()}`,
      fullName: username.trim(),
      email: cleanEmail,
    })
  }

  return (
    <main className="auth-page app-shell" data-palette="current" data-theme={theme}>
      <section className="auth-card" aria-labelledby="auth-title">
        <a className="brand auth-brand" href="/" onClick={(event) => { event.preventDefault(); onNavigate('/') }}>
          <span className="brand-mark">A.</span><span>Aura</span>
        </a>
        <p className="auth-eyebrow">{isSignup ? 'START LEARNING' : 'WELCOME BACK'}</p>
        <h1 id="auth-title">{isSignup ? 'Create your account' : 'Welcome back'}</h1>
        <p className="auth-description">{isSignup ? 'Bring your learning materials and progress together.' : 'Sign in to continue to your study workspace.'}</p>

        <form className="auth-form" onSubmit={submit} noValidate>
          <label>
            Username
            <input autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required />
          </label>
          <label>
            Email
            <input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          </label>
          <label>
            Password
            <input type="password" autoComplete={isSignup ? 'new-password' : 'current-password'} value={password} onChange={(event) => setPassword(event.target.value)} required />
          </label>
          {isSignup && (
            <label>
              Confirm Password
              <input type="password" autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} required />
            </label>
          )}
          {error && <p className="auth-error" role="alert">{error}</p>}
          <button className="auth-submit" type="submit">
            {isSignup ? 'Create account' : 'Log in'}
          </button>
        </form>
        <p className="auth-demo-note">Demo access only. Passwords aren’t saved; connect an authentication service for real accounts.</p>
        <p className="auth-switch">
          {isSignup ? 'Already have an account?' : "Don't have an account?"}{' '}
          <button type="button" onClick={() => onNavigate(isSignup ? '/login' : '/signup')}>
            {isSignup ? 'Log in' : 'Sign up'}
          </button>
        </p>
        <button className="auth-back" type="button" onClick={() => onNavigate('/')}>← Back to dashboard</button>
      </section>
    </main>
  )
}
