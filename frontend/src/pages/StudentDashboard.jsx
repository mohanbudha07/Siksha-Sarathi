import { useEffect, useState } from 'react'
import axios from 'axios'
import './StudentDashboard.css'

function StudentDashboard() {
  const [student, setStudent] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    axios
      .get('/api/student/dashboard', {
        withCredentials: true,
      })
      .then((response) => {
        setStudent(response.data.student)
      })
      .catch((error) => {
        console.error(error)
        setError(`API error: ${error.response?.status || error.message}`)
      })
  }, [])

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <div>
          <h1>Siksha Sarathi</h1>
          <p>Student Dashboard</p>
        </div>

        <div className="student-info">
          {student ? (
            <>
              <strong>{student.full_name}</strong>
              <span>Grade {student.grade}</span>
            </>
          ) : (
            <span>Loading...</span>
          )}
        </div>
      </header>

      <main className="dashboard-content">
        <section className="welcome-section">
          <h2>
            {student
              ? `Welcome, ${student.full_name}!`
              : 'Welcome!'}
          </h2>

          <p>
            Continue your learning and track your academic progress.
          </p>

          {error && <p>{error}</p>}
        </section>

        <section className="dashboard-cards">
          <div className="dashboard-card">
            <h3>Performance</h3>
            <p>View your predicted academic performance.</p>
          </div>

          <div className="dashboard-card">
            <h3>Quizzes</h3>
            <p>Take quizzes and check your results.</p>
          </div>

          <div className="dashboard-card">
            <h3>AI Assistant</h3>
            <p>Get help with your learning questions.</p>
          </div>

          <div className="dashboard-card">
            <h3>Learning Notes</h3>
            <p>Access notes uploaded by your teacher.</p>
          </div>
        </section>
      </main>
    </div>
  )
}

export default StudentDashboard
