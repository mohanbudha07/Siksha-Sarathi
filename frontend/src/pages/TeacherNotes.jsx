import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'
import { useToast } from '../components/feedback/useToast'
import { downloadBlobResponse, fileExtension, formatFileSize } from '../utils/learningMaterials'
import './TeacherNotes.css'

function TeacherNotes() {
  const navigate = useNavigate()
  const { confirm, toast } = useToast()

  const [notes, setNotes] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [deletingId, setDeletingId] = useState(null)
  const [downloadingId, setDownloadingId] = useState(null)

  const downloadAttachment = async (note, attachment) => {
    try {
      setDownloadingId(attachment.id)
      const response = await api.get(
        `/teacher/notes/${note.id}/attachments/${attachment.id}/download`,
        { responseType: 'blob' }
      )
      downloadBlobResponse(response, attachment.original_filename)
    } catch {
      toast.error('Unable to download this attachment.')
    } finally {
      setDownloadingId(null)
    }
  }

  useEffect(() => {
    const loadNotes = async () => {
      try {
        const response = await api.get('/teacher/notes')
        setNotes(response.data.notes || [])
      } catch (err) {
        console.error('Teacher notes error:', err)

        setError('Unable to load your Learning Materials.')
      } finally {
        setLoading(false)
      }
    }

    loadNotes()
  }, [])

  const handleDelete = async (note) => {
    const confirmed = await confirm({
      title: 'Delete note?',
      description: `Delete "${note.title}"? This action cannot be undone.`,
      confirmLabel: 'Delete Note',
      variant: 'danger',
    })
    if (!confirmed) return

    setDeletingId(note.id)

    try {
      await api.delete(`/teacher/notes/${note.id}`)
      setNotes((currentNotes) =>
        currentNotes.filter((item) => item.id !== note.id)
      )
      toast.success('Note removed.')
    } catch (err) {
      console.error('Delete note error:', err)
      toast.error('Unable to delete this note.')
    } finally {
      setDeletingId(null)
    }
  }

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

          <h1>My Learning Materials</h1>

          <p>
            Manage class resources and individual Student materials you have uploaded.
          </p>
        </div>

        <div className="teacher-notes-hero-icon">
          📚
        </div>
      </section>

      <main className="teacher-notes-content">

        <div className="teacher-notes-heading">
          <div>
            <h2>Your materials</h2>
            <p>
              Only materials uploaded from your teacher account are shown.
            </p>
          </div>

          <button
            onClick={() => navigate('/teacher/upload')}
          >
            + Upload Material
          </button>
        </div>

        {notes.length === 0 ? (
          <section className="teacher-notes-empty">
            <div className="empty-icon">📚</div>

            <h2>No Learning Materials yet</h2>

            <p>
              You have not shared any materials yet. Start with a class resource or an individual Student item.
            </p>

            <button
              onClick={() => navigate('/teacher/upload')}
            >
              Upload Learning Material
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
                  <th>Target / Audience</th>
                  <th>Attachments</th>
                  <th>Created</th>
                  <th>Actions</th>
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
                      {note.target_class_name || 'Legacy subject access'}
                      <small className="teacher-material-audience">
                        {note.audience_type === 'student' ? `Specific student · ${note.target_student_name}` : note.audience_type === 'legacy' ? 'Legacy' : 'Entire class'}
                      </small>
                    </td>

                    <td>
                      <span>{note.attachment_count || 0} file{note.attachment_count === 1 ? '' : 's'}</span>
                      {note.attachments?.map((attachment) => <button
                        key={attachment.id}
                        type="button"
                        className="teacher-material-download"
                        onClick={() => downloadAttachment(note, attachment)}
                        disabled={downloadingId === attachment.id}
                        title={`${attachment.original_filename} · ${formatFileSize(attachment.size_bytes)}`}
                      >
                        <span className="material-file-badge">{fileExtension(attachment.original_filename).toUpperCase()}</span>
                        {attachment.original_filename}
                      </button>)}
                    </td>

                    <td>
                      {note.created_at || '—'}
                    </td>

                    <td>
                      <div className="note-actions">
                        <button
                          type="button"
                          className="edit-note-button"
                          onClick={() => navigate(`/teacher/notes/${note.id}/edit`)}
                        >
                          Edit
                        </button>

                        <button
                          type="button"
                          className="delete-note-button"
                          onClick={() => handleDelete(note)}
                          disabled={deletingId === note.id}
                        >
                          {deletingId === note.id ? 'Deleting...' : 'Delete'}
                        </button>
                      </div>
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
