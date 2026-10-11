import { useState, type ReactNode } from 'react'
import './ProgressPage.css'

type Page = 'Dashboard' | 'My Courses' | 'Upload Materials' | 'AI Tutor' | 'Quizzes' | 'Progress'
type Concept = { name: string; score: number; state: 'mastered' | 'developing' | 'review'; x: number; y: number }

const concepts: Concept[] = [
  { name: 'Cell structure', score: 92, state: 'mastered', x: 48, y: 13 },
  { name: 'Genetics', score: 78, state: 'mastered', x: 22, y: 28 },
  { name: 'Photosynthesis', score: 85, state: 'mastered', x: 77, y: 27 },
  { name: 'Cell communication', score: 31, state: 'review', x: 12, y: 57 },
  { name: 'Membranes & transport', score: 78, state: 'mastered', x: 82, y: 55 },
  { name: 'Cellular respiration', score: 54, state: 'developing', x: 30, y: 83 },
  { name: 'Cellular energy', score: 61, state: 'developing', x: 67, y: 83 },
]

const subjects = [
  { name: 'Biology', score: 68, color: 'green', mark: '✿' },
  { name: 'Mathematics', score: 54, color: 'sage', mark: '∑' },
  { name: 'Physics', score: 47, color: 'gold', mark: '◉' },
  { name: 'Computer Science', score: 32, color: 'coral', mark: '⌘' },
]

