import { useMemo, useState } from 'react'
import { getStudyWorkspace } from '../services/studyData'
import { generateQuiz, resolveCourseId, submitQuizAnswers } from '../services/studyApi'
import { ApiUnavailableError } from '../services/apiClient'
import type { AssessmentResult, AssessmentType, QuizQuestion } from '../types/study'
import './AssessmentPage.css'

type Page = 'Dashboard' | 'My Courses' | 'Upload Materials' | 'AI Tutor' | 'Quizzes' | 'Progress'
const assessmentTypes: Array<{ id: AssessmentType; title: string; description: string; icon: string }> = [
  { id: 'chapter', title: 'Chapter Assessment', description: 'Check your understanding across all topics in a chapter.', icon: '▤' },
  { id: 'topic', title: 'Topic Practice', description: 'Focus on one selected topic or concept.', icon: '◎' },
  { id: 'material', title: 'Uploaded Material', description: 'Assess content from a selected PDF, slide deck, or note.', icon: '↑' },
  { id: 'weak_areas', title: 'Weak Areas', description: 'Revisit topics where your demo mastery needs support.', icon: '△' },
]

export default function AssessmentPage({ course, setPage }: { course: string; setPage: (page: Page) => void }) {
  const workspace = useMemo(() => getStudyWorkspace(course), [course])
  const [assessmentType, setAssessmentType] = useState<AssessmentType>('chapter')
  const [materialId, setMaterialId] = useState(workspace.materials[0]?.id ?? '')
  const [topicId, setTopicId] = useState(workspace.topics[0]?.id ?? '')
  const [questionCount, setQuestionCount] = useState(10)
  const [questions, setQuestions] = useState<QuizQuestion[]>([])
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [questionIndex, setQuestionIndex] = useState(0)
  const [result, setResult] = useState<AssessmentResult | null>(null)
  const [step, setStep] = useState<'setup' | 'taking' | 'results'>('setup')
  const [demoMode, setDemoMode] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const selectedMaterial = workspace.materials.find((item) => item.id === materialId)
  const selectedTopic = workspace.topics.find((item) => item.id === topicId)
  const weakTopics = workspace.mastery.filter((item) => item.score !== undefined && item.score < 65)
  const coverageTopics = assessmentType === 'topic'
    ? selectedTopic ? [selectedTopic] : []
    : assessmentType === 'weak_areas'
      ? workspace.topics.filter((topic) => weakTopics.some((item) => item.topicId === topic.id))
      : (assessmentType === 'chapter' || assessmentType === 'material') && selectedMaterial
        ? workspace.topics.filter((topic) => topic.sourceLocations.some((location) => location.materialId === selectedMaterial.id))
        : workspace.topics
  const currentQuestion = questions[questionIndex]
  const canStart = assessmentType !== 'topic' || Boolean(selectedTopic)

  async function startAssessment() {
    setBusy(true)
    setError('')
    setAnswers({})
    setResult(null)
    try {
      const generated = await generateQuiz({
        courseId: resolveCourseId(course),
        assessmentType,
        materialId: assessmentType === 'material' || assessmentType === 'chapter' ? materialId || undefined : undefined,
        topicId: assessmentType === 'topic' ? topicId : undefined,
        questionCount,
      })
      if (!generated.length) {
        setError('The assessment service returned no questions.')
        return
      }
      setQuestions(generated)
      setQuestionIndex(0)
      setDemoMode(generated.every((question) => question.isDemo))
      setStep('taking')
    } catch (requestError) {
      if (!(requestError instanceof ApiUnavailableError)) {
        setError(requestError instanceof Error ? requestError.message : 'Could not start this assessment.')
        return
      }
      const sample = workspace.sampleQuestion
      const sampleMaterialMatches = sample.citationIds.some((citationId) =>
        workspace.citations.some((citation) => citation.id === citationId && citation.materialId === materialId),
      )
      const sampleTopicMatches = assessmentType !== 'topic' || sample.topicId === topicId
      const sampleIncluded = coverageTopics.some((topic) => topic.id === sample.topicId)
      if (sample.isDemo && sample.choices.length > 0 && sampleMaterialMatches && sampleTopicMatches && sampleIncluded) {
        setQuestions([sample])
        setQuestionIndex(0)
        setDemoMode(true)
        setStep('taking')
      } else {
        setError('Quiz generation is not connected yet. No assessment was created. The available sample question does not match this selection.')
      }
    } finally {
      setBusy(false)
    }
  }

  async function finishAssessment() {
    setBusy(true)
    setError('')
    const submittedAnswers = questions.map((question) => ({ questionId: question.id, choiceId: answers[question.id] }))
    if (demoMode) {
      const correctCount = questions.filter((question) => answers[question.id] === question.correctChoiceId).length
      const score = Math.round((correctCount / questions.length) * 100)
      const topicIdForResult = questions[0]?.topicId
      setResult({
        id: `demo-result-${Date.now()}`,
        courseId: resolveCourseId(course),
        questionIds: questions.map((question) => question.id),
        score,
        completedAt: new Date().toISOString(),
        isDemo: true,
        topicPerformance: topicIdForResult ? [{ topicId: topicIdForResult, score, questionCount: questions.length }] : [],
        recommendedAction: score < 70 ? 'Review the source material for this topic, then try another practice session.' : 'Continue to the next topic and revisit this concept later to reinforce recall.',
      })
      setStep('results')
      setBusy(false)
      return
    }
    try {
      const assessmentResult = await submitQuizAnswers({
        courseId: resolveCourseId(course),
        assessmentType,
        materialId: selectedMaterial?.id,
        topicId: assessmentType === 'topic' ? topicId : undefined,
        answers: submittedAnswers,
      })
      setResult(assessmentResult)
      setStep('results')
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not submit this assessment.')
    } finally {
      setBusy(false)
    }
  }

  function restart() {
    setStep('setup')
    setQuestions([])
    setAnswers({})
    setResult(null)
    setError('')
  }

  return (
    <div className="assessment-page">
      <header className="assessment-heading">
        <div><span className="assessment-eyebrow">ASSESSMENT CENTER <b>DEMO DATA</b></span><h1>Assess your understanding</h1><p>Measure learning across a chapter, material, or topic.</p></div>
        <span className="assessment-stamp">◷ &nbsp;Self-paced learning</span>
      </header>

      {step === 'setup' && <>
        <div className="assessment-type-grid" aria-label="Assessment type">
          {assessmentTypes.map((item) => <button type="button" key={item.id} className={`assessment-type-card ${assessmentType === item.id ? 'selected' : ''}`} aria-pressed={assessmentType === item.id} onClick={() => { setAssessmentType(item.id); setError('') }}>
            <span className="assessment-type-icon">{item.icon}</span><strong>{item.title}</strong><small>{item.description}</small>
          </button>)}
        </div>

        <div className="assessment-content-grid">
          <section className="assessment-config-card">
            <div className="assessment-section-heading"><div><span>YOUR NEXT ASSESSMENT</span><h2>{assessmentTypes.find((item) => item.id === assessmentType)?.title}</h2><p>Set up a focused assessment using available course materials.</p></div><span className="demo-pill">DEMO</span></div>
            <div className="assessment-selectors">
              <label>Course<select value={course} disabled><option>{course}</option></select></label>
              {(assessmentType === 'chapter' || assessmentType === 'material') && <label>Material / Chapter<select value={materialId} onChange={(event) => setMaterialId(event.target.value)} disabled={!workspace.materials.length}>
                {workspace.materials.length ? workspace.materials.map((material) => <option key={material.id} value={material.id}>{material.title}</option>) : <option value="">No demo materials available</option>}
              </select></label>}
              {assessmentType === 'topic' && <label>Topic<select value={topicId} onChange={(event) => setTopicId(event.target.value)} disabled={!workspace.topics.length}>
                {workspace.topics.length ? workspace.topics.map((topic) => <option key={topic.id} value={topic.id}>{topic.title}</option>) : <option value="">No detected topics available</option>}
              </select></label>}
              {assessmentType === 'weak_areas' && <p className="weak-area-caption">Topics below 65% demo mastery are included.</p>}
            </div>
            {assessmentType === 'material' && <p className="assessment-demo-note">Demo materials are examples, not uploaded files. Backend material selection is not connected yet.</p>}

            <div className="assessment-topic-preview">
              <div><strong>Detected topics</strong><span>{coverageTopics.length} included {workspace.topics.some((topic) => topic.isDemo) ? '· demo' : ''}</span></div>
              <div className="assessment-topic-chips">{coverageTopics.length
                ? coverageTopics.map((topic) => <span key={topic.id}>{topic.title}</span>)
                : <small>{assessmentType === 'weak_areas' ? 'No low-mastery topics are currently available.' : 'No topics are connected to this selection.'}</small>}</div>
            </div>

            <div className="assessment-summary-grid">
              <label className="assessment-summary-item"><span>Question count</span><select value={questionCount} onChange={(event) => setQuestionCount(Number(event.target.value))}><option value={5}>5 questions</option><option value={10}>10 questions</option><option value={15}>15 questions</option><option value={25}>25 questions</option></select></label>
              <div className="assessment-summary-item"><span>Estimated time</span><strong>~ {questionCount * 1} min</strong></div>
              <div className="assessment-summary-item"><span>Difficulty</span><strong>Adaptive <small>Backend required</small></strong></div>
              <div className="assessment-summary-item"><span>Topic coverage</span><strong>{coverageTopics.length ? '100%' : '—'}</strong></div>
            </div>
            <p className="assessment-demo-note">Demo fallback can use only an existing matching sample question; selected question count and full topic coverage require the assessment backend.</p>
            {error && <div className="assessment-error" role="alert">{error}</div>}
            <button type="button" className="assessment-primary-button" disabled={busy || !canStart || !coverageTopics.length} onClick={startAssessment}>{busy ? 'Preparing…' : 'Start Assessment'} <span>→</span></button>
          </section>

          <aside className="assessment-side-card">
            <div className="assessment-section-heading"><div><span>TOPIC DISTRIBUTION</span><h2>Coverage preview</h2></div><span className="preview-icon">◉</span></div>
            {coverageTopics.length ? <div className="coverage-list">{coverageTopics.map((topic, index) => <div className="coverage-row" key={topic.id}><span><i className={`coverage-color color-${index % 5}`} />{topic.title}</span><small>{assessmentType === 'topic' ? questionCount : Math.max(1, Math.round(questionCount / coverageTopics.length))}</small></div>)}</div> : <p className="assessment-side-empty">Topic distribution appears when material topics are available.</p>}
            <p className="coverage-caption">Topic list and question distribution are illustrative until the assessment API is connected.</p>
          </aside>
        </div>
        <div className="assessment-bottom-grid">
          <section className="assessment-how-card"><strong>How it works</strong><div><span><b>1</b>Choose assessment type</span><i>→</i><span><b>2</b>Confirm scope</span><i>→</i><span><b>3</b>Complete assessment</span><i>→</i><span><b>4</b>Review results</span></div></section>
          <section className="assessment-history-card"><div><strong>Recent assessments</strong><span>DEMO</span></div>{[['Chapter 4 Assessment','Biology · Cellular Energy','80%'],['Topic Practice · Photosynthesis','Biology · Chapter 4','75%'],['Weak Areas Practice','Biology · Chapter 3','62%']].map(([name,detail,score]) => <div className="assessment-history-row" key={name}><span><b>{name}</b><small>{detail}</small></span><strong>{score}</strong></div>)}</section>
        </div>
      </>}

      {step === 'taking' && currentQuestion && <section className="assessment-taking-card">
        <div className="assessment-section-heading"><div><span>{assessmentTypes.find((item) => item.id === assessmentType)?.title.toUpperCase()} · {demoMode ? 'DEMO QUESTION' : 'ASSESSMENT'}</span><h2>{selectedMaterial?.title ?? selectedTopic?.title ?? course}</h2></div><span className="assessment-step-count">{questionIndex + 1} / {questions.length}</span></div>
        <div className="assessment-progress"><span style={{ width: `${((questionIndex + 1) / questions.length) * 100}%` }} /></div>
        <h3>{currentQuestion.prompt}</h3>
        <p className="assessment-question-note">Choose the best answer. {demoMode && 'One existing sample question · not generated by AI.'}</p>
        <div className="assessment-answer-options">{currentQuestion.choices.map((choice, index) => <button type="button" key={choice.id} className={answers[currentQuestion.id] === choice.id ? 'chosen' : ''} onClick={() => setAnswers((current) => ({ ...current, [currentQuestion.id]: choice.id }))}><span>{String.fromCharCode(65 + index)}</span>{choice.text}</button>)}</div>
        {error && <div className="assessment-error" role="alert">{error}</div>}
        <div className="assessment-taking-actions"><button type="button" className="assessment-secondary-button" onClick={restart}>Exit assessment</button>{questionIndex < questions.length - 1
          ? <button type="button" className="assessment-primary-button" disabled={!answers[currentQuestion.id]} onClick={() => setQuestionIndex((index) => index + 1)}>Next question <span>→</span></button>
          : <button type="button" className="assessment-primary-button" disabled={!answers[currentQuestion.id] || busy} onClick={finishAssessment}>{busy ? 'Submitting…' : 'Submit assessment'} <span>→</span></button>}</div>
      </section>}

      {step === 'results' && result && <AssessmentResults result={result} questions={questions} workspace={workspace} onRestart={restart} onStudy={() => setPage('AI Tutor')} />}
    </div>
  )
}

