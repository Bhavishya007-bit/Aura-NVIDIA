
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

type SourceUploadDto = {
  source_id: string
  course_id: string
  filename: string
  file_type: string
  upload_status: 'uploaded'
  processing_status: ProcessingStatus
  content_unit_count: number
  warnings: string[]
  created_at: string
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

const demoCourseIds: Record<string, string> = {
  'Foundations of Biology': 'foundations-of-biology',
  'Chemistry II': 'chemistry-ii',
  'Environmental Science': 'environmental-science',
}

export function resolveCourseId(courseName: string): string {
  return demoCourseIds[courseName] || 'demo-course'
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

  return (record as unknown as CoursesResponse).courses.map((item) => {
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

export async function askTutor(
  _request: TutorRequest,
): Promise<TutorResponse> {
  return unavailable('AI Tutor')
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
  const dto = requireRecord(
    value,
    'source upload',
  ) as unknown as SourceUploadDto

  if (
    typeof dto.source_id !== 'string' ||
    typeof dto.course_id !== 'string' ||
    typeof dto.filename !== 'string' ||
    typeof dto.file_type !== 'string' ||
    dto.upload_status !== 'uploaded' ||
    ![
      'success',
      'partial',
      'empty',
      'not_configured',
      'error',
    ].includes(dto.processing_status) ||
    typeof dto.content_unit_count !== 'number' ||
    !Array.isArray(dto.warnings) ||
    !dto.warnings.every((warning) => typeof warning === 'string') ||
    typeof dto.created_at !== 'string'
  ) {
    throw new ApiResponseError(
      'The Aura API returned an invalid source upload response.',
    )
  }

  return {
    sourceId: dto.source_id,
    courseId: dto.course_id,
    filename: dto.filename,
    fileType: dto.file_type,
    uploadStatus: dto.upload_status,
    processingStatus: dto.processing_status,
    contentUnitCount: dto.content_unit_count,
    warnings: dto.warnings,
    createdAt: dto.created_at,
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
