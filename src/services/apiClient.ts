import { API_BASE_URL } from '../config/api'

export class ApiUnavailableError extends Error {
  constructor(message = 'The Aura API is unavailable.') {
    super(message)
    this.name = 'ApiUnavailableError'
  }
}
export class ApiHttpError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message)
    this.name = 'ApiHttpError'
  }
}
export class ApiResponseError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ApiResponseError'
  }
}
type ApiRequestOptions = Omit<RequestInit, 'headers'> & { headers?: HeadersInit }
type AuthTokenProvider = () => string | null | Promise<string | null>
let authTokenProvider: AuthTokenProvider = () => null
let unauthorizedHandler: (token: string) => void = () => {}
export function setApiUnauthorizedHandler(handler: (token: string) => void): void {
  unauthorizedHandler = handler
}

/** The host application supplies its auth token; credentials remain centralized here. */
export function setApiAuthTokenProvider(provider: AuthTokenProvider): void {
  authTokenProvider = provider
}
export async function requestApi<T>(
  path: string,
  options: ApiRequestOptions,
  decode: (value: unknown) => T,
): Promise<T> {
  const url = `${API_BASE_URL.replace(/\/+$/, '')}/${path.replace(/^\/+/, '')}`
  const headers = new Headers(options.headers)
  const token = await authTokenProvider()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  let response: Response
  try {
    response = await fetch(url, { ...options, headers })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiUnavailableError(`Could not reach the Aura API at ${API_BASE_URL}.`)
  }
  if (!response.ok) {
    if (response.status === 401 && token && !/^\/?auth\/(login|register)$/.test(path)) {
      unauthorizedHandler(token)
    }
    throw new ApiHttpError(response.status, await readErrorMessage(response))
  }
  let body: unknown
  try {
    body = await response.json()
  } catch {
    throw new ApiResponseError(`The Aura API returned invalid JSON (HTTP ${response.status}).`)
  }
  return decode(body)
}
export function requireRecord(value: unknown, resource: string): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new ApiResponseError(`The Aura API returned an invalid ${resource} response.`)
  }
  return value as Record<string, unknown>
}
async function readErrorMessage(response: Response): Promise<string> {
  let body: unknown
  try {
    body = await response.json()
  } catch {
    return `Aura API request failed (HTTP ${response.status}).`
  }
  if (typeof body !== 'object' || body === null) return `Aura API request failed (HTTP ${response.status}).`
  const detail = (body as Record<string, unknown>).detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const messages = detail.flatMap(item => {
      if (typeof item !== 'object' || item === null) return []
      const message = (item as Record<string, unknown>).msg
      return typeof message === 'string' ? [message] : []
    })
    if (messages.length) return messages.join(' ')
  }
  return `Aura API request failed (HTTP ${response.status}).`
}

/** Binary previews use the same account token and 401 handling as JSON requests. */
export async function requestApiBlob(path: string, signal?: AbortSignal): Promise<Blob> {
  const url = `${API_BASE_URL.replace(/\/+$/, '')}/${path.replace(/^\/+/, '')}`
  const headers = new Headers()
  const token = await authTokenProvider()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  let response: Response
  try { response = await fetch(url, { method: 'GET', headers, signal }) }
  catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiUnavailableError(`Could not reach the Aura API at ${API_BASE_URL}.`)
  }
  if (!response.ok) {
    if (response.status === 401 && token) unauthorizedHandler(token)
    throw new ApiHttpError(response.status, await readErrorMessage(response))
  }
  return response.blob()
}
