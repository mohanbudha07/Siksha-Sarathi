import { useEffect, useMemo, useState } from 'react'
import api from '../api'
import './TeacherLabQuizzes.css'

const pad = (value) => String(value).padStart(2, '0')

function toLocalInput(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function formatDate(value) {
  if (!value) return 'Not available'
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function TeacherLabQuizzes() {
  const initialStart = new Date(Date.now() + 5 * 60 * 1000)
  const initialEnd = new Date(Date.now() + 50 * 60 * 1000)
  const [quizzes, setQuizzes] = useState([])
  const [assignments, setAssignments] = useState([])
  const [sessions, setSessions] = useState([])
  const [quizId, setQuizId] = useState('')
  const [classId, setClassId] = useState('')
  const [accessCode, setAccessCode] = useState('')
  const [startsAt, setStartsAt] = useState(toLocalInput(initialStart))
  const [endsAt, setEndsAt] = useState(toLocalInput(initialEnd))
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [closingId, setClosingId] = useState(null)
  const [error, setError] = useState('')
  const [createdCode, setCreatedCode] = useState('')

  const publishedQuizzes = useMemo(
    () => quizzes.filter((quiz) => quiz.is_published),
    [quizzes]
  )

  const selectedQuiz = publishedQuizzes.find(
    (quiz) => String(quiz.id) === String(quizId)
  )

  const eligibleAssignments = useMemo(() => {
    if (!selectedQuiz) return assignments
    return assignments.filter(
      (item) => item.subject.toLowerCase() === selectedQuiz.subject.toLowerCase()
    )
  }, [assignments, selectedQuiz])

  const loadData = async () => {
    try {
      setLoading(true)
      setError('')
      const [quizResponse, analyticsResponse, sessionResponse] = await Promise.all([
        api.get('/teacher/quizzes'),
        api.get('/teacher/learning-analytics'),
        api.get('/teacher/quiz-sessions'),
      ])
      setQuizzes(quizResponse.data.quizzes || [])
      setAssignments(analyticsResponse.data.assignments || [])
      setSessions(sessionResponse.data.sessions || [])
    } catch (err) {
      console.error('Load lab quiz data error:', err)
      setError(err.response?.data?.error || 'Unable to load lab quiz information.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  useEffect(() => {
    if (!eligibleAssignments.some((item) => String(item.class_id) === String(classId))) {
      setClassId(eligibleAssignments[0] ? String(eligibleAssignments[0].class_id) : '')
    }
  }, [classId, eligibleAssignments])

  const generateCode = () => {
    const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    const values = new Uint32Array(6)
    window.crypto.getRandomValues(values)
    const code = Array.from(values, (value) => alphabet[value % alphabet.length]).join('')
    setAccessCode(code)
  }

  const handleCreate = async (event) => {
    event.preventDefault()
    setError('')
    setCreatedCode('')
    try {
      setSaving(true)
      const response = await api.post('/teacher/quiz-sessions', {
        quiz_id: Number(quizId),
        class_id: Number(classId),
        access_code: accessCode.trim(),
        starts_at: new Date(startsAt).toISOString(),
        ends_at: new Date(endsAt).toISOString(),
      })
      setCreatedCode(response.data.access_code)
      setAccessCode('')
      await loadData()
    } catch (err) {
      console.error('Create lab session error:', err)
      setError(err.response?.data?.error || 'Unable to schedule this lab quiz.')
    } finally {
      setSaving(false)
    }
  }

  const handleClose = async (labSession) => {
    if (!window.confirm(`Close “${labSession.title}” for ${labSession.class_name}?`)) return
    try {
      setClosingId(labSession.id)
      setError('')
      await api.post(`/teacher/quiz-sessions/${labSession.id}/close`)
      await loadData()
    } catch (err) {
      console.error('Close lab session error:', err)
      setError(err.response?.data?.error || 'Unable to close this lab session.')
    } finally {
      setClosingId(null)
    }
  }

  return (
    <div className="lab-quiz-page">
      <section className="lab-quiz-hero">
        <div>
          <p>COMPUTER-LAB ASSESSMENT</p>
          <h1>Lab Quiz Sessions</h1>
          <span>Schedule a controlled quiz for an assigned class and share a temporary code in the lab.</span>
        </div>
        <div className="lab-hero-icon">🖥️</div>
      </section>

      {error && <div className="lab-alert lab-alert-error">⚠️ {error}</div>}
      {createdCode && (
        <div className="lab-alert lab-alert-success">
          Session created. Write this one-time access code on the board: <strong>{createdCode}</strong>
        </div>
      )}

      <div className="lab-quiz-layout">
        <form className="lab-session-form" onSubmit={handleCreate}>
          <div className="lab-section-heading">
            <span>1</span>
            <div><h2>Schedule a session</h2><p>Times are displayed in your computer’s local timezone.</p></div>
          </div>

          <label>
            Published quiz
            <select value={quizId} onChange={(event) => setQuizId(event.target.value)} required>
              <option value="">Select a quiz</option>
              {publishedQuizzes.map((quiz) => (
                <option value={quiz.id} key={quiz.id}>{quiz.title} — {quiz.subject}</option>
              ))}
            </select>
          </label>

          <label>
            Assigned class
            <select value={classId} onChange={(event) => setClassId(event.target.value)} required>
              <option value="">Select a matching class</option>
              {eligibleAssignments.map((assignment) => (
                <option value={assignment.class_id} key={`${assignment.class_id}-${assignment.subject}`}>
                  {assignment.class_name} — {assignment.subject}
                </option>
              ))}
            </select>
          </label>

          <div className="lab-time-grid">
            <label>Starts at<input type="datetime-local" value={startsAt} onChange={(event) => setStartsAt(event.target.value)} required /></label>
            <label>Ends at<input type="datetime-local" value={endsAt} onChange={(event) => setEndsAt(event.target.value)} required /></label>
          </div>

          <label>
            Temporary access code
            <div className="lab-code-field">
              <input minLength="4" maxLength="20" value={accessCode} onChange={(event) => setAccessCode(event.target.value.toUpperCase())} placeholder="Example: LAB2048" required />
              <button type="button" onClick={generateCode}>Generate</button>
            </div>
          </label>

          <button className="lab-primary-button" disabled={saving || !publishedQuizzes.length || !eligibleAssignments.length}>
            {saving ? 'Scheduling...' : 'Schedule Lab Quiz'}
          </button>

          {!publishedQuizzes.length && <p className="lab-form-hint">Create and publish a teacher-owned quiz first.</p>}
          {selectedQuiz && !eligibleAssignments.length && <p className="lab-form-hint">You are not assigned to teach {selectedQuiz.subject} in a class.</p>}
        </form>

        <section className="lab-guidance-card">
          <h2>Safe lab workflow</h2>
          <ol>
            <li>Seat students at school computers and verify the class roster.</li>
            <li>Open the session only for the planned examination window.</li>
            <li>Share the code inside the lab, not through public messages.</li>
            <li>Check submission counts before closing the session.</li>
          </ol>
          <p>A network failure does not create a zero mark. A result is saved only after submission succeeds.</p>
        </section>
      </div>

      <section className="lab-session-list">
        <div className="lab-list-heading"><div><h2>Your sessions</h2><p>Access codes cannot be viewed again after creation.</p></div><button onClick={loadData}>Refresh</button></div>
        {loading ? <div className="lab-empty-state">Loading sessions...</div> : sessions.length === 0 ? <div className="lab-empty-state">No lab quiz sessions scheduled yet.</div> : (
          <div className="lab-session-grid">
            {sessions.map((item) => (
              <article className="lab-session-card" key={item.id}>
                <div className="lab-session-top"><span className={`lab-state lab-state-${item.state}`}>{item.state}</span><strong>{item.submission_count} submitted</strong></div>
                <h3>{item.title}</h3>
                <p>{item.subject} · {item.class_name}</p>
                <dl><div><dt>Starts</dt><dd>{formatDate(item.starts_at)}</dd></div><div><dt>Ends</dt><dd>{formatDate(item.ends_at)}</dd></div></dl>
                {['scheduled', 'active'].includes(item.state) && <button className="lab-close-button" onClick={() => handleClose(item)} disabled={closingId === item.id}>{closingId === item.id ? 'Closing...' : 'Close Session'}</button>}
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

export default TeacherLabQuizzes
