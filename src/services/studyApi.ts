import {
  requestApi,
  requireRecord,
  ApiUnavailableError,
  ApiResponseError,
} from './apiClient'
import type {
  Citation,
  ChatMessage,
  Course,
  LearningHistoryEntry,
  LearningInsights,
  PrerequisiteRecommendation,
  QuizAnswerSubmission,
  QuizGenerationRequest,
  QuizQuestion,
  QuizResult,
  AssessmentResult,
  StudyMaterial,
  StudyToolContent,
  Topic,
  TopicMastery,
  ConceptMastery,
  TutorRequest,
  TutorResponse,
} from '../types/study'
type ProcessingStatus =
  | 'success'
  | 'partial'
  | 'empty'
  | 'not_configured'
  | 'error'
export type SourceUploadResult = {
  sourceId: string
  courseId: string
  filename: string
  fileType: string
  uploadStatus: 'uploaded'
  processingStatus: ProcessingStatus
  contentUnitCount: number
  warnings: string[]
  createdAt: string
}
type StudyTool = 'notes' | 'summary' | 'flashcards' | 'quizzes'
type StudentMasteryResponse = {
  student_id: number
  mastery: Array<{
    student_id: number
    topic_id: number
    topic_name: string
    mastery_score: number
    last_updated: string
  }>
}
type CourseDto = {
  course_id: number
  course_name: string
}
type CoursesResponse = {
  courses: CourseDto[]
}
const endpoints = {
  courses: 'courses',
  uploadSource: (courseId: string) =>
    `courses/${encodeURIComponent(courseId)}/sources`,
  studentMastery: (studentId: number) =>
    `students/${studentId}/mastery`,
}
let courseIds: Record<string, number> = {}
export function resolveCourseId(courseName: string): string {
  const courseId = courseIds[courseName]
  if (courseId === undefined) {
    throw new Error(
      `Course "${courseName}" is not available in the backend.`
    )
  }
  return String(courseId)
}
/**
 * Fetch real courses from FastAPI.
 */
