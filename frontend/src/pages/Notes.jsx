import { useEffect, useState } from 'react'
import api from '../api'
import './Notes.css'

function Notes() {
  const [notes, setNotes] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')

  useEffect(() => {
    api
      .get('/student/notes')
      .then((response) => {
        setNotes(response.data.notes || [])
      })
      .catch((error) => {
        console.error(error)
        setError(`API error: ${error.response?.status || error.message}`)
      })
      .finally(() => {
        setLoading(false)
      })
  }, [])

  const filteredNotes = notes.filter((note) => {
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
          <p className="notes-label">LEARNING RESOURCE</p>
          <h1>Learning Notes</h1>
          <p>
            Explore notes and study materials uploaded by your teacher.
          </p>
        </div>

        <div className="notes-hero-icon">📚</div>
      </section>

      <section className="notes-toolbar">
        <div className="notes-count">
          <strong>{notes.length}</strong>
          <span>Available Notes</span>
        </div>

        <div className="search-box">
          <span>🔍</span>
          <input
            type="text"
            placeholder="Search notes..."
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
        <div className="notes-error">
          ⚠️ {error}
        </div>
      )}

      {!loading && !error && filteredNotes.length === 0 && (
        <div className="notes-state">
          <div className="empty-notes-icon">📖</div>
          <h2>
            {search ? 'No matching notes' : 'No learning notes yet'}
          </h2>
          <p>
            {search
              ? 'Try searching for another subject or chapter.'
              : 'Your teacher has not uploaded any notes yet.'}
          </p>
        </div>
      )}

      {!loading && !error && filteredNotes.length > 0 && (
        <section className="notes-grid">
          {filteredNotes.map((note) => (
            <article className="note-card" key={note.id}>

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

              <p className="note-content">
                {note.content}
              </p>

              <div className="note-footer">
                <span>Learning Material</span>
                <span>→</span>
              </div>

            </article>
          ))}
        </section>
      )}

    </div>
  )
}

export default Notes
