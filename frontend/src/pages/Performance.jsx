import { useEffect, useState } from 'react'
import api from '../api'
import './Performance.css'

function Performance() {
  const [prediction, setPrediction] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)

  // Form state
  const [form, setForm] = useState({
    attendance: '',
    assignment_score: '',
    quiz_score: '',
    study_hours: '',
  })

  const loadPrediction = () => {
    setLoading(true)
    api
      .get('/student/prediction')
      .then((response) => {
        setPrediction(response.data.prediction)
      })
      .catch((error) => {
        console.error(error)
        setError(`API error: ${error.response?.status || error.message}`)
      })
      .finally(() => {
        setLoading(false)
      })
  }

  useEffect(() => {
    loadPrediction()
  }, [])

  const handleChange = (e) => {
    setForm({
      ...form,
      [e.target.name]: e.target.value,
    })
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)

    try {
      const response = await api.post('/student/prediction', {
        attendance: Number(form.attendance),
        assignment_score: Number(form.assignment_score),
        quiz_score: Number(form.quiz_score),
        study_hours: Number(form.study_hours),
      })

      // Update the displayed prediction
      setPrediction({
        prediction: response.data.prediction.result,
        attendance: response.data.prediction.attendance,
        assignment_score: response.data.prediction.assignment_score,
        quiz_score: response.data.prediction.quiz_score,
        study_hours: response.data.prediction.study_hours,
      })

      // Clear form
      setForm({
        attendance: '',
        assignment_score: '',
        quiz_score: '',
        study_hours: '',
      })
    } catch (err) {
      console.error(err)
      setError(
        err.response?.data?.error || 'Failed to generate prediction'
      )
    } finally {
      setSubmitting(false)
    }
  }

  const getPredictionClass = (value) => {
    if (!value) return 'prediction-default'
    const text = value.toLowerCase()
    if (text.includes('excellent')) return 'prediction-excellent'
    if (text.includes('good')) return 'prediction-good'
    if (text.includes('average')) return 'prediction-average'
    return 'prediction-warning'
  }

  return (
    <div className="performance-page">
      <section className="performance-hero">
        <div>
          <p className="performance-label">ACADEMIC ANALYSIS</p>
          <h1>My Performance</h1>
          <p>
            Understand your current academic performance and identify areas
            where you can improve.
          </p>
        </div>
        <div className="performance-hero-icon">📊</div>
      </section>

      {/* Generate New Prediction Form */}
      <section className="prediction-card" style={{ marginBottom: 30 }}>
        <h2 style={{ marginBottom: 16 }}>Generate New Prediction</h2>

        <form onSubmit={handleSubmit} style={{ display: 'grid', gap: 14, maxWidth: 500 }}>
          <div>
            <label>Attendance (%)</label>
            <input
              type="number"
              name="attendance"
              value={form.attendance}
              onChange={handleChange}
              min="0"
              max="100"
              required
              placeholder="e.g. 85"
              style={{ width: '100%', padding: 10, marginTop: 4 }}
            />
          </div>

          <div>
            <label>Assignment Score</label>
            <input
              type="number"
              name="assignment_score"
              value={form.assignment_score}
              onChange={handleChange}
              min="0"
              max="100"
              required
              placeholder="e.g. 78"
              style={{ width: '100%', padding: 10, marginTop: 4 }}
            />
          </div>

          <div>
            <label>Quiz Score</label>
            <input
              type="number"
              name="quiz_score"
              value={form.quiz_score}
              onChange={handleChange}
              min="0"
              max="100"
              required
              placeholder="e.g. 80"
              style={{ width: '100%', padding: 10, marginTop: 4 }}
            />
          </div>

          <div>
            <label>Study Hours (per day)</label>
            <input
              type="number"
              name="study_hours"
              value={form.study_hours}
              onChange={handleChange}
              min="0"
              step="0.5"
              required
              placeholder="e.g. 3.5"
              style={{ width: '100%', padding: 10, marginTop: 4 }}
            />
          </div>

          {error && <div style={{ color: 'red' }}>⚠️ {error}</div>}

          <button
            type="submit"
            disabled={submitting}
            style={{
              padding: '12px 20px',
              background: '#2563eb',
              color: 'white',
              border: 'none',
              borderRadius: 8,
              fontWeight: 600,
              cursor: 'pointer',
              marginTop: 8,
            }}
          >
            {submitting ? 'Generating...' : 'Generate Prediction'}
          </button>
        </form>
      </section>

      {loading && (
        <div className="performance-state">
          <div className="performance-spinner" />
          <p>Analyzing your performance...</p>
        </div>
      )}

      {!loading && !prediction && (
        <div className="performance-state">
          <div className="empty-performance-icon">📈</div>
          <h2>No prediction available</h2>
          <p>Fill the form above to generate your first prediction.</p>
        </div>
      )}

      {!loading && prediction && (
        <>
          <section className="prediction-card">
            <div className="prediction-heading">
              <div>
                <p className="small-label">LATEST PREDICTION</p>
                <h2>Your Academic Outlook</h2>
              </div>
              <div className={`prediction-badge ${getPredictionClass(prediction.prediction)}`}>
                {prediction.prediction}
              </div>
            </div>

            <div className="prediction-message">
              <span className="prediction-message-icon">🎯</span>
              <div>
                <strong>Performance Prediction</strong>
                <p>
                  This prediction is based on your current academic activity
                  and learning data.
                </p>
              </div>
            </div>
          </section>

          <section className="metrics-section">
            <div className="section-title">
              <h2>Performance Metrics</h2>
              <p>Your current learning indicators</p>
            </div>

            <div className="metrics-grid">
              <div className="metric-card">
                <div className="metric-icon">📅</div>
                <div>
                  <span>Attendance</span>
                  <strong>{prediction.attendance}%</strong>
                </div>
              </div>

              <div className="metric-card">
                <div className="metric-icon">📝</div>
                <div>
                  <span>Assignment Score</span>
                  <strong>{prediction.assignment_score}</strong>
                </div>
              </div>

              <div className="metric-card">
                <div className="metric-icon">🧠</div>
                <div>
                  <span>Quiz Score</span>
                  <strong>{prediction.quiz_score}</strong>
                </div>
              </div>

              <div className="metric-card">
                <div className="metric-icon">⏱️</div>
                <div>
                  <span>Study Hours</span>
                  <strong>{prediction.study_hours}</strong>
                </div>
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  )
}

export default Performance