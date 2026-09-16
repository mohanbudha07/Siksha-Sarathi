import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import api from '../api'
import './Quiz.css'

const formatTime = (value) => new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
  timeStyle: 'short',
}).format(new Date(value))

function Quiz() {
  const [searchParams] = useSearchParams()
  const requestedQuizId = searchParams.get('quiz_id')
  const [quizzes, setQuizzes] = useState([])
  const [labSessions, setLabSessions] = useState([])
  const [quiz, setQuiz] = useState(null)
  const [selectedQuizId, setSelectedQuizId] = useState('')
  const [activeLabSessionId, setActiveLabSessionId] = useState(null)
  const [accessCodes, setAccessCodes] = useState({})
  const [startingId, setStartingId] = useState(null)
  const [answers, setAnswers] = useState({})
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    const loadPage = async () => {
      try {
        setLoading(true)
        const [quizResponse, sessionResponse] = await Promise.all([
          api.get('/student/quizzes'),
          api.get('/student/quiz-sessions'),
        ])
        const available = quizResponse.data.quizzes || []
        setQuizzes(available)
        setLabSessions(sessionResponse.data.sessions || [])

        if (available.length) {
          const firstId = String(
            available.find((item) => String(item.id) === requestedQuizId)?.id || available[0].id
          )
          setSelectedQuizId(firstId)
          const response = await api.get('/student/quiz', {
            params: { quiz_id: firstId },
          })
          setQuiz(response.data.quiz)
        }
      } catch (err) {
        console.error(err)
        setError(err.response?.data?.error || 'Unable to load available quizzes.')
      } finally {
        setLoading(false)
      }
    }
    loadPage()
  }, [requestedQuizId])

  const handleQuizChange = async (event) => {
    const quizId = event.target.value
    setSelectedQuizId(quizId)
    setActiveLabSessionId(null)
    setQuiz(null)
    setAnswers({})
    setResult(null)
    setError('')

    try {
      const response = await api.get('/student/quiz', {
        params: { quiz_id: quizId },
      })
      setQuiz(response.data.quiz)
    } catch (err) {
      setError(err.response?.data?.error || 'Unable to load this quiz.')
    }
  }

  const startLabQuiz = async (labSession) => {
    try {
      setStartingId(labSession.id)
      setError('')
      const response = await api.post(
        `/student/quiz-sessions/${labSession.id}/start`,
        { access_code: accessCodes[labSession.id] || '' }
      )
      setQuiz(response.data.quiz)
      setActiveLabSessionId(response.data.session_id)
      setSelectedQuizId('')
      setAnswers({})
      setResult(null)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (err) {
      setError(err.response?.data?.error || 'Unable to start this lab quiz.')
    } finally {
      setStartingId(null)
    }
  }

  const handleAnswer = (index, option) => {
    setAnswers((current) => ({ ...current, [index]: option }))
    setError('')
  }

  const handleSubmit = async () => {
    const unanswered = quiz.questions.length - Object.keys(answers).length
    if (unanswered > 0 && !window.confirm(
      `${unanswered} question${unanswered === 1 ? ' is' : 's are'} unanswered. Submit anyway?`
    )) return

    try {
      setSubmitting(true)
      setError('')
      const payload = { quiz_id: quiz.id, answers }
      if (activeLabSessionId) payload.quiz_session_id = activeLabSessionId
      const response = await api.post('/student/quiz/submit', payload)
      setResult(response.data)
    } catch (err) {
      setError(err.response?.data?.error || 'Unable to submit this quiz.')
    } finally {
      setSubmitting(false)
    }
  }

  const labPanel = (
    <section className="student-lab-panel">
      <div className="student-lab-heading">
        <div><p>SCHOOL COMPUTER LAB</p><h2>Assigned Lab Quizzes</h2></div>
        <span>{labSessions.length} session{labSessions.length === 1 ? '' : 's'}</span>
      </div>
      {labSessions.length === 0 ? (
        <div className="student-lab-empty">Your teacher has not scheduled a lab quiz for your class.</div>
      ) : (
        <div className="student-lab-list">
          {labSessions.map((item) => (
            <article className="student-lab-card" key={item.id}>
              <div className="student-lab-card-title">
                <div>
                  <span className={`student-lab-state state-${item.state}`}>{item.state}</span>
                  <h3>{item.title}</h3>
                  <p>{item.subject} · {item.class_name}</p>
                </div>
                <div className="student-lab-time">
                  <small>Available</small>
                  <strong>{formatTime(item.starts_at)}</strong>
                  <small>to {formatTime(item.ends_at)}</small>
                </div>
              </div>
              {item.state === 'active' && (
                <div className="student-lab-access">
                  <input
                    aria-label={`Access code for ${item.title}`}
                    maxLength="20"
                    placeholder="Enter access code"
                    value={accessCodes[item.id] || ''}
                    onChange={(event) => setAccessCodes((current) => ({
                      ...current,
                      [item.id]: event.target.value.toUpperCase(),
                    }))}
                  />
                  <button onClick={() => startLabQuiz(item)} disabled={startingId === item.id}>
                    {startingId === item.id ? 'Checking...' : 'Start Quiz'}
                  </button>
                </div>
              )}
              {item.state === 'scheduled' && <p className="student-lab-note">This quiz will open at the scheduled start time.</p>}
              {item.state === 'submitted' && <p className="student-lab-note success">✓ Your submission has been recorded.</p>}
              {['ended', 'closed'].includes(item.state) && <p className="student-lab-note">This session is no longer available.</p>}
            </article>
          ))}
        </div>
      )}
    </section>
  )

  if (loading) {
    return <div className="quiz-state"><div className="quiz-spinner" /><p>Loading quizzes...</p></div>
  }

  if (result) {
    const percentage = Math.round((result.score / result.total) * 100)
    return (
      <div className="quiz-page">
        <section className="result-card">
          <div className="result-icon">{percentage >= 80 ? '🎉' : percentage >= 50 ? '👍' : '📚'}</div>
          <p className="result-label">{activeLabSessionId ? 'LAB QUIZ SUBMITTED' : 'QUIZ COMPLETED'}</p>
          <h1>{activeLabSessionId ? 'Submission recorded' : 'Great job!'}</h1>
          <div className="score-circle"><strong>{percentage}%</strong><span>Score</span></div>
          <h2>{result.score} / {result.total}</h2>
          <p className="result-message">{result.message}</p>
          {result.skipped > 0 && <p className="result-skipped">{result.skipped} unanswered question{result.skipped === 1 ? '' : 's'} recorded</p>}
          <button className="retry-button" onClick={() => window.location.reload()}>
            {activeLabSessionId ? 'Return to Quizzes' : 'Take Quiz Again'}
          </button>
        </section>
      </div>
    )
  }

  if (!quiz) {
    return (
      <div className="quiz-page">
        {labPanel}
        {error && <div className="quiz-error">⚠️ {error}</div>}
        <section className="practice-empty-card">
          <div>📘</div><h2>No practice quiz available</h2>
          <p>Start an active assigned lab quiz above with the code from your teacher.</p>
        </section>
      </div>
    )
  }

  const answeredCount = Object.keys(answers).length
  const progress = Math.round((answeredCount / quiz.questions.length) * 100)

  return (
    <div className="quiz-page">
      {!activeLabSessionId && labPanel}

      {activeLabSessionId ? (
        <div className="active-lab-banner">
          <strong>Controlled lab quiz in progress</strong>
          <span>Submit before your teacher closes the session.</span>
        </div>
      ) : (
        <section className="quiz-selector-card">
          <label htmlFor="student-quiz-select">Choose a practice quiz</label>
          <select id="student-quiz-select" value={selectedQuizId} onChange={handleQuizChange}>
            {quizzes.map((item) => (
              <option value={item.id} key={item.id}>
                {item.title} — {item.subject} ({item.question_count} questions)
              </option>
            ))}
          </select>
        </section>
      )}

      <section className={`quiz-hero ${activeLabSessionId ? 'lab-quiz-hero' : ''}`}>
        <div>
          <p className="quiz-label">{activeLabSessionId ? 'ASSIGNED LAB QUIZ' : 'STUDENT PRACTICE QUIZ'}</p>
          <h1>{quiz.title}</h1>
          <p>Subject: <strong>{quiz.subject}</strong></p>
        </div>
        <div className="quiz-icon">{activeLabSessionId ? '🖥️' : '📝'}</div>
      </section>

      <section className="quiz-progress-card">
        <div><strong>{answeredCount} of {quiz.questions.length} answered</strong><span>{progress}% complete</span></div>
        <div className="quiz-progress-track"><div className="quiz-progress-fill" style={{ width: `${progress}%` }} /></div>
      </section>

      {error && <div className="quiz-error">⚠️ {error}</div>}

      <main className="questions-container">
        {quiz.questions.map((question, index) => (
          <section className="question-card" key={index}>
            <div className="question-number">Question {index + 1}</div>
            <div className="question-metadata">
              <span>{question.topic}</span>
              <span className={`difficulty difficulty-${question.difficulty}`}>
                {question.difficulty === 'unspecified' ? 'Difficulty not set' : question.difficulty}
              </span>
              {question.cognitive_level !== 'unspecified' && <span>{question.cognitive_level.replace('_', ' ')}</span>}
              {question.curriculum_code !== 'unspecified' && <span>{question.curriculum_code}</span>}
            </div>
            <h2>{question.question}</h2>
            <div className="options-list">
              {question.options.map((option) => (
                <label className={`quiz-option ${answers[index] === option ? 'selected' : ''}`} key={option}>
                  <input type="radio" name={`question-${index}`} value={option} checked={answers[index] === option} onChange={() => handleAnswer(index, option)} />
                  <span className="option-letter">{String.fromCharCode(65 + question.options.indexOf(option))}</span>
                  <span>{option}</span>
                  {answers[index] === option && <span className="check-mark">✓</span>}
                </label>
              ))}
            </div>
          </section>
        ))}

        <div className="submit-area">
          <button className="submit-quiz-button" onClick={handleSubmit} disabled={submitting}>
            {submitting ? 'Submitting...' : activeLabSessionId ? 'Submit Lab Quiz →' : 'Submit Quiz →'}
          </button>
          <p>Unanswered questions will be recorded as skipped.</p>
        </div>
      </main>
    </div>
  )
}

export default Quiz
