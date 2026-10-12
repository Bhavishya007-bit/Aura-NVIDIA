/** Browser-local drafts; account identity and API permissions still come from the server. */
export function readWorkspace<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return fallback
    const value: unknown = JSON.parse(raw)
    if (!value || typeof value !== 'object' || Array.isArray(value)) return fallback
    return value as T
  } catch { return fallback }
}
export function saveWorkspace(key: string, value: unknown): void {
  try { localStorage.setItem(key, JSON.stringify(value)) }
  catch { window.dispatchEvent(new Event('aura:workspace-save-failed')) }
}
export function navigationKey(userId: string): string {
  return `aura.navigation.v1:${userId}`
}
