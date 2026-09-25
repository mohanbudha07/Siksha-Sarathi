import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'
import './StudentDashboard.css'

function StudentDashboard() {
  const [student, setStudent] = useState(null)
  const [stats, setStats] = useState(null)
  const [currentClass, setCurrentClass] = useState(null)
  const [subjects, setSubjects] = useState([])
  const [recentActivity, setRecentActivity] = useState([])
  const [subjectPerformance, setSubjectPerformance] = useState([])
  const [error, setError] = useState('')

  const navigate = useNavigate()

  useEffect(() => {
    api
      .get('/student/dashboard')
      .then((response) => {
        setStudent(response.data.student)
        setStats(response.data.stats)
        setCurrentClass(response.data.current_class)
        setSubjects(response.data.subjects || [])
        setRecentActivity(response.data.recent_activity || [])
        setSubjectPerformance(response.data.subject_performance || [])
      })
      .catch((error) => {
        console.error(error)
        setError(
          `API error: ${error.response?.status || error.message}`
        )
      })
  }, [])

  const formatActivityDate = (value) => {
    if (!value) return ''
    const parsed = new Date(value)
    return Number.isNaN(parsed.getTime()) ? '' : parsed.toLocaleDateString()
  }

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
              <span>{currentClass?.name || `Grade ${student.grade}`}</span>
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
            🎓 {currentClass?.name || 'No class assigned'}
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
                {stats ? stats.available_notes : '--'}
              </strong>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-icon">📚</div>
            <div>
              <span>Subjects</span>
              <strong>{stats ? stats.subject_count : '--'}</strong>
            </div>
          </div>

        </section>

        {!currentClass && <section className="dashboard-empty"><strong>No class assigned yet</strong><span>Your class subjects, notes, and quizzes will appear here once your school assigns you to a class.</span></section>}

        <section className="dashboard-overview-grid">
          <div className="dashboard-panel">
            <div className="panel-heading"><h2>My Subjects</h2><span>{subjects.length}</span></div>
            {subjects.length === 0 ? <p className="dashboard-empty-text">No subjects are available yet.</p> : <div className="subject-list">{subjects.map((subject) => <span key={subject.id}>{subject.name}{subject.code ? ` · ${subject.code}` : ''}</span>)}</div>}
          </div>
          <div className="dashboard-panel">
            <div className="panel-heading"><h2>Subject Performance</h2></div>
            {subjectPerformance.length === 0 ? <p className="dashboard-empty-text">Complete a quiz to see subject performance.</p> : <div className="performance-list">{subjectPerformance.map((item) => <div key={item.subject}><span>{item.subject}</span><strong>{item.average_score}% <small>{item.attempts} attempt{item.attempts === 1 ? '' : 's'}</small></strong></div>)}</div>}
          </div>
        </section>

        <section className="dashboard-panel dashboard-activity">
          <div className="panel-heading"><h2>Recent Quiz Activity</h2></div>
          {recentActivity.length === 0 ? <p className="dashboard-empty-text">No quiz attempts yet. Your completed quizzes will appear here.</p> : <div className="activity-list">{recentActivity.map((item) => <div key={item.attempt_id}><div><strong>{item.quiz_title}</strong><span>{item.subject}{formatActivityDate(item.created_at) ? ` · ${formatActivityDate(item.created_at)}` : ''}</span></div><strong>{item.score}/{item.total_questions} <small>{item.percentage}%</small></strong></div>)}</div>}
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
