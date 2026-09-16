import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'
import './TeacherDashboard.css'

const quickActions = [
  { title: 'Take attendance', text: 'Open today’s class register.', path: '/teacher/attendance', tone: 'green' },
  { title: 'Record paper marks', text: 'Enter exam or assignment results.', path: '/teacher/assessments', tone: 'orange' },
  { title: 'Run a lab quiz', text: 'Schedule a supervised computer-lab quiz.', path: '/teacher/lab-quizzes', tone: 'blue' },
  { title: 'Share learning notes', text: 'Create or manage student materials.', path: '/teacher/notes', tone: 'purple' },
]

function TeacherDashboard() {
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const fetchDashboard = useCallback(async () => {
    try {
      setLoading(true)
      setError('')
      const response = await api.get('/teacher/dashboard')
      setData(response.data)
    } catch (err) {
      console.error('Teacher dashboard error:', err)
      setError(err.response?.data?.error || 'Unable to load the teacher dashboard.')
    } finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchDashboard() }, [fetchDashboard])

  if (loading) return <div className="teacher-overview-state"><div className="teacher-overview-spinner" /><p>Loading your workspace...</p></div>
  if (error) return <div className="teacher-overview-state error"><h2>Dashboard unavailable</h2><p>{error}</p><button onClick={fetchDashboard}>Try again</button></div>

  const teacher = data?.teacher || {}
  const statistics = data?.statistics || {}
  const recentNotes = data?.recent_notes || []
  const firstName = String(teacher.name || 'Teacher').trim().split(/\s+/)[0]

  return (
    <div className="teacher-overview-page">
      <section className="teacher-overview-heading">
        <div><p>TEACHER OVERVIEW</p><h1>Welcome back, {firstName}</h1><span>See what needs your attention and continue today’s teaching work.</span></div>
        <button onClick={() => navigate('/teacher/analytics')}>Review learning insights →</button>
      </section>

      <section className="teacher-overview-stats">
        <article><span>Students</span><strong>{statistics.total_students ?? 0}</strong><small>Across the school records</small></article>
        <article><span>Quiz attempts</span><strong>{statistics.total_quiz_attempts ?? 0}</strong><small>Recorded online attempts</small></article>
        <article><span>Average quiz score</span><strong>{statistics.average_quiz_score ?? 0}%</strong><small>Online activity only</small></article>
        <article className="attention"><span>Needs follow-up</span><strong>{statistics.students_needing_improvement ?? 0}</strong><small>Open insights for evidence</small></article>
      </section>

      <section className="teacher-overview-section">
        <div className="teacher-overview-section-title"><div><h2>Continue your work</h2><p>Common teacher tasks, grouped in one place.</p></div></div>
        <div className="teacher-quick-grid">
          {quickActions.map((action) => (
            <button key={action.path} className={`teacher-quick-card ${action.tone}`} onClick={() => navigate(action.path)}>
              <span>{action.title.charAt(0)}</span><div><strong>{action.title}</strong><small>{action.text}</small></div><b>→</b>
            </button>
          ))}
        </div>
      </section>

      <div className="teacher-overview-columns">
        <section className="teacher-overview-section teacher-insight-callout">
          <p>LEARNING SUPPORT</p><h2>Move from scores to action</h2>
          <span>Learning Insights combines topic-level quiz evidence with paper marks and attendance, without hiding them inside one unclear score.</span>
          <button onClick={() => navigate('/teacher/analytics')}>Open student evidence</button>
        </section>

        <section className="teacher-overview-section">
          <div className="teacher-overview-section-title"><div><h2>Recent notes</h2><p>Your latest learning materials.</p></div><button onClick={() => navigate('/teacher/notes')}>View all</button></div>
          {recentNotes.length === 0 ? <div className="teacher-overview-empty">No notes uploaded yet.</div> : (
            <div className="teacher-recent-list">{recentNotes.slice(0, 4).map((note) => (
              <article key={note.id}><span>{note.subject?.charAt(0) || 'N'}</span><div><strong>{note.title}</strong><small>{note.subject}{note.chapter ? ` · Chapter ${note.chapter}` : ''}</small></div></article>
            ))}</div>
          )}
        </section>
      </div>
    </div>
  )
}

export default TeacherDashboard
