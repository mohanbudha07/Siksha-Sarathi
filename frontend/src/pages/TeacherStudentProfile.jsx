import { useEffect, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import api from '../api'
import TeacherInterventions from '../components/TeacherInterventions'
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
  const [prediction, setPrediction] = useState(null)
  const [predictionLoading, setPredictionLoading] = useState(true)
  const [predictionError, setPredictionError] = useState(false)
  const [predictionRetry, setPredictionRetry] = useState(0)

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

  useEffect(() => {
    let active = true

    const loadPrediction = async () => {
      if (!subject) {
        setPrediction(null)
        setPredictionError(false)
        setPredictionLoading(false)
        return
      }

      setPredictionLoading(true)
      setPredictionError(false)
      try {
        const response = await api.get(
          `/teacher/students/${studentId}/prediction`,
          { params: { subject } }
        )
        if (active) setPrediction(response.data)
      } catch {
        if (active) {
          setPrediction(null)
          setPredictionError(true)
        }
      } finally {
        if (active) setPredictionLoading(false)
      }
    }

    loadPrediction()
    return () => {
      active = false
    }
  }, [studentId, subject, predictionRetry])

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
  const paper = data?.paper_assessments || {}
  const attendance = data?.attendance || {}
  const paperHistory = data?.recent_paper_assessments || []
  const attendanceHistory = data?.recent_attendance || []
  const actions = data?.teacher_actions || []
  const forecast = prediction?.prediction || {}
  const forecastEvidence = prediction?.evidence || {}
  const predictionPercent = forecast.prediction_percent
  const validPrediction =
    typeof predictionPercent === 'number' &&
    Number.isFinite(predictionPercent) &&
    predictionPercent >= 0 &&
    predictionPercent <= 100
  const academicEvidenceCount =
    forecastEvidence.academic_evidence_count ??
    (Number(forecastEvidence.quiz_attempt_count || 0) +
      Number(forecastEvidence.prior_paper_count || 0))

  const renderForecastEvidence = () => (
    <div className="tla-forecast-evidence">
      <h3>Evidence available</h3>
      <dl>
        <div>
          <dt>Prior scored quizzes</dt>
          <dd>{forecastEvidence.quiz_attempt_count ?? 'Not recorded'}</dd>
        </div>
        <div>
          <dt>Prior paper results</dt>
          <dd>{forecastEvidence.prior_paper_count ?? 'Not recorded'}</dd>
        </div>
        <div>
          <dt>Attendance</dt>
          <dd>
            {forecastEvidence.has_attendance_evidence === undefined
              ? 'Not recorded'
              : forecastEvidence.has_attendance_evidence
                ? 'Available'
                : 'Not available'}
          </dd>
        </div>
      </dl>
      {forecastEvidence.academic_evidence_count !== undefined && (
        <p className="tla-forecast-evidence-total">
          {academicEvidenceCount} scored academic observations before this date
        </p>
      )}
    </div>
  )

  const renderForecastState = () => {
    if (predictionLoading) {
      return <p className="tla-muted" role="status">Checking forecast availability…</p>
    }

    if (predictionError) {
      return (
        <div className="tla-forecast-message" role="status">
          <strong>Forecast service unavailable.</strong>
          <p>Observed learning evidence is still available on this profile.</p>
          <button
            type="button"
            className="tla-forecast-retry"
            onClick={() => setPredictionRetry((retry) => retry + 1)}
          >
            Retry forecast
          </button>
        </div>
      )
    }

    if (forecast.status === 'prediction_available' && validPrediction) {
      return (
        <div className="tla-forecast-available">
          <div>
            <span className="tla-forecast-label">Estimated next paper score</span>
            <strong className="tla-forecast-value">{predictionPercent}%</strong>
            <p>This is a model estimate, not a guaranteed result.</p>
          </div>
          <dl className="tla-forecast-meta">
            <div><dt>Subject</dt><dd>{prediction?.student?.subject || subject}</dd></div>
            <div><dt>As of</dt><dd>{prediction?.as_of_date || 'Not provided'}</dd></div>
            {forecast.model_version && <div><dt>Model version</dt><dd>{forecast.model_version}</dd></div>}
            {forecast.model_type && <div><dt>Model type</dt><dd>{forecast.model_type}</dd></div>}
          </dl>
          {renderForecastEvidence()}
        </div>
      )
    }

    if (forecast.status === 'model_unavailable') {
      return (
        <div className="tla-forecast-message" role="status">
          <strong>ML forecast not available yet.</strong>
          <p>No validated school prediction model is currently deployed.</p>
          <p>Observed quiz, paper and attendance evidence remains available below.</p>
        </div>
      )
    }

    if (forecast.status === 'insufficient_evidence') {
      return (
        <div className="tla-forecast-message" role="status">
          <strong>Not enough academic evidence yet.</strong>
          <p>A forecast requires at least one prior scored quiz or one prior paper assessment. Attendance alone is not enough.</p>
          {forecastEvidence.academic_evidence_count !== undefined && (
            <p>{academicEvidenceCount} scored academic observations are available before this date.</p>
          )}
          {renderForecastEvidence()}
        </div>
      )
    }

    if (forecast.status === 'prediction_invalid' || forecast.status === 'prediction_available') {
      return (
        <div className="tla-forecast-message" role="status">
          <strong>Forecast temporarily unavailable.</strong>
          <p>The prediction output did not pass validation, so Siksha Sarathi is using observed learning evidence instead.</p>
        </div>
      )
    }

    return (
      <div className="tla-forecast-message" role="status">
        <strong>Forecast service unavailable.</strong>
        <p>Observed learning evidence is still available on this profile.</p>
        <button
          type="button"
          className="tla-forecast-retry"
          onClick={() => setPredictionRetry((retry) => retry + 1)}
        >
          Retry forecast
        </button>
      </div>
    )
  }

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
          <span>Paper assessments</span>
          <strong>{paper.graded_assessments ? `${paper.average_percent}%` : '—'}</strong>
          <small>{paper.recorded_assessments || 0} recorded entries</small>
        </article>
        <article>
          <span>Attendance</span>
          <strong>{attendance.recorded_days ? `${attendance.attendance_percent}%` : '—'}</strong>
          <small>{attendance.recorded_days || 0} school days across {attendance.recorded_months || 0} months</small>
        </article>
        <article>
          <span>Skipped answers</span>
          <strong>{summary.skipped_answers}</strong>
          <small>{summary.skip_percent}% of quiz questions</small>
        </article>
      </section>

      <section className="tla-panel tla-forecast-panel" aria-labelledby="tla-forecast-title">
        <div className="tla-section-heading">
          <div>
            <p className="tla-eyebrow tla-forecast-eyebrow">ML FORECAST</p>
            <h2 id="tla-forecast-title">Performance forecast</h2>
            <p>A separate model estimate alongside the observed learning evidence.</p>
          </div>
        </div>
        {renderForecastState()}
      </section>

      <TeacherInterventions
        studentId={studentId}
        subject={subject}
        suggestions={actions}
      />

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

      <div className="tla-profile-grid tla-school-evidence-grid">
        <section className="tla-panel">
          <div className="tla-section-heading"><div><h2>Paper assessment evidence</h2><p>Published teacher-entered marks only.</p></div></div>
          {paperHistory.length === 0 ? <p className="tla-muted">No published paper marks have been recorded.</p> : (
            <div className="tla-evidence-list">
              {paperHistory.map((item) => (
                <article key={item.assessment_id}>
                  <div><strong>{item.title}</strong><small>{item.assessment_date} · {String(item.assessment_type).replaceAll('_', ' ')}</small></div>
                  <span className={item.is_absent ? 'is-absent' : ''}>{item.is_absent ? 'Absent' : `${item.percentage}%`}</span>
                </article>
              ))}
            </div>
          )}
        </section>

        <section className="tla-panel">
          <div className="tla-section-heading"><div><h2>Attendance evidence</h2><p>Monthly totals copied from the paper register, separate from subject scores.</p></div></div>
          <div className="tla-attendance-counts">
            <span><strong>{attendance.recorded_months || 0}</strong>Months</span><span><strong>{attendance.recorded_days || 0}</strong>School days</span><span><strong>{attendance.present_days || 0}</strong>Present</span><span><strong>{attendance.absent_days || 0}</strong>Absent</span>
          </div>
          {attendanceHistory.length > 0 && <div className="tla-attendance-recent">{attendanceHistory.slice(0, 12).map((item) => <span key={item.attendance_summary_id}><strong>{String(item.attendance_month).slice(0, 7)}</strong>{item.present_days}/{item.total_school_days} days</span>)}</div>}
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