export async function listCourses(): Promise<Course[]> {
  return requestApi(
    endpoints.courses,
    { method: 'GET' },
    decodeCourses,
  )
}
function decodeCourses(value: unknown): Course[] {
  const record = requireRecord(value, 'courses')
  if (!Array.isArray(record.courses)) {
    throw new ApiResponseError(
      'The Aura API returned an invalid courses response.',
    )
  }
  const courses = (record as unknown as CoursesResponse).courses.map((item) => {
    if (
      typeof item.course_id !== 'number' ||
      typeof item.course_name !== 'string'
    ) {
      throw new ApiResponseError(
        'The Aura API returned an invalid course record.',
      )
    }
    return {
      id: String(item.course_id),
      title: item.course_name,
    }
  })
  courseIds = Object.fromEntries(courses.map(item => [item.title, Number(item.id)]))
  return courses
}
export async function uploadCourseSource(
  courseId: string,
  file: File,
): Promise<SourceUploadResult> {
  const form = new FormData()
  form.append('file', file, file.name)
  return requestApi(
    endpoints.uploadSource(courseId),
    { method: 'POST', body: form },
    decodeSourceUpload,
  )
}
export async function listCourseMaterials(
  _courseId: string,
): Promise<StudyMaterial[]> {
  return unavailable('material listing')
}
export async function generateSourceEmbeddings(sourceId: string): Promise<number> {
  const id = requireBackendId(sourceId, 'Source')
  return requestApi(
    `sources/${id}/generate-embeddings`,
    { method: 'POST' },
    value => {
      const record = requireRecord(value, 'embeddings')
      if (record.status !== 'completed' ||
          typeof record.embedded_count !== 'number' ||
          !Number.isInteger(record.embedded_count) || record.embedded_count <= 0) {
        throw new ApiResponseError('The file is not ready for search: embeddings did not complete.')
      }
      if (String(record.source_id) !== String(id)) {
        throw new ApiResponseError('The embeddings response refers to a different source.')
      }
      return record.embedded_count
    },
  )
}
function requireBackendId(value: string, label: string): number {
  if (!/^\d+$/.test(value) || !Number.isSafeInteger(Number(value)) || Number(value) <= 0) {
    throw new Error(`${label} must be a real backend ID. Select a course or upload a file first.`)
  }
  return Number(value)
}
export async function askTutor(
  request: TutorRequest & { history?: Array<{ role: 'user' | 'assistant'; content: string }> },
): Promise<TutorResponse> {
  const courseId = requireBackendId(request.courseId, 'Course')
  const sourceId = request.materialId ? requireBackendId(request.materialId, 'Source') : null
  type BackendSource = {
    chunk_id: string | number
    source_id: string | number
    source_name: string
    page?: number | null
    page_number?: number | null
    slide?: number | null
    slide_number?: number | null
    timestamp_start?: number | null
    timestamp_seconds?: number | null
    timestamp_end?: number | null
    content?: string
  }
  type BackendChatResponse = {
    answer: string
    sources?: BackendSource[]
    citation_validation?: {
      valid?: boolean
    }
  }
  const response = await requestApi(
    'chat',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question: request.question,
        top_k: 3,
        course_id: courseId,
        source_id: sourceId,
        history: request.history?.slice(-8) ?? [],
      }),
    },
    (value) => {
      const record = requireRecord(value, 'chat response')
      if (typeof record.answer !== 'string') {
        throw new ApiResponseError(
          'The Aura API returned an invalid chat response.',
        )
      }
      if (record.sources !== undefined && !Array.isArray(record.sources)) {
        throw new ApiResponseError('The Aura API returned invalid chat sources.')
      }
      if (record.citation_validation !== undefined) {
        requireRecord(record.citation_validation, 'citation validation')
      }
      return record as unknown as BackendChatResponse
    },
  )
  const citations: Citation[] = (response.sources ?? []).map(
    (source, index) => {
      const sourceRecord = requireRecord(source, 'chat source')
      if ((typeof sourceRecord.source_id !== 'number' && typeof sourceRecord.source_id !== 'string') ||
          (typeof sourceRecord.chunk_id !== 'number' && typeof sourceRecord.chunk_id !== 'string')) {
        throw new ApiResponseError('The Aura API returned a source without valid IDs.')
      }
      const slide = source.slide ?? source.slide_number
      const page = source.page ?? source.page_number
      const seconds = source.timestamp_start ?? source.timestamp_seconds
      let location: Citation['location']
      if (typeof slide === 'number' && Number.isFinite(slide) && slide > 0) {
        location = { kind: 'slide', slide }
      } else if (typeof page === 'number' && Number.isFinite(page) && page > 0) {
        location = { kind: 'pdf_page', page }
      } else if (typeof seconds === 'number' && Number.isFinite(seconds) && seconds >= 0) {
        location = {
          kind: 'video_timestamp',
          seconds,
        }
      } else {
        location = { kind: 'pdf_page', page: 0 }
      }
      return {
        id: `source-${source.source_id}-${source.chunk_id}-${index}`,
        materialId: String(source.source_id),
        sourceId: String(source.source_id),
        location,
        excerpt: source.content,
        isDemo: false,
      }
    },
  )
  const groundingStatus: TutorResponse['groundingStatus'] =
    response.citation_validation?.valid === true
      ? 'grounded'
      : response.sources?.length
        ? 'partially_covered'
        : 'not_covered'
  return {
    message: {
      id: `tutor-${crypto.randomUUID()}`,
      role: 'tutor',
      content: response.answer,
      citationIds: citations.map((citation) => citation.id),
      isDemo: false,
    },
    citations,
    groundingStatus,
  }
}
export async function getStudyToolContent(
  _courseId: string,
  _materialId: string,
  _tool: StudyTool,
): Promise<StudyToolContent> {
  return unavailable('AI study tools')
}
export async function generateQuiz(
  _request: QuizGenerationRequest,
): Promise<QuizQuestion[]> {
  return unavailable('quiz generation')
}
export async function submitQuizAnswers(
  _submission: QuizAnswerSubmission,
): Promise<AssessmentResult> {
  return unavailable('quiz answer submission')
}
/**
 * Fetches real topic mastery from FastAPI.
 * Student ID 1 is used temporarily because it was
 * verified in the Swagger response.
 */
