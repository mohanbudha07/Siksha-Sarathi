import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import SchoolOutlinedIcon from '@mui/icons-material/SchoolOutlined'
import QuizOutlinedIcon from '@mui/icons-material/QuizOutlined'
import MenuBookOutlinedIcon from '@mui/icons-material/MenuBookOutlined'
import AutoAwesomeOutlinedIcon from '@mui/icons-material/AutoAwesomeOutlined'
import EventNoteOutlinedIcon from '@mui/icons-material/EventNoteOutlined'
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
  const [loading, setLoading] = useState(true)

  const navigate = useNavigate()

  const loadDashboard = async () => {
    setLoading(true)
    setError('')
    try {
      const response = await api.get('/student/dashboard')
      setStudent(response.data.student)
      setStats(response.data.stats)
      setCurrentClass(response.data.current_class)
      setSubjects(response.data.subjects || [])
      setRecentActivity(response.data.recent_activity || [])
      setSubjectPerformance(response.data.subject_performance || [])
    } catch (requestError) {
      console.error('Student dashboard error:', requestError)
      setError('Unable to load your learning dashboard. Check your connection and try again.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadDashboard() }, [])

  const formatActivityDate = (value) => {
    if (!value) return ''
    const parsed = new Date(value)
    return Number.isNaN(parsed.getTime()) ? '' : parsed.toLocaleDateString()
  }

  return (
    <div className="dashboard">

      <header className="dashboard-header">
        <div>
          <p className="dashboard-eyebrow">STUDENT OVERVIEW</p>
          <h1>{student ? `Welcome back, ${student.full_name}` : 'Your learning'}</h1>
          <p>Keep practising one topic at a time.</p>
        </div>
      </header>

      <main className="dashboard-content">

        {error && <div className="dashboard-error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={loadDashboard}>Try again</button>
        </div>}

        {/* Statistics */}
        <section className="stats-grid">
          <div className="stat-card">
            <div className="stat-icon"><SchoolOutlinedIcon aria-hidden="true" /></div>
            <div>
              <span>Current class</span>
              <strong>{loading ? '—' : currentClass?.name || 'Unassigned'}</strong>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-icon"><SchoolOutlinedIcon aria-hidden="true" /></div>
            <div>
              <span>Subjects</span>
              <strong>{loading ? '—' : stats?.subject_count ?? 0}</strong>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-icon"><QuizOutlinedIcon aria-hidden="true" /></div>
            <div>
              <span>Completed Quizzes</span>
              <strong>{loading ? '—' : stats?.completed_quizzes ?? 0}</strong>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-icon"><AutoAwesomeOutlinedIcon aria-hidden="true" /></div>
            <div>
              <span>Average quiz score</span>
              <strong>{loading ? '—' : `${stats?.average_quiz_score ?? 0}%`}</strong>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-icon"><MenuBookOutlinedIcon aria-hidden="true" /></div>
            <div>
              <span>Learning notes</span>
              <strong>{loading ? '—' : stats?.available_notes ?? 0}</strong>
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

          <button
            type="button"
            className="dashboard-card"
            onClick={() => navigate('/student/quiz')}
          >
            <div className="card-icon"><QuizOutlinedIcon aria-hidden="true" /></div>
            <h3>Quizzes</h3>
            <p>Test your knowledge and improve your understanding.</p>
            <span className="dashboard-card-action">Take a quiz <span aria-hidden="true">→</span></span>
          </button>

          <button
            type="button"
            className="dashboard-card"
            onClick={() => navigate('/student/notes')}
          >
            <div className="card-icon"><MenuBookOutlinedIcon aria-hidden="true" /></div>
            <h3>Learning Notes</h3>
            <p>Read study materials and notes uploaded by your teacher.</p>
            <span className="dashboard-card-action">Open notes <span aria-hidden="true">→</span></span>
          </button>

          <button
            type="button"
            className="dashboard-card"
            onClick={() => navigate('/student/practice-plan')}
          >
            <div className="card-icon"><EventNoteOutlinedIcon aria-hidden="true" /></div>
            <h3>My Practice Plan</h3>
            <p>Choose a next step based on your recent learning evidence.</p>
            <span className="dashboard-card-action">View my plan <span aria-hidden="true">→</span></span>
          </button>

          <button
            type="button"
            className="dashboard-card"
            onClick={() => navigate('/student/ai')}
          >
            <div className="card-icon"><AutoAwesomeOutlinedIcon aria-hidden="true" /></div>
            <h3>AI Assistant</h3>
            <p>Ask questions and get help with your subjects.</p>
            <span className="dashboard-card-action">Ask a question <span aria-hidden="true">→</span></span>
          </button>

        </section>

      </main>
    </div>
  )
}

export default StudentDashboard
