import { requestApi, requireRecord, setApiAuthTokenProvider, ApiResponseError } from './apiClient'

const AUTH_TOKEN_KEY = 'aura.authToken'

export type AuthUser = {
  id?: string
  fullName: string
  email: string
}

type AuthTokenResponse = {
  access_token: string
}

setApiAuthTokenProvider(() => sessionStorage.getItem(AUTH_TOKEN_KEY))

export function hasAuthToken(): boolean {
  return Boolean(sessionStorage.getItem(AUTH_TOKEN_KEY))
}

export function clearAuthToken(): void {
  sessionStorage.removeItem(AUTH_TOKEN_KEY)
}

export async function registerAccount(fullName: string, email: string, password: string): Promise<void> {
  await requestApi(
    'auth/register',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ full_name: fullName, email, password }),
    },
    (value) => requireRecord(value, 'registration'),
  )
}

export async function loginAccount(email: string, password: string): Promise<void> {
  const result = await requestApi(
    'auth/login',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    },
    decodeAuthToken,
  )
  sessionStorage.setItem(AUTH_TOKEN_KEY, result.access_token)
}

export async function getCurrentUser(): Promise<AuthUser> {
  return requestApi('auth/me', { method: 'GET' }, decodeAuthUser)
}

function decodeAuthToken(value: unknown): AuthTokenResponse {
  const record = requireRecord(value, 'login')
  if (typeof record.access_token !== 'string' || !record.access_token) {
    throw new ApiResponseError('The Aura API returned an invalid login response.')
  }
  return { access_token: record.access_token }
}

function decodeAuthUser(value: unknown): AuthUser {
  const record = requireRecord(value, 'current user')
  const fullName = record.full_name
  if (
    (fullName !== undefined && typeof fullName !== 'string') ||
    typeof record.email !== 'string'
  ) {
    throw new ApiResponseError('The Aura API returned an invalid current-user response.')
  }
  return {
    id: typeof record.id === 'string' ? record.id : undefined,
    fullName: fullName || record.email.split('@')[0],
    email: record.email,
  }
}
