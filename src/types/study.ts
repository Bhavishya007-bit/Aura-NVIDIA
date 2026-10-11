/** Offsets in videos are measured in seconds from the media start. */
export type SourceLocation =
  | { kind: 'pdf_page'; page: number }
  | { kind: 'slide'; slide: number }
  | { kind: 'video_timestamp'; seconds: number }

/** IDs are stable opaque keys; relationships never depend on labels or array order. */
export interface Course {
  id: string
  title: string
  description?: string
}

export interface StudyMaterial {
  id: string
  courseId: string
  title: string
  type: 'pdf' | 'slides' | 'video' | 'document'
  status: 'demo' | 'uploaded' | 'processing' | 'ready' | 'failed'
  sourceId: string
}

export interface Citation {
  id: string
  materialId: string
  sourceId: string
  location: SourceLocation
  excerpt?: string
  isDemo: boolean
}

export interface Concept {
  id: string
  courseId: string
  topicId: string
  title: string
  prerequisiteConceptIds: string[]
  sourceLocations: Array<{ materialId: string; location: SourceLocation }>
  isDemo: boolean
}

export interface Topic {
  id: string
  courseId: string
  title: string
  conceptIds: string[]
  prerequisiteTopicIds: string[]
  sourceLocations: Array<{ materialId: string; location: SourceLocation }>
  isDemo: boolean
}

export interface ConceptMastery {
  conceptId: string
  level: 'not_started' | 'developing' | 'proficient' | 'strong'
  /** Optional percentage from 0 to 100; not a measured learning gain. */
  score?: number
  updatedAt?: string
  isDemo: boolean
}

export interface PrerequisiteRecommendation {
  id: string
  topicId: string
  conceptIds: string[]
  reason: string
  isDemo: boolean
}

export interface ChatMessage {
  id: string
  role: 'student' | 'tutor'
  content: string
  citationIds: string[]
  isDemo: boolean
}

export interface TutorRequest {
  courseId: string
  materialId?: string
  question: string
}

export interface TutorResponse {
  message: ChatMessage
  citations: Citation[]
  groundingStatus: 'grounded' | 'partially_covered' | 'not_covered' | 'unavailable'
}

export interface Note {
  id: string
  courseId: string
  materialId: string
  topicId?: string
  title: string
  content: string
  citationIds: string[]
}

export interface Summary {
  id: string
  courseId: string
  materialId: string
  content: string
  citationIds: string[]
}

export interface Flashcard {
  id: string
  courseId: string
  materialId: string
  topicId?: string
  question: string
  answer: string
  citationIds: string[]
}

export type StudyToolContent =
  | { kind: 'notes'; items: Note[] }
  | { kind: 'summary'; item: Summary }
  | { kind: 'flashcards'; items: Flashcard[] }
  | { kind: 'quizzes'; items: QuizQuestion[] }

export interface QuizQuestion {
  id: string
  courseId: string
  topicId: string
  difficulty: 'beginner' | 'intermediate' | 'advanced'
  prompt: string
  choices: Array<{ id: string; text: string }>
  correctChoiceId?: string
  explanation?: string
  citationIds: string[]
  isDemo: boolean
}

export interface QuizResult {
  id: string
  courseId: string
  questionIds: string[]
  /** Percentage from 0 to 100. */
  score: number
  /** ISO 8601 timestamp. */
  completedAt: string
  isDemo: boolean
}

export interface QuizAnswerSubmission {
  courseId: string
  assessmentType?: AssessmentType
  materialId?: string
  topicId?: string
  answers: Array<{ questionId: string; choiceId?: string; freeResponse?: string }>
}

export type AssessmentType = 'chapter' | 'topic' | 'material' | 'weak_areas'

export interface QuizGenerationRequest {
  courseId: string
  assessmentType: AssessmentType
  materialId?: string
  topicId?: string
  questionCount: number
}

export interface TopicAssessmentPerformance {
  topicId: string
  score: number
  questionCount: number
}

export interface AssessmentResult extends QuizResult {
  topicPerformance: TopicAssessmentPerformance[]
  recommendedAction?: string
}

export interface LearningHistoryEntry {
  id: string
  courseId: string
  conceptId?: string
  activityType: 'study' | 'quiz' | 'review'
  occurredAt: string
  durationSeconds?: number
  score?: number
  isDemo: boolean
}

export interface TopicMastery {
  topicId: string
  topicName?: string
  level: 'not_started' | 'developing' | 'proficient' | 'strong'
  /** Optional percentage from 0 to 100; not a measured learning gain. */
  score?: number
  recommendation?: string
  updatedAt?: string
  isDemo: boolean
}

export interface LearningInsights {
  courseId: string
  topics: Topic[]
  conceptMastery: ConceptMastery[]
  topicMastery: TopicMastery[]
  recommendations: PrerequisiteRecommendation[]
  history: LearningHistoryEntry[]
  quizResults: QuizResult[]
  isDemo: boolean
}

export interface StudyWorkspace {
  course: Course
  materials: StudyMaterial[]
  concepts: Concept[]
  conceptMastery: ConceptMastery[]
  topics: Topic[]
  prerequisiteRecommendations: PrerequisiteRecommendation[]
  mastery: TopicMastery[]
  citations: Citation[]
  sampleQuestion: QuizQuestion
}
