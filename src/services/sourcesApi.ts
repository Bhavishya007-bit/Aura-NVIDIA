export { uploadCourseSource } from './studyApi'
export type { SourceUploadResult as SourceUploadResponse } from './studyApi'

export type ProcessingStatus = 'success' | 'partial' | 'empty' | 'not_configured' | 'error'