export default function ProgressPage({ setPage }: { setPage: (page: Page) => void }) {
  const [selectedConcept, setSelectedConcept] = useState('Cell communication')

  return (
    <main className="learning-intelligence">
      <header className="intelligence-heading">
        <div>
          <div className="intelligence-eyebrow">LEARNING INTELLIGENCE <span>DEMO DATA</span></div>
          <h1>Understand how you’re learning,</h1>
          <p>not just how much you’ve studied.</p>
        </div>
        <div className="intelligence-quote"><span>✳</span><span>“Small steps every day<br />lead to big progress.”</span></div>
      </header>

      <section className="intelligence-metrics" aria-label="Learning health overview">
        <article className="intelligence-card health-card">
          <div className="intelligence-card-label"><span className="metric-icon">✿</span>Overall Learning Health</div>
          <div className="health-content"><div className="health-ring"><span>72<small>%</small></span></div><div><strong>On track</strong><span className="metric-change">↑ 12%</span><small>vs. last month</small></div></div>
        </article>
        <MetricCard icon="◎" title="Mastery" value="68%" note="Across all topics" change="↑ 14%" />
        <MetricCard icon="◌" title="Recall Readiness" value="62%" note="Can recall key concepts" change="↑ 9%" />
        <article className="intelligence-card mini-metric"><div className="intelligence-card-label"><span className="metric-icon">▦</span>Study Consistency</div><strong>4/7</strong><p>days this week</p><div className="week-dots" aria-label="Studied 4 of 7 days"><i/><i/><i/><i/><i/><i/><i/></div></article>
        <article className="intelligence-card mini-metric"><div className="intelligence-card-label"><span className="metric-icon">↗</span>Concepts Strengthened</div><strong>+5</strong><p>this week</p><div className="week-dots wins-dots" aria-label="Five concepts strengthened"><i/><i/><i/><i/><i/></div></article>
      </section>

      <section className="intelligence-main-grid">
        <article className="intelligence-card concept-map-card">
          <CardHeading eyebrow="YOUR UNDERSTANDING ACROSS KEY CONCEPTS" title="Concept Mastery Map"><span className="mastery-legend"><i className="mastered-dot"/>Mastered <i className="developing-dot"/>Developing <i className="review-dot"/>Needs review</span></CardHeading>
          <div className="concept-map" aria-label="Concept mastery map">
            <svg className="concept-connectors" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
              {concepts.map((item) => <line key={item.name} x1="50" y1="51" x2={item.x} y2={item.y} />)}
            </svg>
            <div className="map-center"><strong>Foundations<br />of Biology</strong><small>7 concepts</small></div>
            {concepts.map((item) => <button type="button" key={item.name} className={`concept-node ${item.state}${selectedConcept === item.name ? ' chosen' : ''}`} style={{ left: `${item.x}%`, top: `${item.y}%` }} onClick={() => setSelectedConcept(item.name)} aria-pressed={selectedConcept === item.name}>
              <strong>{item.name}</strong><span>{item.score}%</span>
            </button>)}
          </div>
          <div className="map-selection"><span><i className={`mastery-dot ${concepts.find((item) => item.name === selectedConcept)?.state}`} />Selected concept</span><strong>{selectedConcept}</strong><span>{concepts.find((item) => item.name === selectedConcept)?.score}% mastery · demo data</span></div>
          <button type="button" className="map-link" onClick={() => setPage('AI Tutor')}>Explore concepts in Study Desk <span>→</span></button>
        </article>

        <div className="intelligence-middle-column">
          <article className="intelligence-card recommendation-card">
            <div className="recommendation-title"><span className="recommendation-mark">✳</span><div><span>BASED ON YOUR RECENT PRACTICE</span><h2>What should I study next?</h2></div></div>
            <div className="recommendation-concept"><span className="focus-icon">↗</span><div><strong>Cell Communication</strong><small>31% mastery · <b>High priority</b></small></div><span className="recommendation-arrow">›</span></div>
            <p>You struggled with receptor signaling questions. A focused review can strengthen this foundation.</p>
            <button type="button" className="review-cta" onClick={() => setPage('AI Tutor')}>Start a review <span>→</span></button>
            <span className="recommendation-footnote">Demo recommendation · based on sample activity</span>
          </article>
          <GrowthCard />
        </div>

        <article className="intelligence-card quadrant-card">
          <CardHeading eyebrow="HOW ACCURACY RELATES TO CONFIDENCE" title="Confidence vs Performance" />
          <div className="quadrant-plot">
            <span className="axis-label y-axis">Confidence</span><span className="axis-label x-axis">Performance</span>
            <span className="plot-scale scale-high">High</span><span className="plot-scale scale-low">Low</span>
            <span className="quadrant-label overconfident">Overconfident<small>needs practice</small></span><span className="quadrant-label strong">Strong<small>keep it up</small></span>
            <span className="quadrant-label attention">Needs attention<small>focus here</small></span><span className="quadrant-label hidden-strength">Hidden strengths<small>great potential</small></span>
            <QuadrantPoint name="Cell Communication" x={12} y={27} state="review" />
            <QuadrantPoint name="Photosynthesis" x={81} y={27} state="mastered" />
            <QuadrantPoint name="Membranes" x={82} y={43} state="mastered" />
            <QuadrantPoint name="Genetics" x={78} y={56} state="developing" />
            <QuadrantPoint name="Cellular Energy" x={48} y={67} state="developing" />
            <QuadrantPoint name="Cell Structure" x={83} y={83} state="mastered" />
          </div>
          <div className="quadrant-caption">Demo analysis · confidence and quiz accuracy</div>
        </article>
      </section>

      <section className="intelligence-lower-grid">
        <article className="intelligence-card lower-card review-queue-card">
          <CardHeading eyebrow="A LITTLE REVIEW GOES A LONG WAY" title="Review Queue"><button type="button" onClick={() => setPage('AI Tutor')}>View all <span>→</span></button></CardHeading>
          <div className="queue-head"><span>CONCEPT</span><span>MASTERY</span><span>EST. TIME</span><span /></div>
          {[
            ['Cell Communication', '31%', '12 min', 'review'],
            ['Cellular Respiration', '54%', '10 min', 'developing'],
            ['Membranes & Transport', '78%', '8 min', 'developing'],
            ['ATP & Energy Transfer', '61%', '7 min', 'developing'],
          ].map(([name, score, time, state]) => <button type="button" className="queue-row" key={name} onClick={() => { setSelectedConcept(name === 'ATP & Energy Transfer' ? 'Cellular energy' : name); setPage('AI Tutor') }}>
            <span><i className={`mastery-dot ${state}`} />{name}</span><strong className={state}>{score}</strong><small>{time}</small><b>›</b>
          </button>)}
        </article>
        <article className="intelligence-card lower-card recent-wins-card">
          <CardHeading eyebrow="PROGRESS WORTH NOTICING" title="Recent Wins"><button type="button" onClick={() => setPage('AI Tutor')}>View all <span>→</span></button></CardHeading>
          {[
            ['Photosynthesis', 'Mastery increased from 67% → 85%', '2 days ago'],
            ['Genetics', 'Mastery increased from 66% → 78%', '3 days ago'],
            ['Cell Structure', 'Mastery increased from 83% → 92%', '4 days ago'],
          ].map(([name, detail, when]) => <div className="win-row" key={name}><span className="win-icon">↗</span><div><strong>{name}</strong><small>{detail}</small></div><time>{when}</time></div>)}
        </article>
        <article className="intelligence-card lower-card subjects-card">
          <CardHeading eyebrow="MASTERY BY SUBJECT" title="All Subjects"><button type="button">View all <span>→</span></button></CardHeading>
          {subjects.map((subject) => <div className="subject-row" key={subject.name}><span className={`subject-icon ${subject.color}`}>{subject.mark}</span><strong>{subject.name}</strong><span className="subject-bar"><i className={subject.color} style={{ width: `${subject.score}%` }} /></span><b>{subject.score}%</b></div>)}
        </article>
      </section>
    </main>
  )
}