function AssessmentResults({ result, questions, workspace, onRestart, onStudy }: { result: AssessmentResult; questions: QuizQuestion[]; workspace: ReturnType<typeof getStudyWorkspace>; onRestart: () => void; onStudy: () => void }) {
  const topicScores = result.topicPerformance.map((performance) => ({
    title: workspace.topics.find((topic) => topic.id === performance.topicId)?.title ?? 'Selected topic',
    score: performance.score,
  }))
  const strongTopics = topicScores.filter((topic) => topic.score >= 70)
  const reviewTopics = topicScores.filter((topic) => topic.score < 70)
  return <section className="assessment-results-card">
    <div className="assessment-results-heading"><div><span>ASSESSMENT COMPLETE <b>{result.isDemo ? 'DEMO RESULT' : 'BACKEND RESULT'}</b></span><h2>Your results</h2><p>{questions.length} question{questions.length === 1 ? '' : 's'} · Completed {new Date(result.completedAt).toLocaleDateString()}</p></div><div className="assessment-result-score"><strong>{result.score}%</strong><small>Overall score</small></div></div>
    <div className="assessment-results-grid">
      <div><h3>Topic-wise performance</h3>{topicScores.length ? topicScores.map((topic) => <div className="result-topic-row" key={topic.title}><span>{topic.title}</span><strong>{topic.score}%</strong><i><b style={{ width: `${topic.score}%` }} /></i></div>) : <p>No topic breakdown was returned.</p>}</div>
      <div><h3>Strong topics</h3>{strongTopics.length ? strongTopics.map((topic) => <p className="result-insight strong-insight" key={topic.title}>✓ &nbsp;{topic.title} · {topic.score}%</p>) : <p>No strong topics identified in this assessment.</p>}</div>
      <div><h3>Topics needing review</h3>{reviewTopics.length ? reviewTopics.map((topic) => <p className="result-insight review-insight" key={topic.title}>↗ &nbsp;{topic.title} · {topic.score}%</p>) : <p>No review priorities from this result.</p>}</div>
    </div>
    <div className="assessment-next-action"><strong>Recommended next action</strong><p>{result.recommendedAction ?? 'Review the topics identified above before your next assessment.'}</p><button type="button" className="assessment-primary-button" onClick={onStudy}>Open Study Desk <span>→</span></button></div>
    {result.isDemo && <p className="assessment-results-disclaimer">Demo result from {questions.length} existing sample question. Full scoring and topic analysis require the backend assessment service.</p>}
    <button type="button" className="assessment-secondary-button" onClick={onRestart}>Back to Assessment Center</button>
  </section>
}
