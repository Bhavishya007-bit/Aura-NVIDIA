import { resolveCourseId } from './studyApi'
import { studyDemoWorkspaces } from '../data/studyDemo'
import type { StudyWorkspace, TutorResponse } from '../types/study'

export interface StudyDataAdapter {
  getWorkspace(courseId: string): StudyWorkspace
}

// The current app has no workspace-read API contract; keep demo behavior behind
// this adapter until the backend team provides one. No network endpoint is assumed.
const demoStudyDataAdapter: StudyDataAdapter = {
  getWorkspace(courseId) {
    const workspace = studyDemoWorkspaces[courseId]
    if (workspace) return workspace

    return {
      course: { id: courseId, title: 'Selected course' },
      materials: [],
      concepts: [],
      conceptMastery: [],
      topics: [],
      prerequisiteRecommendations: [],
      mastery: [],
      citations: [],
      sampleQuestion: {
        id: 'demo-question-empty',
        courseId,
        topicId: 'no-topic',
        difficulty: 'beginner',
        prompt: 'No sample assessment is available for this course yet.',
        choices: [],
        citationIds: [],
        isDemo: true,
      },
    }
  },
}

export function getStudyWorkspace(courseName: string): StudyWorkspace {
  return demoStudyDataAdapter.getWorkspace(resolveCourseId(courseName))
}

export function getDemoTutorFallback(question: string): TutorResponse {
  return {
    message: {
      id: `demo-tutor-${Date.now()}`,
      role: 'tutor',
      content: `Demo fallback only: Aura could not connect to a source-grounded tutor, so it did not generate an answer to “${question}”.`,
      citationIds: [],
      isDemo: true,
    },
    citations: [],
    groundingStatus: 'unavailable',
  }
}
