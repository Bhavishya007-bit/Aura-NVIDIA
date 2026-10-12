import { useEffect, useState } from "react";

import PalettePreview from "./PalettePreview";

import { useCurrentLocalDate } from "../hooks/useCurrentLocalDate";

import {

  getLearningInsights,

  listCourses,

} from "../services/studyApi";

import type {

  Course,

  LearningInsights,

} from "../types/study";

import "./FieldnoteDashboard.css";

type Page =

  | "Dashboard"

  | "My Courses"

  | "Upload Materials"

  | "AI Tutor"

  | "Quizzes"

  | "Progress";

type Palette = "current";

type Props = {

  course: string;

  studentName: string;

  palettePreview: Palette;

  setPalettePreview: (palette: Palette) => void;

  setPage: (page: Page) => void;

};

export default function FieldnoteDashboard({

  course,

  studentName,

  palettePreview,

  setPalettePreview,

  setPage,

}: Props) {

  const today = useCurrentLocalDate();

  const firstName = studentName.trim().split(/\s+/)[0];

  const [insights, setInsights] =

    useState<LearningInsights | null>(null);

  const [loading, setLoading] = useState(true);

  const [error, setError] = useState("");

  const [courses, setCourses] = useState<Course[]>([]);

  const [coursesLoading, setCoursesLoading] = useState(true);

  const [coursesError, setCoursesError] = useState("");

  // Match the selected course name to the real backend course ID.
  const selectedCourseId = courses.find((item) => item.title === course)?.id;

  // Load real courses from the FastAPI backend.

  useEffect(() => {

    let cancelled = false;

    async function loadCourses() {

      setCoursesLoading(true);

      setCoursesError("");

      try {

        const result = await listCourses();

        if (!cancelled) {

          setCourses(result);

        }

      } catch (err) {

        if (!cancelled) {

          setCoursesError(

            err instanceof Error

              ? err.message

              : "Unable to load courses.",

          );

          setCourses([]);

        }

      } finally {

        if (!cancelled) {

          setCoursesLoading(false);

        }

      }

    }

    void loadCourses();

    return () => {

      cancelled = true;

    };

  }, []);

  // Load mastery only after courses are loaded and the selected course ID is known.
  useEffect(() => {
    let cancelled = false;

    async function loadInsights() {
      if (coursesLoading) {
        return;
      }

      setLoading(true);
      setError("");

      if (!selectedCourseId) {
        setInsights(null);
        setError(
          coursesError ||
            `Could not find the selected course "${course}" in the Aura API.`,
        );
        setLoading(false);
        return;
      }

      try {
        // The mastery endpoint currently uses verified student ID 1.
        // Pass the numeric backend course ID, not the course name.
        const result = await getLearningInsights(selectedCourseId);

        if (!cancelled) {
          setInsights(result);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Unable to load learning progress.",
          );
          setInsights(null);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadInsights();

    return () => {
      cancelled = true;
    };
  }, [course, selectedCourseId, coursesLoading, coursesError]);

  const strongestTopic = insights?.topicMastery.reduce<

    (typeof insights.topicMastery)[number] | null

  >((best, current) => {

    if (!best) return current;

    return (current.score ?? 0) > (best.score ?? 0)

      ? current

      : best;

  }, null);

  return (

    <>

      <PalettePreview

        value={palettePreview}

        onChange={setPalettePreview}

      />

      <div className="fieldnote-dashboard">

        <div className="dashboard-primary">

          <section className="dashboard-welcome">

            <div>

              <div className="eyebrow">{today}</div>

              <h1>

                Good morning, {firstName}{" "}

                <span className="wave">✳</span>

              </h1>

              <p>

                A little progress each day adds up. You’re doing well.

              </p>

            </div>

            <div className="week-pill">

              <span className="pulse" />

              <span>Your week</span>

              <strong>Activity unavailable</strong>

            </div>

          </section>

          <section

            className="fieldnote-feature"

            aria-label="Continue your course"

          >

            <div className="feature-copy">

              <span className="feature-kicker">

                ● &nbsp; YOUR COURSE

              </span>

              <h2>{course}</h2>

              <p>

                Course progress will appear when learning progress

                is connected.

              </p>

              <div className="feature-progress">

                <span style={{ width: "0%" }} />

              </div>

              <div className="feature-meta">

                <span>Progress unavailable</span>

                <span>Study history not connected</span>

              </div>

              <button

                className="feature-button"

                onClick={() => setPage("My Courses")}

              >

                View courses <span>→</span>

              </button>

            </div>

          </section>

          <section className="dashboard-courses">

            <div className="fieldnote-section-heading">

              <h2>Your courses</h2>

              <button onClick={() => setPage("My Courses")}>

                All courses <span>→</span>

              </button>

            </div>

            {coursesLoading && (

              <p role="status">Loading courses from Aura API…</p>

            )}

            {!coursesLoading && coursesError && (

              <p role="alert">

                Could not load courses: {coursesError}

              </p>

            )}

            {!coursesLoading &&

              !coursesError &&

              courses.length === 0 && (

                <p>No courses are available yet.</p>

              )}

            {!coursesLoading && courses.length > 0 && (

              <div className="fieldnote-course-grid">

                {courses.map((item) => (

                  <CourseCard

                    key={item.id}

                    title={item.title}

                    open={() => setPage("My Courses")}

                  />

                ))}

              </div>

            )}

          </section>

          <section className="fieldnote-recent">

            <div className="fieldnote-section-heading">

              <h2>Recently studied</h2>

              <button onClick={() => setPage("Progress")}>

                View all <span>→</span>

              </button>

            </div>

            <p>

              Study history is not connected yet. Your recent

              learning sessions will appear here when available.

            </p>

          </section>

        </div>

        <aside

          className="dashboard-rail"

          aria-label="Learning overview"

        >

          <section className="rail-panel">

            <h2>Real topic mastery</h2>

            {loading && (

              <p role="status">

                Loading mastery from Aura API…

              </p>

            )}

            {!loading && error && (

              <p role="alert">

                Could not load mastery: {error}

              </p>

            )}

            {!loading && !error && strongestTopic && (

              <div>

                <h3>

                  {strongestTopic.topicName ??

                    `Topic ${strongestTopic.topicId}`}

                </h3>

                <div className="rail-stats">

                  <div>

                    <strong>

                      {(strongestTopic.score ?? 0).toFixed(2)}%

                    </strong>

                    <small>Mastery score</small>

                  </div>

                  <div>

                    <strong>{strongestTopic.level}</strong>

                    <small>Mastery level</small>

                  </div>

                </div>

                {strongestTopic.updatedAt && (

                  <small>

                    Updated:{" "}

                    {new Date(

                      strongestTopic.updatedAt,

                    ).toLocaleString()}

                  </small>

                )}

              </div>

            )}

            {!loading && !error && !strongestTopic && (

              <p>No mastery records are available yet.</p>

            )}

          </section>

          <section className="rail-panel activity-summary">

            <h2>

              <span aria-hidden="true">▥</span>{" "}

              Weekly learning activity

            </h2>

            <p>

              Weekly activity data is not connected to the backend

              yet.

            </p>

            <div className="rail-stats">

              <div>

                <strong>—</strong>

                <small>Average study time</small>

              </div>

              <div>

                <strong>—</strong>

                <small>Active study days</small>

              </div>

            </div>

          </section>

          <section className="rail-panel encouragement">

            <span

              className="encouragement-leaf"

              aria-hidden="true"

            >

              ❧

            </span>

            <div>

              <h2>Keep learning!</h2>

              <p>

                Consistency today builds confidence tomorrow.

              </p>

            </div>

          </section>

          <section className="rail-panel quick-actions">

            <h2>Quick actions</h2>

            <button onClick={() => setPage("Upload Materials")}>

              <span>＋</span>

              <span>

                <strong>Add study material</strong>

                <small>Notes, slides or readings</small>

              </span>

            </button>

            <button onClick={() => setPage("Quizzes")}>

              <span>▣</span>

              <span>

                <strong>Take a quiz</strong>

                <small>Test your understanding</small>

              </span>

            </button>

            <button onClick={() => setPage("AI Tutor")}>

              <span>✧</span>

              <span>

                <strong>Ask AI Tutor</strong>

                <small>Study assistance</small>

              </span>

            </button>

          </section>

          <figure className="rail-quote">

            <blockquote>

              “Study not for grades,

              <br />

              but for the life you want

              <br />

              to live.”

            </blockquote>

            <figcaption>— Aura study note</figcaption>

          </figure>

        </aside>

      </div>

    </>

  );

}

function CourseCard({

  title,

  open,

}: {

  title: string;

  open: () => void;

}) {

  return (

    <article className="fieldnote-course-card">

      <div className="fieldnote-card-tags">

        <span>COURSE</span>

        <span aria-hidden="true">❧</span>

      </div>

      <h3>{title}</h3>

      <p>Course progress not available</p>

      <div className="fieldnote-card-progress">

        <span className="fieldnote-progress-track">

          <i style={{ width: "0%" }} />

        </span>

        <small>—</small>

        <button

          onClick={open}

          aria-label={`Open ${title}`}

        >

          →

        </button>

      </div>

    </article>

  );

}
