import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'
import './TeacherNotes.css'   // reuse existing styles

function TeacherUploadNote() {
  const navigate = useNavigate()

  const [form, setForm] = useState({
    title: '',
    subject: '',
    chapter: '',
    content: '',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const handleChange = (e) => {
    setForm({
      ...form,
      [e.target.name]: e.target.value,
    })
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setSuccess('')
    setLoading(true)

    try {
      await api.post('/teacher/notes', form)
      setSuccess('Note uploaded successfully!')
      setForm({ title: '', subject: '', chapter: '', content: '' })

      // Optional: go back to notes list after 1.5 seconds
      setTimeout(() => {
        navigate('/teacher/notes')
      }, 1500)
    } catch (err) {
      console.error(err)
      setError(
        err.response?.data?.error || 'Failed to upload note. Please try again.'
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="teacher-notes-page">
      <section className="teacher-notes-hero">
        <div>
          <p className="teacher-label">TEACHER PANEL</p>
          <h1>Upload Note 📝</h1>
          <p>Share learning materials with your students.</p>
        </div>
        <div className="teacher-notes-hero-icon">📤</div>
      </section>

      <main className="teacher-notes-content" style={{ maxWidth: 700 }}>
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div>
            <label>Title</label>
            <input
              type="text"
              name="title"
              value={form.title}
              onChange={handleChange}
              required
              placeholder="e.g. Introduction to Photosynthesis"
              style={{ width: '100%', padding: 10, marginTop: 4 }}
            />
          </div>

          <div>
            <label>Subject</label>
            <input
              type="text"
              name="subject"
              value={form.subject}
              onChange={handleChange}
              required
              placeholder="e.g. Science"
              style={{ width: '100%', padding: 10, marginTop: 4 }}
            />
          </div>

          <div>
            <label>Chapter</label>
            <input
              type="text"
              name="chapter"
              value={form.chapter}
              onChange={handleChange}
              required
              placeholder="e.g. Chapter 5"
              style={{ width: '100%', padding: 10, marginTop: 4 }}
            />
          </div>

          <div>
            <label>Content</label>
            <textarea
              name="content"
              value={form.content}
              onChange={handleChange}
              required
              rows={8}
              placeholder="Write the full note content here..."
              style={{ width: '100%', padding: 10, marginTop: 4 }}
            />
          </div>

          {error && <div style={{ color: 'red' }}>⚠️ {error}</div>}
          {success && <div style={{ color: 'green' }}>✅ {success}</div>}

          <div style={{ display: 'flex', gap: 12, marginTop: 10 }}>
            <button
              type="submit"
              disabled={loading}
              style={{
                padding: '12px 24px',
                background: '#4f00ff',
                color: 'white',
                border: 'none',
                borderRadius: 8,
                cursor: 'pointer',
                fontWeight: 600,
              }}
            >
              {loading ? 'Uploading...' : 'Upload Note'}
            </button>

            <button
              type="button"
              onClick={() => navigate('/teacher/notes')}
              style={{
                padding: '12px 24px',
                background: '#e5e7eb',
                border: 'none',
                borderRadius: 8,
                cursor: 'pointer',
              }}
            >
              Cancel
            </button>
          </div>
        </form>
      </main>
    </div>
  )
}

export default TeacherUploadNote