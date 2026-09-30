import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import api from '../api'
import './QuizHistory.css'

function TeacherQuizAttempts() {
  const { quizId, resultId } = useParams()
  const navigate = useNavigate()
  const [quiz, setQuiz] = useState(null)
  const [attempts, setAttempts] = useState([])
  const [detail, setDetail] = useState(null)
  const [pagination, setPagination] = useState({ page: 1, page_size: 10, total: 0, total_pages: 0 })
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [pageError, setPageError] = useState('')

  useEffect(() => {
    let active = true
    const load = async () => {
      try {
        setLoading(true)
        setPageError('')
        if (resultId) {
          const response = await api.get(`/teacher/quizzes/${quizId}/attempts/${resultId}`)
          if (active) {
            setDetail(response.data)
            setQuiz({ title: response.data.attempt.quiz_title, subject: response.data.attempt.subject })
          }
        } else {
          const response = await api.get(`/teacher/quizzes/${quizId}/attempts`, {
            params: { page: pagination.page, page_size: pagination.page_size, search },
          })
          if (active) {
            setAttempts(response.data.attempts || [])
            setPagination(response.data.pagination)
            setQuiz(response.data.quiz)
            setDetail(null)
          }
        }
      } catch (error) {
        if (active) setPageError(error.response?.data?.error || 'Unable to load Quiz attempts.')
      } finally {
        if (active) setLoading(false)
      }
    }
    load()
    return () => { active = false }
  }, [quizId, resultId, pagination.page, pagination.page_size, search])

  const submitSearch = (event) => {
    event.preventDefault()
    setPagination((current) => ({ ...current, page: 1 }))
    setSearch(searchInput.trim())
  }

  if (resultId) {
    const attempt = detail?.attempt
    return <main className="quiz-history-page teacher-attempt-page">
      <header className="quiz-history-heading"><div><p>QUIZ ATTEMPTS</p><h1>{attempt?.student_name || 'Attempt Details'}</h1><span>{quiz?.title || 'Loading Quiz…'}</span></div><button type="button" className="history-secondary-button" onClick={() => navigate(`/teacher/quizzes/${quizId}/attempts`)}>← Back to Attempts</button></header>
      {pageError && <p className="quiz-history-error" role="alert">{pageError}</p>}
      {loading ? <p className="quiz-history-state">Loading attempt…</p> : attempt && <>
        <section className="teacher-attempt-summary">
          <div><span>Quiz</span><strong>{attempt.quiz_title}</strong></div>
          <div><span>Student</span><strong>{attempt.student_name}</strong><small>{attempt.student_email}</small></div>
          <div><span>Subject</span><strong>{attempt.subject}</strong></div>
          <div><span>Score</span><strong>{attempt.score} / {attempt.total_questions}</strong></div>
          <div><span>Correct</span><strong>{attempt.correct_count}</strong></div>
          <div><span>Wrong</span><strong>{attempt.wrong_count}</strong></div>
          <div><span>Skipped</span><strong>{attempt.skipped_count}</strong></div>
          <div><span>Percentage</span><strong>{attempt.percentage}%</strong></div>
          <div><span>Attempt type</span><strong>{attempt.attempt_type}</strong></div>
          <div><span>Submitted NPT</span><strong>{attempt.submitted_at}</strong></div>
        </section>
        <section className="teacher-attempt-answers">
          <h2>Answers</h2>
          {detail.answers.map((answer) => {
            const status = answer.is_skipped ? 'Skipped' : answer.is_correct ? 'Correct' : 'Incorrect'
            return <article key={answer.question_index}>
              <header><h3>Question {answer.question_index + 1}</h3><span className={`answer-status ${status.toLowerCase()}`}>{status}</span></header>
              <p className="attempt-question-text">{answer.question_text}</p>
              <div className="attempt-answer-grid">
                <div><span>Student answer</span><strong>{answer.is_skipped || answer.selected_answer == null ? 'No answer' : answer.selected_answer}</strong></div>
                <div><span>Correct answer</span><strong>{answer.correct_answer}</strong></div>
                <div><span>Topic</span><strong>{answer.topic}</strong></div>
                <div><span>Difficulty</span><strong>{answer.difficulty}</strong></div>
              </div>
            </article>
          })}
        </section>
      </>}
    </main>
  }

  return <main className="quiz-history-page teacher-attempt-page">
    <header className="quiz-history-heading"><div><p>QUIZ ATTEMPTS</p><h1>{quiz?.title || 'Quiz Attempts'}</h1><span>{quiz?.subject || ''}</span></div><button type="button" className="history-secondary-button" onClick={() => navigate('/teacher/quizzes')}>← Back to Quizzes</button></header>
    <form className="teacher-attempt-search" onSubmit={submitSearch}><input value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Search Student name or email" aria-label="Search Student name or email" /><button type="submit">Search</button></form>
    {pageError && <p className="quiz-history-error" role="alert">{pageError}</p>}
    {loading ? <p className="quiz-history-state">Loading attempts…</p> : attempts.length === 0 ? <p className="quiz-history-state">No Students have attempted this Quiz yet.</p> : <>
      <div className="teacher-attempt-list">
        {attempts.map((attempt) => <article className="teacher-attempt-card" key={attempt.attempt_id}>
          <div className="teacher-attempt-card-heading"><div><h2>{attempt.student_name}</h2><span>{attempt.student_email}</span></div><span className="attempt-type-badge">{attempt.attempt_type}</span></div>
          <dl>
            <div><dt>Score</dt><dd>{attempt.score} / {attempt.total_questions}</dd></div>
            <div><dt>Correct</dt><dd>{attempt.correct_count}</dd></div>
            <div><dt>Wrong</dt><dd>{attempt.wrong_count}</dd></div>
            <div><dt>Skipped</dt><dd>{attempt.skipped_count}</dd></div>
            <div><dt>Percentage</dt><dd>{attempt.percentage}%</dd></div>
            <div><dt>Submitted NPT</dt><dd>{attempt.submitted_at}</dd></div>
          </dl>
          <button type="button" className="history-primary-button" onClick={() => navigate(`/teacher/quizzes/${quizId}/attempts/${attempt.attempt_id}`)}>View Details</button>
        </article>)}
      </div>
      <footer className="quiz-history-pagination">
        <label>Rows per page<select value={pagination.page_size} onChange={(event) => setPagination((current) => ({ ...current, page_size: Number(event.target.value), page: 1 }))}>{[10, 25, 50].map((size) => <option key={size}>{size}</option>)}</select></label>
        <div><button type="button" disabled={pagination.page <= 1} onClick={() => setPagination((current) => ({ ...current, page: current.page - 1 }))}>← Previous</button><span>Page {pagination.page} of {pagination.total_pages}</span><button type="button" disabled={pagination.page >= pagination.total_pages} onClick={() => setPagination((current) => ({ ...current, page: current.page + 1 }))}>Next →</button></div>
      </footer>
    </>}
  </main>
}

export default TeacherQuizAttempts