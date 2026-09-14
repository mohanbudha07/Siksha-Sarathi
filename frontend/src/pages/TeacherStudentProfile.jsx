import { useEffect, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import api from '../api'
import './TeacherLearningAnalytics.css'

const statusClass = (status) =>
  `tla-status tla-status-${String(status || 'no-activity')
    .toLowerCase()
    .replaceAll(' ', '-')}`

function MetricBar({ value }) {
  const safeValue = Math.min(100, Math.max(0, Number(value) || 0))
  return (
    <div className="tla-progress" aria-label={`${safeValue}%`}>
      <span style={{ width: `${safeValue}%` }} />
    </div>
  )
}

function TeacherStudentProfile() {
  const navigate = useNavigate()
  const { studentId } = useParams()
  const [searchParams] = useSearchParams()
  const subject = searchParams.get('subject') || ''
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const loadProfile = async () => {
      if (!subject) {
        setError('A subject is required to open this learning profile.')
        setLoading(false)
        return
      }

      try {
        setLoading(true)
        setError('')
        const response = await api.get(
          `/teacher/students/${studentId}/learning-profile`,
          { params: { subject } }
        )
        setData(response.data)
      } catch (err) {
        console.error('Teacher student profile error:', err)
        setError(
          err.response?.data?.error || 'Unable to load this learning profile.'
        )
      } finally {
        setLoading(false)
      }
    }

    loadProfile()
  }, [studentId, subject])

  if (loading) {
    return (
      <div className="tla-page">
        <div className="tla-state">
          <div className="tla-spinner" />
          <p>Analysing student learning activity...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="tla-page">
        <div className="tla-state tla-error">
          <h2>Profile unavailable</h2>
          <p>{error}</p>
          <button onClick={() => navigate('/teacher/analytics')}>
            Back to analytics
          </button>
        </div>
      </div>
    )
  }

  const student = data?.student || {}
  const summary = data?.summary || {}
  const topics = data?.topics || []
  const difficulties = data?.difficulties || []
  const attempts = data?.recent_attempts || []
  const mistakes = data?.common_mistakes || []

  return (
    <div className="tla-page tla-profile-page">
      <button className="tla-back" onClick={() => navigate('/teacher/analytics')}>
        ← Back to learning analytics
      </button>

      <section className="tla-profile-hero">
        <div className="tla-profile-identity">
          <span>{student.full_name?.charAt(0).toUpperCase()}</span>
          <div>
            <p className="tla-eyebrow">STUDENT LEARNING PROFILE</p>
            <h1>{student.full_name}</h1>
            <p>
              {student.class_name} · {student.section} · {student.subject}
            </p>
          </div>
        </div>
        <span className={statusClass(summary.status)}>{summary.status}</span>
      </section>

      <section className="tla-stat-grid tla-profile-stats">
        <article>
          <span>Accuracy</span>
          <strong>{summary.accuracy_percent}%</strong>
          <small>{summary.correct_answers}/{summary.total_questions} correct answers</small>
        </article>
        <article>
          <span>Quiz attempts</span>
          <strong>{summary.attempts}</strong>
          <small>Recorded for {student.subject}</small>
        </article>
        <article>
          <span>Skipped answers</span>
          <strong>{summary.skipped_answers}</strong>
          <small>{summary.skip_percent}% of tracked questions</small>
        </article>
        <article>
          <span>Questions tracked</span>
          <strong>{summary.total_questions}</strong>
          <small>Used in this diagnosis</small>
        </article>
      </section>

      <div className="tla-profile-grid">
        <section className="tla-panel">
          <div className="tla-section-heading">
            <div>
              <h2>Topic diagnosis</h2>
              <p>Lowest accuracy topics appear first.</p>
            </div>
          </div>
          {topics.length === 0 ? (
            <p className="tla-muted">No topic activity has been recorded yet.</p>
          ) : (
            <div className="tla-metric-list">
              {topics.map((topic) => (
                <article key={topic.topic}>
                  <div className="tla-metric-title">
                    <strong>{topic.topic}</strong>
                    <span>{topic.accuracy_percent}%</span>
                  </div>
                  <MetricBar value={topic.accuracy_percent} />
                  <small>
                    {topic.correct_answers}/{topic.total_questions} correct ·{' '}
                    {topic.skipped_answers} skipped
                  </small>
                </article>
              ))}
            </div>
          )}
        </section>

        <section className="tla-panel">
          <div className="tla-section-heading">
            <div>
              <h2>Difficulty performance</h2>
              <p>Compare results across question difficulty.</p>
            </div>
          </div>
          {difficulties.length === 0 ? (
            <p className="tla-muted">No difficulty data has been recorded yet.</p>
          ) : (
            <div className="tla-metric-list">
              {difficulties.map((item) => (
                <article key={item.difficulty}>
                  <div className="tla-metric-title">
                    <strong className="tla-capitalize">{item.difficulty}</strong>
                    <span>{item.accuracy_percent}%</span>
                  </div>
                  <MetricBar value={item.accuracy_percent} />
                  <small>
                    {item.total_questions} questions · {item.skip_percent}% skipped
                  </small>
                </article>
              ))}
            </div>
          )}
        </section>
      </div>

      <section className="tla-panel">
        <div className="tla-section-heading">
          <div>
            <h2>Recent attempt trend</h2>
            <p>Latest ten {student.subject} attempts, newest first.</p>
          </div>
        </div>
        {attempts.length === 0 ? (
          <p className="tla-muted">No attempts have been recorded for this subject.</p>
        ) : (
          <div className="tla-attempt-list">
            {attempts.map((attempt) => (
              <article key={attempt.attempt_id}>
                <div>
                  <strong>{attempt.quiz_title}</strong>
                  <small>
                    Attempt #{attempt.attempt_id} · {attempt.skipped_answers} skipped
                  </small>
                </div>
                <div className="tla-attempt-score">
                  <strong>{attempt.percentage}%</strong>
                  <span>{attempt.score}/{attempt.total_questions}</span>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="tla-panel">
        <div className="tla-section-heading">
          <div>
            <h2>Common mistakes</h2>
            <p>Repeated incorrect responses that may need teacher intervention.</p>
          </div>
        </div>
        {mistakes.length === 0 ? (
          <p className="tla-muted">No incorrect answered questions were found.</p>
        ) : (
          <div className="tla-mistake-list">
            {mistakes.map((mistake, index) => (
              <article key={`${mistake.question_text}-${index}`}>
                <div className="tla-mistake-count">{mistake.mistake_count}×</div>
                <div>
                  <div className="tla-mistake-tags">
                    <span>{mistake.topic}</span>
                    <span className="tla-capitalize">{mistake.difficulty}</span>
                  </div>
                  <h3>{mistake.question_text}</h3>
                  <p>Correct answer: <strong>{mistake.correct_answer}</strong></p>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

export default TeacherStudentProfile