export async function getLearningInsights(
  courseId: string,
): Promise<LearningInsights> {
  const studentId = 1
  const masteryRecords = await requestApi(
    `${endpoints.studentMastery(studentId)}?course_id=${encodeURIComponent(courseId)}`,
    { method: 'GET' },
    decodeStudentMastery,
  )
  const topicMastery: TopicMastery[] = masteryRecords.map((item) => {
    const score = Math.max(
      0,
      Math.min(100, item.mastery_score * 100),
    )
    const level: TopicMastery['level'] =
      score >= 85
        ? 'strong'
        : score >= 65
          ? 'proficient'
          : score > 0
            ? 'developing'
            : 'not_started'
    return {
      topicId: String(item.topic_id),
      topicName: item.topic_name,
      level,
      score,
      recommendation: `Review ${item.topic_name} to reinforce your understanding.`,
      updatedAt: item.last_updated,
      isDemo: false,
    }
  })
  return {
    courseId,
    topics: [],
    conceptMastery: [],
    topicMastery,
    recommendations: [],
    history: [],
    quizResults: [],
    isDemo: false,
  }
}
function decodeStudentMastery(
  value: unknown,
): StudentMasteryResponse['mastery'] {
  const record = requireRecord(value, 'student mastery')
  if (
    typeof record.student_id !== 'number' ||
    !Array.isArray(record.mastery)
  ) {
    throw new ApiResponseError(
      'The Aura API returned an invalid student mastery response.',
    )
  }
  return record.mastery.map((item) => {
    const mastery = requireRecord(item, 'topic mastery')
    if (
      typeof mastery.student_id !== 'number' ||
      typeof mastery.topic_id !== 'number' ||
      typeof mastery.topic_name !== 'string' ||
      typeof mastery.mastery_score !== 'number' ||
      !Number.isFinite(mastery.mastery_score) ||
      typeof mastery.last_updated !== 'string'
    ) {
      throw new ApiResponseError(
        'The Aura API returned an invalid topic mastery record.',
      )
    }
    return {
      student_id: mastery.student_id,
      topic_id: mastery.topic_id,
      topic_name: mastery.topic_name,
      mastery_score: mastery.mastery_score,
      last_updated: mastery.last_updated,
    }
  })
}
function unavailable<T>(feature: string): Promise<T> {
  return Promise.reject(
    new ApiUnavailableError(
      `${feature} is not connected: its FastAPI endpoint contract has not been provided.`,
    ),
  )
}
function decodeSourceUpload(value: unknown): SourceUploadResult {
  const dto = requireRecord(value, 'source upload')
  if (
    (typeof dto.source_id !== 'number' &&
      typeof dto.source_id !== 'string') ||
    typeof dto.course_id !== 'number' ||
    typeof dto.source_name !== 'string' ||
    typeof dto.source_type !== 'string' ||
    typeof dto.status !== 'string' ||
    typeof dto.content_units !== 'number' ||
    !Array.isArray(dto.warnings) ||
    !dto.warnings.every((warning) => typeof warning === 'string')
  ) {
    throw new ApiResponseError(
      'The Aura API returned an invalid source upload response.',
    )
  }
  const validStatuses = [
    'success',
    'partial',
    'empty',
    'not_configured',
    'error',
  ] as const
  if (!validStatuses.includes(dto.status as (typeof validStatuses)[number])) {
    throw new ApiResponseError(
      'The Aura API returned an unknown processing status.',
    )
  }
  return {
    sourceId: String(dto.source_id),
    courseId: String(dto.course_id),
    filename: dto.source_name,
    fileType: dto.source_type,
    uploadStatus: 'uploaded',
    processingStatus: dto.status as SourceUploadResult['processingStatus'],
    contentUnitCount: dto.content_units,
    warnings: dto.warnings,
    createdAt: new Date().toISOString(),
  }
}
export type { StudyTool }
export type {
  Citation,
  ChatMessage,
  ConceptMastery,
  LearningHistoryEntry,
  LearningInsights,
  PrerequisiteRecommendation,
  QuizAnswerSubmission,
  QuizGenerationRequest,
  QuizQuestion,
  QuizResult,
  AssessmentResult,
  StudyMaterial,
  StudyToolContent,
  Topic,
  TopicMastery,
  TutorRequest,
  TutorResponse,
}