function MetricCard({ icon, title, value, note, change }: { icon: string; title: string; value: string; note: string; change: string }) {
  return <article className="intelligence-card mini-metric"><div className="intelligence-card-label"><span className="metric-icon">{icon}</span>{title}</div><strong>{value}</strong><p>{note}</p><small className="metric-change">{change} <span>vs. last week</span></small></article>
}

function CardHeading({ eyebrow, title, children }: { eyebrow: string; title: string; children?: ReactNode }) {
  return <div className="intelligence-card-heading"><div><h2>{title}</h2><p>{eyebrow}</p></div>{children}</div>
}

function QuadrantPoint({ name, x, y, state }: { name: string; x: number; y: number; state: string }) {
  return <span className={`quadrant-point ${state}`} style={{ left: `${x}%`, top: `${y}%` }}><i />{name}</span>
}

function GrowthCard() {
  return <article className="intelligence-card growth-card">
    <CardHeading eyebrow="MASTERY AND ACCURACY OVER TIME" title="Learning Growth"><span className="growth-legend"><i />Mastery <i />Accuracy</span></CardHeading>
    <div className="growth-chart">
      <div className="growth-y-labels"><span>100%</span><span>75%</span><span>50%</span><span>25%</span><span>0%</span></div>
      <svg viewBox="0 0 300 116" preserveAspectRatio="none" role="img" aria-label="Demo chart: mastery improves from 22 to 68 percent and accuracy from 15 to 54 percent across four weeks">
        <path className="chart-area" d="M0 91 L35 78 L72 70 L108 58 L145 53 L180 47 L217 39 L253 32 L300 18 L300 116 L0 116Z" />
        <path className="chart-line mastery-line" d="M0 91 L35 78 L72 70 L108 58 L145 53 L180 47 L217 39 L253 32 L300 18" />
        <path className="chart-line accuracy-line" d="M0 101 L35 92 L72 84 L108 77 L145 68 L180 64 L217 59 L253 53 L300 43" />
        {[['0','91'],['35','78'],['72','70'],['108','58'],['145','53'],['180','47'],['217','39'],['253','32'],['300','18']].map(([x,y]) => <circle key={`${x}-${y}`} cx={x} cy={y} r="2.2" className="mastery-point" />)}
        {[['0','101'],['35','92'],['72','84'],['108','77'],['145','68'],['180','64'],['217','59'],['253','53'],['300','43']].map(([x,y]) => <circle key={`a-${x}-${y}`} cx={x} cy={y} r="2.2" className="accuracy-point" />)}
      </svg>
      <div className="growth-weeks"><span>Week 1</span><span>Week 2</span><span>Week 3</span><span>Week 4</span></div>
    </div>
    <div className="growth-bottom"><span><i className="mastery-key" />Mastery</span><span><i className="accuracy-key" />Accuracy</span><small>Demo data · last 4 weeks</small></div>
  </article>
}
