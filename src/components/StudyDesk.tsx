import { useMemo, useState } from 'react'
import { getDemoTutorFallback, getStudyWorkspace } from '../services/studyData'
import { askTutor, resolveCourseId } from '../services/studyApi'
import { ApiHttpError, ApiUnavailableError } from '../services/apiClient'
import type { ChatMessage, SourceLocation, StudyMaterial } from '../types/study'
import './StudyDesk.css'
type Page = 'Dashboard' | 'My Courses' | 'Upload Materials' | 'AI Tutor' | 'Quizzes' | 'Progress'
type DeskTab = 'AI Tutor' | 'Original Notes' | 'AI Notes' | 'Flashcards' | 'AI Quizzes'
const tabs: DeskTab[] = ['AI Tutor', 'Original Notes', 'AI Notes', 'Flashcards', 'AI Quizzes']
function formatLocation(location: SourceLocation): string {
  if (location.kind === 'pdf_page' && location.page !== undefined) return `Page ${location.page}`
  if (location.kind === 'slide' && location.slide !== undefined) return `Slide ${location.slide}`
  if (location.kind === 'video_timestamp' && location.seconds !== undefined) {
    const minutes = Math.floor(location.seconds / 60)
    const seconds = String(location.seconds % 60).padStart(2, '0')
    return `${minutes}:${seconds}`
  }
  return 'Source location unavailable'
}
function materialTypeLabel(material: StudyMaterial): string {
  if (material.type === 'pdf') return 'PDF'
  if (material.type === 'slides') return 'SLIDES'
  if (material.type === 'video') return 'VIDEO'
  return 'DOCUMENT'
}
export default function StudyDesk({
  course,
  courses,
  studentName,
  onCourseChange,
  setPage,
}: {
  course: string
  courses: string[]
  studentName: string
  onCourseChange: (course: string) => void
  setPage: (page: Page) => void
}) {
  const workspace = useMemo(() => getStudyWorkspace(course), [course])
  const [materialId, setMaterialId] = useState(workspace.materials[0]?.id ?? '')
  const [activeTab, setActiveTab] = useState<DeskTab>('AI Tutor')
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [extraCitations, setExtraCitations] = useState(workspace.citations)
  const [chatError, setChatError] = useState('')
  const [sending, setSending] = useState(false)
  const [topicPath] = useState<Array<{ topicId: string; conceptId?: string }>>(
    () => workspace.topics[0] ? [{ topicId: workspace.topics[0].id }] : [],
  )
  const material = workspace.materials.find((item) => item.id === materialId) ?? workspace.materials[0]
  const activePath = topicPath.at(-1)
  const topic = workspace.topics.find((item) => item.id === activePath?.topicId)
  const concept = workspace.concepts.find((item) => item.id === activePath?.conceptId)
  const firstName = studentName.trim().split(/\s+/)[0]
  async function sendQuestion(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const text = question.trim()
    if (!text || sending) return
    const userMessage: ChatMessage = {
      id: `student-${Date.now()}`,
      role: 'student',
      content: text,
      citationIds: [],
      isDemo: false,
    }
    setMessages((current) => [...current, userMessage])
    setQuestion('')
    setChatError('')
    setSending(true)
    try {
      const response = await askTutor({
        courseId: resolveCourseId(course),
        materialId: material?.status !== 'demo' ? material?.sourceId : undefined,
        question: text,
      })
      setMessages((current) => [...current, response.message])
      setExtraCitations((current) => [...current, ...response.citations])
    } catch (error) {
      if (error instanceof ApiUnavailableError) {
        setMessages((current) => [...current, getDemoTutorFallback(text).message])
      } else if (error instanceof ApiHttpError) {
        setChatError(error.message)
      } else {
        setChatError(error instanceof Error ? error.message : 'The tutor request failed.')
      }
    } finally {
      setSending(false)
    }
  }
  const activeCitation = material && workspace.citations.find((citation) => citation.materialId === material.id)
  return (
    <div className="study-desk">
      <header className="desk-heading">
        <div>
          <div className="desk-eyebrow">FIELDNOTE STUDY DESK <span>DEMO MODE</span></div>
          <h1>Study with your materials</h1>
          <p>Keep your reading and questions together in one focused space.</p>
        </div>
        <button type="button" className="desk-upload-link" onClick={() => setPage('Upload Materials')}>＋ Add material</button>
      </header>
      <div className="desk-selectors">
        <label>
          <span>COURSE</span>
          <select value={course} onChange={(event) => onCourseChange(event.target.value)}>
            {courses.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        <label>
          <span>MATERIAL</span>
          <select
            value={material?.id ?? ''}
            disabled={!workspace.materials.length}
            onChange={(event) => {
              setMaterialId(event.target.value)
              setMessages([])
            }}
          >
            {workspace.materials.length
              ? workspace.materials.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)
              : <option value="">No demo material available</option>}
          </select>
        </label>
        <span className="desk-data-state">{material ? 'Example material · not an uploaded file' : 'No materials connected for this course'}</span>
      </div>
      <div className="desk-tabs" role="tablist" aria-label="Study material views">
        {tabs.map((tab) => (
          <button
            type="button"
            role="tab"
            key={tab}
            aria-selected={activeTab === tab}
            className={activeTab === tab ? 'active' : ''}
            onClick={() => setActiveTab(tab)}
          >
            {tab}
          </button>
        ))}
      </div>
      <div className="desk-workspace single-panel">
        {activeTab === 'Original Notes' && (
          <section className="desk-main-panel desk-resource-panel" aria-label="Original notes workspace">
            <div className="desk-panel-header">
              <div>
                <span className="desk-panel-kicker">ORIGINAL NOTES</span>
                <h2>{material?.title ?? 'No material selected'}</h2>
              </div>
              {material && <span className="material-kind">{materialTypeLabel(material)}</span>}
            </div>
            {material ? (
              <>
                <div className="document-toolbar">
                  <span>Example preview · demo content</span>
                  <span>{activeCitation ? formatLocation(activeCitation.location) : 'Source location not available'}</span>
                </div>
                <article className="document-page">
                  <div className="document-page-meta"><span>FIELDNOTE SAMPLE READING</span><span>COURSE MATERIAL</span></div>
                  <h3>{concept?.title ?? topic?.title ?? workspace.course.title}</h3>
                  <p className="document-byline">Illustrative excerpt · not extracted from an uploaded file</p>
                  <div className="document-rule" />
                  <p>Cells need a reliable way to transfer energy between the reactions that release it and the processes that use it. In this example, <mark>ATP is shown as a short-term energy carrier</mark> that helps couple those reactions.</p>
                  <p>As you read, consider: which parts of this explanation describe the original idea, and what evidence in your own course materials supports it?</p>
                  <blockquote>Use the source location above to revisit the relevant page, slide, or moment in a recording.</blockquote>
                  <div className="document-footer"><span>Sample content for interface preview</span><span>{activeCitation ? formatLocation(activeCitation.location) : 'No citation'}</span></div>
                </article>
                {activeCitation && <div className="desk-source-card">
                  <span className="source-label">DEMO SOURCE CITATION</span>
                  <strong>{material.title} · {formatLocation(activeCitation.location)}</strong>
                  <small>{activeCitation.excerpt}</small>
                </div>}
              </>
            ) : (
              <div className="desk-empty-document">
                <span aria-hidden="true">▤</span>
                <h3>No demo document for this course</h3>
                <p>Uploaded materials are not yet listed in the study desk. The upload flow is available, but a source-list API still needs to be connected.</p>
                <button type="button" onClick={() => setPage('Upload Materials')}>Go to upload materials</button>
              </div>
            )}
          </section>
        )}
        {activeTab === 'AI Notes' && (
          <section className="desk-main-panel desk-resource-panel" aria-label="AI notes workspace">
            <div className="desk-panel-header">
              <div>
                <span className="desk-panel-kicker">AI NOTES</span>
                <h2>{concept?.title ?? topic?.title ?? 'Study notes'}</h2>
              </div>
              <span className="material-kind">AI</span>
            </div>
            <div className="desk-note-stack">
              <article className="desk-note-card">
                <h3>Key ideas</h3>
                <ul>
                  <li>ATP stores and transfers energy in short bursts.</li>
                  <li>Cellular respiration releases energy by breaking down glucose.</li>
                  <li>The mitochondria are central to aerobic respiration.</li>
                </ul>
              </article>
              <article className="desk-note-card">
                <h3>Quick explanation</h3>
                <p>{material?.title ?? 'Cellular energy'} helps explain how cells convert chemical energy into usable work. The process is tightly linked to structure, especially membrane-based transport and enzyme activity.</p>
              </article>
              <article className="desk-note-card">
                <h3>Study prompts</h3>
                <ul>
                  <li>How does ATP help connect anabolic and catabolic processes?</li>
                  <li>What evidence shows the role of mitochondria in energy production?</li>
                </ul>
              </article>
            </div>
          </section>
        )}
        {activeTab === 'Flashcards' && (
          <section className="desk-main-panel desk-resource-panel" aria-label="Flashcards workspace">
            <div className="desk-panel-header">
              <div>
                <span className="desk-panel-kicker">FLASHCARDS</span>
                <h2>Quick review</h2>
              </div>
              <span className="material-kind">3 CARDS</span>
            </div>
            <div className="desk-flashcard-grid">
              {[
                { front: 'What is ATP?', back: 'It is a short-term energy carrier used to power cellular work.' },
                { front: 'Where does cellular respiration mainly occur?', back: 'In the mitochondria.' },
                { front: 'What is the main purpose of glycolysis?', back: 'To break glucose into smaller molecules and release some energy.' },
              ].map((card) => (
                <article key={card.front} className="desk-flashcard">
                  <span>FRONT</span>
                  <strong>{card.front}</strong>
                  <small>Tap to reveal answer</small>
                  <p>{card.back}</p>
                </article>
              ))}
            </div>
          </section>
        )}
        {activeTab === 'AI Quizzes' && (
          <section className="desk-main-panel desk-resource-panel" aria-label="AI quizzes workspace">
            <div className="desk-panel-header">
              <div>
                <span className="desk-panel-kicker">AI QUIZZES</span>
                <h2>Check your understanding</h2>
              </div>
              <span className="material-kind">2 Qs</span>
            </div>
            <div className="desk-quiz-list">
              <article className="desk-quiz-card">
                <h3>1. Which molecule acts as the cell’s short-term energy currency?</h3>
                <ul>
                  <li>DNA</li>
                  <li className="correct">ATP</li>
                  <li>Oxygen</li>
                  <li>Water</li>
                </ul>
              </article>
              <article className="desk-quiz-card">
                <h3>2. Cellular respiration most directly produces usable energy by:</h3>
                <ul>
                  <li>Storing light energy in the nucleus</li>
                  <li className="correct">Releasing energy from glucose</li>
                  <li>Creating proteins from amino acids</li>
                  <li>Translating RNA</li>
                </ul>
              </article>
            </div>
          </section>
        )}
        {activeTab === 'AI Tutor' && (
          <section className="desk-main-panel desk-chat-panel" aria-label="AI Tutor workspace">
            <div className="desk-chat-header">
              <div className="desk-companion-mark">✦</div>
              <div>
                <h2>AI Tutor</h2>
                <p>Your personal study companion.</p>
              </div>
            </div>
            <div className="desk-chat-messages" aria-live="polite">
              <div className="desk-chat-date">TODAY</div>
              <div className="desk-message tutor">
                <span className="desk-message-avatar">✦</span>
                <div className="desk-message-body">
                  <p>Hi {firstName}! Ask anything about {material?.title ?? 'this topic'} and I’ll help explain it clearly.</p>
                  {activeCitation && <span className="desk-citation-chip">↗ {formatLocation(activeCitation.location)} · source</span>}
                </div>
              </div>
              <div className="desk-message tutor">
                <span className="desk-message-avatar">✦</span>
                <div className="desk-message-body">
                  <p>Sure! Let’s break it down in simple terms: Cellular respiration is the process by which cells break down glucose to produce energy in the form of ATP.</p>
                  <span className="desk-citation-chip">Key takeaway · ATP fuels cellular work</span>
                </div>
              </div>
              {messages.map((message) => (
                <div className={`desk-message ${message.role}`} key={message.id}>
                  {message.role === 'tutor' && <span className="desk-message-avatar">✦</span>}
                  <div className="desk-message-body">
                    <p>{message.content}</p>
                    {message.role === 'tutor' && message.citationIds.map((citationId) => {
                      const citation = extraCitations.find((item) => item.id === citationId)
                      const citedMaterial = citation && workspace.materials.find((item) => item.id === citation.materialId)
                      return citation && citedMaterial
                        ? <span className="desk-citation-chip" key={citation.id}>↗ {citedMaterial.title} · {formatLocation(citation.location)}</span>
                        : null
                    })}
                  </div>
                </div>
              ))}
              {messages.length === 0 && (
                <div className="desk-message student">
                  <div className="desk-message-body">
                    <p>Can you explain cellular respiration in simple terms?</p>
                  </div>
                </div>
              )}
            </div>
            <div className="desk-suggestions">
              {['Explain this simply', 'Give me key takeaways', 'Quiz me on this', 'What should I study next?'].map((prompt) => (
                <button type="button" key={prompt} onClick={() => setQuestion(prompt)}>{prompt}</button>
              ))}
            </div>
            {chatError && <div className="desk-api-error" role="alert">{chatError}</div>}
            <form className="desk-composer" onSubmit={sendQuestion}>
              <label className="visually-hidden" htmlFor="study-desk-question">Ask a question about your materials</label>
              <textarea
                id="study-desk-question"
                rows={3}
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="Ask a question about this topic..."
              />
              <div className="desk-composer-row">
                <span>{sending ? 'Thinking…' : 'Keep it focused and specific.'}</span>
                <button type="submit" disabled={!question.trim() || sending}>{sending ? 'Sending…' : 'Send'}</button>
              </div>
            </form>
          </section>
        )}
      </div>
    </div>
  )
}
