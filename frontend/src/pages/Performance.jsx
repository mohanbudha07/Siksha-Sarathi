import { useEffect, useState } from 'react'
import axios from 'axios'

function Performance() {
  const [prediction, setPrediction] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    axios
      .get('/api/student/prediction', {
        withCredentials: true,
      })
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

  return (
    <div>
      <header>
        <h1>Siksha Sarathi</h1>
        <p>Student Performance</p>
      </header>

      <main>
        <h2>Performance Prediction</h2>

        {loading && <p>Loading performance...</p>}

        {error && <p>{error}</p>}

        {!loading && !error && !prediction && (
          <p>No performance prediction is available yet.</p>
        )}

        {prediction && (
          <section>
            <h3>Latest Prediction</h3>

            <h2>{prediction.prediction}</h2>

            <p>Attendance: {prediction.attendance}%</p>

            <p>
              Assignment Score: {prediction.assignment_score}
            </p>

            <p>
              Quiz Score: {prediction.quiz_score}
            </p>

            <p>
              Study Hours: {prediction.study_hours}
            </p>
          </section>
        )}
      </main>
    </div>
  )
}

export default Performance
