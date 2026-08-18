import { useEffect, useState } from 'react'
import api from '../api'

function Notes() {
  const [notes, setNotes] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .get('/student/notes')
      .then((response) => {
        setNotes(response.data.notes)
      })
      .catch((error) => {
        console.error(error)
        setError(
          `API error: ${error.response?.status || error.message}`
        )
      })
      .finally(() => {
        setLoading(false)
      })
  }, [])

  return (
    <div>
      <header>
        <h1>Siksha Sarathi</h1>
        <p>Learning Notes</p>
      </header>

      <main>
        <h2>Learning Notes</h2>

        {loading && <p>Loading notes...</p>}

        {error && <p>{error}</p>}

        {!loading && !error && notes.length === 0 && (
          <p>No learning notes are available yet.</p>
        )}

        {notes.map((note) => (
          <article key={note.id}>
            <h3>{note.title}</h3>
            <p>Subject: {note.subject}</p>
            <p>Chapter: {note.chapter}</p>
            <p>{note.content}</p>
          </article>
        ))}
      </main>
    </div>
  )
}

export default Notes
