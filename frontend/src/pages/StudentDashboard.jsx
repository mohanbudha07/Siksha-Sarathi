import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'
import './StudentDashboard.css'

function StudentDashboard() {
  const [student, setStudent] = useState(null)
  const [stats, setStats] = useState(null)
  const [error, setError] = useState('')

  const navigate = useNavigate()

  useEffect(() => {
    api
      .get('/student/dashboard')
      .then((response) => {
        setStudent(response.data.student)
        setStats(response.data.stats)
      })
      .catch((error) => {
        console.error(error)
        setError(
          `API error: ${error.response?.status || error.message}`
        )
      })
  }, [])

  return (
    <div className="dashboard">

      <header className="dashboard-header">
        <div>
          <h1>Your learning</h1>
          <p>Keep practising one topic at a time.</p>
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
          <div>
            <h2>
              {student
                ? `Welcome back, ${student.full_name}!`
                : 'Welcome!'}
            </h2>

            <p>
              Continue learning, take quizzes, and track your academic progress.
            </p>
          </div>

          <div className="welcome-badge">
            🎓 Grade {student?.grade || '--'}
          </div>
        </section>

        {error && (
          <div className="dashboard-error">
            {error}
          </div>
        )}

        {/* Statistics */}
        <section className="stats-grid">

          <div className="stat-card">
            <div className="stat-icon">📝</div>
            <div>
              <span>Completed Quizzes</span>
              <strong>
                {stats ? stats.completed_quizzes : '--'}
              </strong>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-icon">📊</div>
            <div>
              <span>Average Quiz Score</span>
              <strong>
                {stats ? `${stats.average_quiz_score}%` : '--'}
              </strong>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-icon">📚</div>
            <div>
              <span>Learning Notes</span>
              <strong>
                {stats ? stats.total_notes : '--'}
              </strong>
            </div>
          </div>

        </section>

        <section className="student-plan-prompt">
          <div>
            <span className="section-label">YOUR NEXT STEP</span>
            <h2>Make a practice plan</h2>
            <p>See topics to review from your recent quiz answers, with notes and practice quizzes when available.</p>
          </div>
          <button type="button" onClick={() => navigate('/student/practice-plan')}>
            View my plan →
          </button>
        </section>

        {/* Learning activities */}
        <section className="section-heading">
          <h2>Continue Learning</h2>
          <p>Choose an activity to continue your studies.</p>
        </section>

        <section className="dashboard-cards">

          <div
            className="dashboard-card"
            onClick={() => navigate('/student/quiz')}
          >
            <div className="card-icon">🧠</div>
            <h3>Quizzes</h3>
            <p>
              Test your knowledge and improve your understanding.
            </p>
            <button>Take a Quiz →</button>
          </div>

          <div
            className="dashboard-card"
            onClick={() => navigate('/student/notes')}
          >
            <div className="card-icon">📖</div>
            <h3>Learning Notes</h3>
            <p>
              Read study materials and notes uploaded by your teacher.
            </p>
            <button>Open Notes →</button>
          </div>

          <div
            className="dashboard-card"
            onClick={() => navigate('/student/ai')}
          >
            <div className="card-icon">🤖</div>
            <h3>AI Assistant</h3>
            <p>
              Ask questions and get help with your secondary-level subjects.
            </p>
            <button>Ask AI →</button>
          </div>

        </section>

      </main>
    </div>
  )
}

export default StudentDashboard
