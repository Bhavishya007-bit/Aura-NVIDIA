import { requestApi, requireRecord, setApiAuthTokenProvider, setApiUnauthorizedHandler, ApiResponseError } from './apiClient'

const AUTH_TOKEN_KEY = 'aura.authToken'
export const AUTH_EXPIRED_EVENT = 'aura:auth-expired'
export type AuthUser = { id: string; fullName: string; email: string }

setApiAuthTokenProvider(() => sessionStorage.getItem(AUTH_TOKEN_KEY))
setApiUnauthorizedHandler(token => {
  // A delayed response for an old session must not clear a newer login.
  if (sessionStorage.getItem(AUTH_TOKEN_KEY) !== token) return
  clearAuthToken()
  window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT))
})

export function hasAuthToken(): boolean {
  return Boolean(sessionStorage.getItem(AUTH_TOKEN_KEY))
}
export function clearAuthToken(): void {
  sessionStorage.removeItem(AUTH_TOKEN_KEY)
}
export async function registerAccount(fullName: string, email: string, password: string): Promise<void> {
  await requestApi('auth/register', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: fullName.trim(), email: email.trim(), password }),
  }, decodeAuthUser)
}
export async function loginAccount(email: string, password: string): Promise<void> {
  const token = await requestApi('auth/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: email.trim(), password }),
  }, value => {
    const record = requireRecord(value, 'login')
    if (typeof record.access_token !== 'string' || !record.access_token.trim()) {
      throw new ApiResponseError('The Aura API returned an invalid login response.')
    }
    return record.access_token
  })
  sessionStorage.setItem(AUTH_TOKEN_KEY, token)
}
export async function getCurrentUser(): Promise<AuthUser> {
  return requestApi('auth/me', { method: 'GET' }, decodeAuthUser)
}
export async function logoutAccount(): Promise<void> {
  if (!hasAuthToken()) return
  await requestApi('auth/logout', { method: 'POST' }, value => requireRecord(value, 'logout'))
  clearAuthToken()
}
function decodeAuthUser(value: unknown): AuthUser {
  const record = requireRecord(value, 'current user')
  const id = record.student_id
  if ((typeof id !== 'number' && typeof id !== 'string') ||
      !/^\d+$/.test(String(id)) || !Number.isSafeInteger(Number(id)) || Number(id) < 1 ||
      typeof record.name !== 'string' || !record.name.trim() || typeof record.email !== 'string') {
    throw new ApiResponseError('The Aura API returned an invalid current-user response.')
  }
  return { id: String(id), fullName: record.name, email: record.email }
}
