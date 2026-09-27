import { useEffect, useState } from 'react'
import api from '../api'
import './AdminMLReadiness.css'

const readinessGates = [
  { key: 'eligible_snapshots', label: 'Eligible snapshots' },
  { key: 'unique_students', label: 'Unique students' },
  { key: 'unique_target_dates', label: 'Target dates' },
  { key: 'validation_rows', label: 'Validation rows' },
  { key: 'validation_students', label: 'Validation students' },
]

const sourceMetrics = [
  ['total_students', 'Students in school'],
  ['quiz_attempts', 'Quiz attempts'],
  ['students_with_quiz_attempts', 'Students with quiz attempts'],
  ['published_paper_assessments', 'Published paper assessments'],
  ['valid_scored_paper_rows', 'Valid scored paper rows'],
  ['students_with_valid_paper_evidence', 'Students with valid paper evidence'],
  ['distinct_scored_paper_dates', 'Scored paper dates'],
  ['attendance_records', 'Attendance records'],
  ['subjects_with_academic_evidence', 'Subjects with academic evidence'],
  ['classes_with_academic_evidence', 'Classes with academic evidence'],
]

const stateLabels = {
  pipeline_only: 'Pipeline only',
  insufficient_data: 'Insufficient data',
  data_quality_blocked: 'Data quality blocked',
  ready_for_evaluation: 'Ready for evaluation',
  evaluation_ready: 'Evaluation ready',
  evaluated_not_deployed: 'Evaluated, not deployed',
}

async function requestReadiness() {
  const response = await api.get('/admin/ml/training-readiness')
  return response.data
}

function AdminMLReadiness() {
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    requestReadiness()
      .then((result) => {
        if (active) setReport(result)
      })
      .catch(() => {
        if (active) setError('Unable to load ML readiness information.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => { active = false }
  }, [])

  const refresh = async () => {
    setRefreshing(true)
    setError('')
    try {
      setReport(await requestReadiness())
    } catch {
      setError('Unable to load ML readiness information.')
    } finally {
      setRefreshing(false)
    }
  }

  const readiness = report?.readiness || {}
  const progress = report?.progress || {}
  const evidence = report?.source_evidence || {}
  const stateLabel = stateLabels[readiness.state] || 'Readiness unavailable'

  return (
    <div className="ml-readiness-page">
      <header className="mlr-header">
        <div>
          <p className="mlr-kicker">ADMINISTRATION / MACHINE LEARNING</p>
          <h1>ML Training Readiness</h1>
          <p>Aggregate evidence and Phase 7 readiness gates</p>
        </div>
        <button
          type="button"
          className="mlr-refresh"
          onClick={refresh}
          disabled={loading || refreshing}
        >
          {refreshing ? 'Refreshing...' : 'Refresh'}
        </button>
      </header>

      {error && report && <p className="mlr-error" role="alert">{error}</p>}
      {loading ? (
        <p className="mlr-message" role="status">Loading readiness information...</p>
      ) : report ? (
        <>
          <section className="mlr-state-section" aria-labelledby="mlr-state-title">
            <div className="mlr-state-copy">
              <span className="mlr-state-label">CURRENT STATE</span>
              <h2 id="mlr-state-title">{stateLabel}</h2>
              <p>{readiness.state_explanation}</p>
            </div>
            <dl className="mlr-readiness-flags">
              <div>
                <dt>Training ready</dt>
                <dd>{readiness.training_ready ? 'Yes' : 'No'}</dd>
              </div>
              <div>
                <dt>Evaluation ready</dt>
                <dd>{readiness.evaluation_ready ? 'Yes' : 'No'}</dd>
              </div>
              <div>
                <dt>Deployment ready</dt>
                <dd>{readiness.deployment_ready ? 'Yes' : 'No'}</dd>
              </div>
            </dl>
          </section>

          <section className="mlr-section" aria-labelledby="mlr-gates-title">
            <div className="mlr-section-heading">
              <div>
                <h2 id="mlr-gates-title">Readiness gates</h2>
                <p>Each threshold is assessed independently.</p>
              </div>
            </div>
            <div className="mlr-gates">
              {readinessGates.map((gate) => {
                const value = progress[gate.key] || {}
                const unavailable = !value.available
                return (
                  <div className="mlr-gate-row" key={gate.key}>
                    <div className="mlr-gate-name">{gate.label}</div>
                    <div className="mlr-gate-count">
                      {value.current === null || value.current === undefined
                        ? '—'
                        : Number(value.current).toLocaleString()}
                      <span> / {Number(value.required || 0).toLocaleString()}</span>
                    </div>
                    <div className={`mlr-gate-status ${value.met ? 'is-met' : ''}`}>
                      {unavailable ? 'Not measurable yet' : value.met ? 'Met' : 'Not yet met'}
                    </div>
                  </div>
                )
              })}
            </div>
            {!progress.validation_rows?.available && (
              <p className="mlr-note">
                Validation coverage becomes measurable once enough historical target dates exist for a temporal holdout.
              </p>
            )}
          </section>

          <section className="mlr-section" aria-labelledby="mlr-evidence-title">
            <div className="mlr-section-heading">
              <div>
                <h2 id="mlr-evidence-title">Source evidence</h2>
                <p>Operational records are not the same as eligible training snapshots.</p>
              </div>
            </div>
            <dl className="mlr-evidence-grid">
              {sourceMetrics.map(([key, label]) => (
                <div className="mlr-evidence-item" key={key}>
                  <dt>{label}</dt>
                  <dd>{Number(evidence[key] || 0).toLocaleString()}</dd>
                </div>
              ))}
            </dl>
            <p className="mlr-note">
              Quiz attempts, paper scores, and attendance are source evidence. They do not count as eligible snapshots unless a valid scored target paper has earlier matching academic evidence.
            </p>
          </section>

          <section className="mlr-section mlr-explainer" aria-labelledby="mlr-how-title">
            <h2 id="mlr-how-title">How training data becomes eligible</h2>
            <p>
              A historical snapshot requires a valid scored paper assessment plus earlier quiz or paper evidence for the same student, class, and subject. Evidence needs to accumulate across students and assessment dates; attendance alone is not sufficient.
            </p>
            <ul>
              {(report.guidance || []).map((item) => <li key={item}>{item}</li>)}
            </ul>
          </section>

          <section className="mlr-section mlr-blockers" aria-labelledby="mlr-blockers-title">
            <h2 id="mlr-blockers-title">Blockers and warnings</h2>
            {readiness.blocker_messages?.length ? (
              <ul>{readiness.blocker_messages.map((message) => <li key={message}>{message}</li>)}</ul>
            ) : <p>No current blockers are reported.</p>}
            {readiness.warnings?.length > 0 && (
              <ul>{readiness.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
            )}
          </section>
        </>
      ) : (
        <div className="mlr-error" role="alert">Unable to load ML readiness information.</div>
      )}
    </div>
  )
}

export default AdminMLReadiness