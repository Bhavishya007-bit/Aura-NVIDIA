import { ApiHttpError, requestApi, requireRecord } from './apiClient'

export type GenerationSupport = { multi_chat: boolean; multi_study: boolean; multi_agents: boolean; study_jobs: boolean; study_v2?: boolean }
export const legacySupport: GenerationSupport = { multi_chat: false, multi_study: false, multi_agents: false, study_jobs: false }
/** Optional additive contract. Old deployments remain fully usable for single materials. */
export async function generationSupport(signal?: AbortSignal): Promise<GenerationSupport> {
  try {
    return await requestApi('study/capabilities', { method: 'GET', signal }, value => {
      const row = requireRecord(value, 'study capabilities')
      return { multi_chat: row.multi_chat === true, multi_study: row.multi_study === true, multi_agents: row.multi_agents === true, study_jobs: row.study_jobs === true, study_v2: row.study_v2 === true }
    })
  } catch (error) {
    if (signal?.aborted || error instanceof ApiHttpError && error.status === 401) throw error
    return legacySupport
  }
}
export const multiMaterialNotice = 'This tool currently supports one material at a time. Choose one to continue; your study sets are saved.'
export const materialIds = (ids: string[]) => {
  if (ids.length > 5 || new Set(ids).size !== ids.length || ids.some(id => !/^[1-9]\d*$/.test(id) || !Number.isSafeInteger(Number(id)))) throw new Error('Choose up to 5 different materials.')
  return ids.map(Number)
}
