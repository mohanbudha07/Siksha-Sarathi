import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'
import './TeacherDashboard.css'

function TeacherDashboard() {
  const navigate = useNavigate()

  const [teacher, setTeacher] = useState(null)
  const [statistics, setStatistics] = useState({
    total_notes: 0,
  })
  const [recentNotes, setRecentNotes] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const loadDashboard = async () => {
      try {
        const response = await api.get('/teacher/dashboard')

        setTeacher(response.data.teacher)
        setStatistics(response.data.statistics)
        setRecentNotes(response.data.recent_notes || [])
      } catch (err) {
        console.error('Teacher dashboard error:', err)

        setError(
          err.response?.data?.error ||
            'Unable to load teacher dashboard.'
        )
      } finally {
        setLoading(false)
      }
    }

    loadDashboard()
  }, [])

  if (loading) {
    return (
      <div className="teacher-loading">
        <div className="teacher-spinner"></div>
        <p>Loading your dashboard...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="teacher-error">
        <div>⚠️</div>
        <h2>Something went wrong</h2>
        <p>{error}</p>
        <button onClick={() => window.location.reload()}>
          Try Again
        </button>
      </div>
    )
  }

  return (
    <div className="teacher-dashboard">

      <section className="teacher-hero">

        <div>
          <p className="teacher-label">
            TEACHER PANEL
          </p>

          <h1>
            Welcome, {teacher?.name || 'Teacher'} 👋
          </h1>

          <p>
            Manage your learning resources and support your
            students from one place.
          </p>
        </div>

        <div className="teacher-hero-icon">
          👨‍🏫
        </div>

      </section>

      <main className="teacher-content">

        {/* STATISTICS */}

        <section className="teacher-stats">

          <div className="teacher-stat-card">

            <div className="stat-icon">
              📚
            </div>

            <div>
              <p>Total Notes</p>

              <h2>
                {statistics.total_notes}
              </h2>
            </div>

          </div>

          <div className="teacher-stat-card">

            <div className="stat-icon">
              📤
            </div>

            <div>
              <p>Resources</p>

              <h2>
                {statistics.total_notes}
              </h2>
            </div>

          </div>

          <div className="teacher-stat-card">

            <div className="stat-icon">
              👨‍🎓
            </div>

            <div>
              <p>Students</p>

              <h2>—</h2>
            </div>

          </div>

        </section>

        {/* QUICK ACTIONS */}

        <section className="teacher-section">

          <div className="teacher-section-heading">
            <div>
              <h2>Quick Actions</h2>
              <p>
                Manage your teaching resources.
              </p>
            </div>
          </div>

          <section className="teacher-cards">

            <div
              className="teacher-card"
              onClick={() => navigate('/teacher/upload')}
            >
              <div className="teacher-card-icon">
                📤
              </div>

              <h3>Upload Notes</h3>

              <p>
                Upload new study materials, chapters and
                subject notes for your students.
              </p>

              <button>
                Upload Notes →
              </button>
            </div>

            <div
              className="teacher-card"
              onClick={() => navigate('/teacher/notes')}
            >
              <div className="teacher-card-icon">
                📚
              </div>

              <h3>My Notes</h3>

              <p>
                View and manage the learning resources you
                have uploaded for students.
              </p>

              <button>
                View Notes →
              </button>
            </div>

          </section>

        </section>

        {/* RECENT NOTES */}

        <section className="recent-notes-section">

          <div className="recent-heading">

            <div>
              <h2>Recent Notes</h2>

              <p>
                Your latest uploaded learning materials.
              </p>
            </div>

            <button
              onClick={() => navigate('/teacher/notes')}
            >
              View All
            </button>

          </div>

          {recentNotes.length === 0 ? (

            <div className="empty-notes">

              <div>📚</div>

              <h3>No notes uploaded yet</h3>

              <p>
                Start by uploading your first learning resource.
              </p>

              <button
                onClick={() => navigate('/teacher/upload')}
              >
                Upload Your First Note
              </button>

            </div>

          ) : (

            <div className="recent-notes-list">

              {recentNotes.map((note) => (

                <div
                  className="recent-note"
                  key={note.id}
                >

                  <div className="recent-note-icon">
                    📖
                  </div>

                  <div className="recent-note-info">

                    <h3>
                      {note.title}
                    </h3>

                    <p>
                      {note.subject} • {note.chapter}
                    </p>

                  </div>

                  <div className="recent-note-date">
                    {note.created_at
                      ? new Date(
                          note.created_at
                        ).toLocaleDateString()
                      : ''}
                  </div>

                </div>

              ))}

            </div>

          )}

        </section>

        {/* TEACHER TIP */}

        <section className="teacher-info-panel">

          <div className="info-icon">
            💡
          </div>

          <div>
            <h3>Teacher Tip</h3>

            <p>
              Keep your learning materials organized by
              subject and chapter so students can find them
              easily.
            </p>
          </div>

        </section>

      </main>

    </div>
  )
}

export default TeacherDashboard
