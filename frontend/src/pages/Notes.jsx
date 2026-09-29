import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import api from '../api'
import { useToast } from '../components/feedback/useToast'
import { downloadBlobResponse, fileExtension, formatFileSize } from '../utils/learningMaterials'
import './Notes.css'

function Notes() {
  const { toast } = useToast()
  const [searchParams] = useSearchParams()
  const subjectFilter = searchParams.get('subject') || ''
  const [notes, setNotes] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState(searchParams.get('search') || '')
  const [selectedNote, setSelectedNote] = useState(null)
  const [downloadingAttachmentId, setDownloadingAttachmentId] = useState(null)

  const downloadAttachment = async (note, attachment) => {
    try {
      setDownloadingAttachmentId(attachment.id)
      const response = await api.get(
        `/student/notes/${note.id}/attachments/${attachment.id}/download`,
        { responseType: 'blob' }
      )
      downloadBlobResponse(response, attachment.original_filename)
    } catch {
      toast.error('Unable to download this attachment.')
    } finally {
      setDownloadingAttachmentId(null)
    }
  }

  const renderAttachments = (note) => note.attachments?.length > 0 && (
    <section className="note-attachments" aria-label="Learning material attachments">
      <h3>{note.attachments.length} attachment{note.attachments.length === 1 ? '' : 's'}</h3>
      {note.attachments.map((attachment) => (
        <div className="material-attachment-row" key={attachment.id}>
          <span className="material-file-badge">{fileExtension(attachment.original_filename).toUpperCase()}</span>
          <span className="material-attachment-name" title={attachment.original_filename}>{attachment.original_filename}</span>
          <span className="material-attachment-size">{formatFileSize(attachment.size_bytes)}</span>
          <button
            type="button"
            className="material-download-button"
            onClick={() => downloadAttachment(note, attachment)}
            disabled={downloadingAttachmentId === attachment.id}
          >
            {downloadingAttachmentId === attachment.id ? 'Downloading…' : 'Download'}
          </button>
        </div>
      ))}
    </section>
  )

  useEffect(() => {
    api
      .get('/student/notes')
      .then((response) => {
        setNotes(response.data.notes || [])
      })
      .catch((error) => {
        console.error(error)
        setError('Unable to load your notes. Check your connection and try again.')
      })
      .finally(() => {
        setLoading(false)
      })
  }, [])

  useEffect(() => {
    if (!selectedNote) return undefined

    const closeOnEscape = (event) => {
      if (event.key === 'Escape') setSelectedNote(null)
    }

    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [selectedNote])

  const filteredNotes = notes.filter((note) => {
    if (subjectFilter && note.subject?.toLowerCase() !== subjectFilter.toLowerCase()) {
      return false
    }
    const text = `
      ${note.title}
      ${note.subject}
      ${note.chapter}
      ${note.content}
    `.toLowerCase()

    return text.includes(search.toLowerCase())
  })

  return (
    <div className="notes-page">

      <section className="notes-hero">
        <div>
          <p className="notes-label">CURRENT CLASS RESOURCES</p>
          <h1>Learning Materials</h1>
          <p>
            Read lesson notes and download materials shared for your current class.
          </p>
        </div>

        <div className="notes-hero-icon">📚</div>
      </section>

      <section className="notes-toolbar">
        <div className="notes-count">
          <strong>{notes.length}</strong>
          <span>Available Materials</span>
        </div>

        <div className="search-box">
          <span>🔍</span>
          <input
            type="text"
            placeholder="Search learning materials..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </section>

      {loading && (
        <div className="notes-state">
          <div className="notes-spinner" />
          <p>Loading learning notes...</p>
        </div>
      )}

      {error && (
        <div className="notes-error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => window.location.reload()}>Try again</button>
        </div>
      )}

      {!loading && !error && filteredNotes.length === 0 && (
        <div className="notes-state">
          <div className="empty-notes-icon">📖</div>
          <h2>
            {search ? 'No matching materials' : 'No learning materials yet'}
          </h2>
          <p>
            {search
              ? 'Try searching for another subject or chapter.'
              : 'Your teachers have not shared any materials for your current class yet.'}
          </p>
        </div>
      )}

      {!loading && !error && filteredNotes.length > 0 && (
        <section className="notes-grid">
          {filteredNotes.map((note) => (
            <article
              className="note-card"
              key={note.id}
            >

              <div className="note-card-top">
                <div className="note-icon">📘</div>

                <span className="subject-badge">
                  {note.subject}
                </span>
              </div>

              <h2>{note.title}</h2>

              <div className="chapter">
                <span>📑</span>
                <span>{note.chapter}</span>
              </div>

              <p className="material-audience">
                {note.audience_type === 'student' ? 'Shared with you' : note.audience_type === 'legacy' ? 'Legacy class resource' : 'Class resource'}
                {note.target_class_name ? ` · ${note.target_class_name}` : ''}
              </p>

              {note.content && <p className="note-content">{note.content}</p>}
              {renderAttachments(note)}

              {note.content && <button
                type="button"
                className="note-footer"
                onClick={() => setSelectedNote(note)}
              >
                <span>Read Full Note</span><span>→</span>
              </button>}

            </article>
          ))}
        </section>
      )}

      {selectedNote && (
        <div
          className="note-modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setSelectedNote(null)
          }}
          role="presentation"
        >
          <section
            className="note-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="note-modal-title"
          >
            <button
              type="button"
              className="note-modal-close"
              onClick={() => setSelectedNote(null)}
              aria-label="Close full note"
            >
              ×
            </button>

            <span className="subject-badge">{selectedNote.subject}</span>
            <h2 id="note-modal-title">{selectedNote.title}</h2>
            <p className="note-modal-chapter">📑 {selectedNote.chapter}</p>
            {selectedNote.content && <div className="note-modal-content">{selectedNote.content}</div>}
            {renderAttachments(selectedNote)}
          </section>
        </div>
      )}

    </div>
  )
}

export default Notes
