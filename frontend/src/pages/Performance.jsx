import { useEffect, useState } from 'react'
import api from '../api'
import './Performance.css'

function Performance() {
  const [prediction, setPrediction] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .get('/student/prediction')
      .then((response) => {
        setPrediction(response.data.prediction)
      })
      .catch((error) => {
        console.error(error)
        setError(
          `API error: ${error.response?.status || error.message}`
        )
      })
      .finally(() => {
        setLoading(false)
      })
  }, [])

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
            Understand your current academic performance and
            identify areas where you can improve.
          </p>
        </div>

        <div className="performance-hero-icon">
          📊
        </div>
      </section>

      {loading && (
        <div className="performance-state">
          <div className="performance-spinner" />
          <p>Analyzing your performance...</p>
        </div>
      )}

      {error && (
        <div className="performance-error">
          ⚠️ {error}
        </div>
      )}

      {!loading && !error && !prediction && (
        <div className="performance-state">
          <div className="empty-performance-icon">📈</div>
          <h2>No prediction available</h2>
          <p>
            Complete some learning activities to generate
            your performance prediction.
          </p>
        </div>
      )}

      {!loading && !error && prediction && (
        <>
          <section className="prediction-card">

            <div className="prediction-heading">
              <div>
                <p className="small-label">LATEST PREDICTION</p>
                <h2>Your Academic Outlook</h2>
              </div>

              <div
                className={`prediction-badge ${getPredictionClass(
                  prediction.prediction
                )}`}
              >
                {prediction.prediction}
              </div>
            </div>

            <div className="prediction-message">
              <span className="prediction-message-icon">
                🎯
              </span>

              <div>
                <strong>Performance Prediction</strong>

                <p>
                  This prediction is based on your current
                  academic activity and learning data.
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
                  <strong>
                    {prediction.attendance}%
                  </strong>
                </div>

                <div className="metric-bar">
                  <div
                    style={{
                      width: `${Math.min(
                        Number(prediction.attendance) || 0,
                        100
                      )}%`,
                    }}
                  />
                </div>
              </div>

              <div className="metric-card">
                <div className="metric-icon">📝</div>

                <div>
                  <span>Assignment Score</span>
                  <strong>
                    {prediction.assignment_score}
                  </strong>
                </div>

                <div className="metric-bar">
                  <div
                    style={{
                      width: `${Math.min(
                        Number(prediction.assignment_score) || 0,
                        100
                      )}%`,
                    }}
                  />
                </div>
              </div>

              <div className="metric-card">
                <div className="metric-icon">🧠</div>

                <div>
                  <span>Quiz Score</span>
                  <strong>
                    {prediction.quiz_score}
                  </strong>
                </div>

                <div className="metric-bar">
                  <div
                    style={{
                      width: `${Math.min(
                        Number(prediction.quiz_score) || 0,
                        100
                      )}%`,
                    }}
                  />
                </div>
              </div>

              <div className="metric-card">
                <div className="metric-icon">⏱️</div>

                <div>
                  <span>Study Hours</span>
                  <strong>
                    {prediction.study_hours}
                  </strong>
                </div>

                <div className="study-note">
                  Hours per day
                </div>
              </div>

            </div>
          </section>

          <section className="improvement-card">

            <div className="improvement-icon">
              💡
            </div>

            <div>
              <h2>Keep Improving</h2>

              <p>
                Regular attendance, completing assignments,
                practicing quizzes, and maintaining consistent
                study habits can help improve your academic
                performance.
              </p>
            </div>

          </section>
        </>
      )}

    </div>
  )
}

export default Performance
