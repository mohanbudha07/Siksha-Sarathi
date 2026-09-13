import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import api from '../api'
import './TeacherNotes.css'

function TeacherEditNote() {
  const { noteId } = useParams()
  const navigate = useNavigate()
  const [form, setForm] = useState({
    title: '',
    subject: '',
    chapter: '',
    content: '',
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  useEffect(() => {
    api
      .get(`/teacher/notes/${noteId}`)
      .then((response) => {
        const note = response.data.note
        setForm({
          title: note.title || '',
          subject: note.subject || '',
          chapter: note.chapter || '',
          content: note.content || '',
        })
      })
      .catch((err) => {
        console.error('Load note error:', err)
        setError(err.response?.data?.error || 'Unable to load this note.')
      })
      .finally(() => setLoading(false))
  }, [noteId])

  const handleChange = (event) => {
    setForm((current) => ({
      ...current,
      [event.target.name]: event.target.value,
    }))
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError('')
    setSuccess('')
    setSaving(true)

    try {
      await api.put(`/teacher/notes/${noteId}`, form)
      setSuccess('Note updated successfully!')
      setTimeout(() => navigate('/teacher/notes'), 800)
    } catch (err) {
      console.error('Update note error:', err)
      setError(err.response?.data?.error || 'Unable to update this note.')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="teacher-loading">
        <div className="teacher-spinner"></div>
        <p>Loading note...</p>
      </div>
    )
  }

  return (
    <div className="teacher-notes-page">
      <section className="teacher-notes-hero">
        <div>
          <p className="teacher-label">TEACHER PANEL</p>
          <h1>Edit Note ✏️</h1>
          <p>Update this learning resource for your students.</p>
        </div>
        <div className="teacher-notes-hero-icon">📝</div>
      </section>

      <main className="teacher-notes-content" style={{ maxWidth: 760 }}>
        {error && !form.title ? (
          <div className="teacher-error">
            <h2>Unable to edit note</h2>
            <p>{error}</p>
            <button onClick={() => navigate('/teacher/notes')}>Back to Notes</button>
          </div>
        ) : (
          <form className="teacher-note-form" onSubmit={handleSubmit}>
            <div>
              <label htmlFor="title">Title</label>
              <input id="title" name="title" value={form.title} onChange={handleChange} required />
            </div>

            <div>
              <label htmlFor="subject">Subject</label>
              <input id="subject" name="subject" value={form.subject} onChange={handleChange} required />
            </div>

            <div>
              <label htmlFor="chapter">Chapter</label>
              <input id="chapter" name="chapter" value={form.chapter} onChange={handleChange} required />
            </div>

            <div>
              <label htmlFor="content">Content</label>
              <textarea id="content" name="content" rows="12" value={form.content} onChange={handleChange} required />
            </div>

            {error && <div className="teacher-note-form-message error">⚠️ {error}</div>}
            {success && <div className="teacher-note-form-message success">✅ {success}</div>}

            <div className="teacher-note-form-actions">
              <button className="teacher-note-save-button" type="submit" disabled={saving}>
                {saving ? 'Saving...' : 'Save Changes'}
              </button>
              <button className="teacher-note-cancel-button" type="button" onClick={() => navigate('/teacher/notes')}>
                Cancel
              </button>
            </div>
          </form>
        )}
      </main>
    </div>
  )
}

export default TeacherEditNote
