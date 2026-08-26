import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'
import './TeacherNotes.css'

function TeacherNotes() {
  const navigate = useNavigate()

  const [notes, setNotes] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const loadNotes = async () => {
      try {
        const response = await api.get('/teacher/notes')
        setNotes(response.data.notes || [])
      } catch (err) {
        console.error('Teacher notes error:', err)

        setError(
          err.response?.data?.error ||
            'Unable to load your notes.'
        )
      } finally {
        setLoading(false)
      }
    }

    loadNotes()
  }, [])

  if (loading) {
    return (
      <div className="teacher-loading">
        <div className="teacher-spinner"></div>
        <p>Loading your notes...</p>
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
    <div className="teacher-notes-page">

      <section className="teacher-notes-hero">
        <div>
          <p className="teacher-label">TEACHER PANEL</p>

          <h1>My Notes 📚</h1>

          <p>
            View and manage the learning materials you have
            uploaded for your students.
          </p>
        </div>

        <div className="teacher-notes-hero-icon">
          📚
        </div>
      </section>

      <main className="teacher-notes-content">

        <div className="teacher-notes-heading">
          <div>
            <h2>Your Learning Resources</h2>
            <p>
              All notes uploaded from your teacher account.
            </p>
          </div>

          <button
            onClick={() => navigate('/teacher/upload')}
          >
            + Upload Note
          </button>
        </div>

        {notes.length === 0 ? (
          <section className="teacher-notes-empty">
            <div className="empty-icon">📚</div>

            <h2>No notes uploaded yet</h2>

            <p>
              You haven't uploaded any learning resources.
              Start by uploading your first note.
            </p>

            <button
              onClick={() => navigate('/teacher/upload')}
            >
              Upload Your First Note
            </button>
          </section>
        ) : (
          <section className="teacher-notes-table-wrapper">

            <table className="teacher-notes-table">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Subject</th>
                  <th>Chapter</th>
                  <th>Upload Date</th>
                </tr>
              </thead>

              <tbody>
                {notes.map((note) => (
                  <tr key={note.id}>
                    <td>
                      <div className="note-title">
                        <span>📖</span>
                        <strong>{note.title}</strong>
                      </div>
                    </td>

                    <td>{note.subject}</td>

                    <td>{note.chapter}</td>

                    <td>
                      {note.created_at
                        ? new Date(
                            note.created_at
                          ).toLocaleDateString()
                        : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

          </section>
        )}

      </main>
    </div>
  )
}

export default TeacherNotes
