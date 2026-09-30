import { useEffect, useState } from 'react'
import api from '../api'
import { useToast } from '../components/feedback/useToast'
import './QuizHistory.css'

function StudentQuizHistory() {
  const { toast } = useToast()
  const [attempts, setAttempts] = useState([])
  const [pagination, setPagination] = useState({ page: 1, page_size: 10, total: 0, total_pages: 0 })
  const [loading, setLoading] = useState(true)
  const [pageError, setPageError] = useState('')
  const [detail, setDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)

  useEffect(() => {
    let active = true
    const load = async () => {
      try {
        setLoading(true)
        const response = await api.get('/student/quiz-history', {
          params: { page: pagination.page, page_size: pagination.page_size },
        })
        if (!active) return
        setAttempts(response.data.attempts || [])
        setPagination(response.data.pagination)
      } catch (error) {
        if (active) setPageError(error.response?.data?.error || 'Unable to load Quiz History.')
      } finally {
        if (active) setLoading(false)
      }
    }
    load()
    return () => { active = false }
  }, [pagination.page, pagination.page_size])

  const openDetail = async (resultId) => {
    try {
      setDetailLoading(true)
      const response = await api.get(`/student/quiz-history/${resultId}`)
      setDetail(response.data)
    } catch (error) {
      toast.error(error.response?.data?.error || 'Unable to load this Quiz attempt.')
    } finally {
      setDetailLoading(false)
    }
  }

  const attempt = detail?.attempt

  return (
    <main className="quiz-history-page">
      <header className="quiz-history-heading"><div><p>YOUR LEARNING</p><h1>Quiz History</h1><span>Review your completed Practice and Lab Quizzes.</span></div></header>
      {pageError && <p className="quiz-history-error" role="alert">{pageError}</p>}
      {loading ? <p className="quiz-history-state">Loading Quiz History…</p> : attempts.length === 0 ? <p className="quiz-history-state">You have not completed any Quizzes yet.</p> : <>
        <div className="student-history-list">
          {attempts.map((item) => <article className="student-history-card" key={item.result_id}>
            <div className="student-history-title"><h2>{item.quiz_title}</h2><span>{item.attempt_type}</span></div>
            <dl>
              <div><dt>Subject</dt><dd>{item.subject || '—'}</dd></div>
              <div><dt>Score</dt><dd>{item.score} / {item.total_questions}</dd></div>
              <div><dt>Correct</dt><dd>{item.correct_count}</dd></div>
              <div><dt>Wrong</dt><dd>{item.wrong_count}</dd></div>
              <div><dt>Skipped</dt><dd>{item.skipped_count}</dd></div>
              <div><dt>Percentage</dt><dd>{item.percentage}%</dd></div>
              <div className="history-submitted"><dt>Submitted</dt><dd>{item.submitted_at || '—'}</dd></div>
            </dl>
            <button type="button" className="history-primary-button" onClick={() => openDetail(item.result_id)}>View Details</button>
          </article>)}
        </div>
        <footer className="quiz-history-pagination">
          <label>Rows per page<select value={pagination.page_size} onChange={(event) => setPagination((current) => ({ ...current, page_size: Number(event.target.value), page: 1 }))}>{[10, 25, 50].map((size) => <option key={size}>{size}</option>)}</select></label>
          <div><button type="button" disabled={pagination.page <= 1} onClick={() => setPagination((current) => ({ ...current, page: current.page - 1 }))}>← Previous</button><span>Page {pagination.page} of {pagination.total_pages}</span><button type="button" disabled={pagination.page >= pagination.total_pages} onClick={() => setPagination((current) => ({ ...current, page: current.page + 1 }))}>Next →</button></div>
        </footer>
      </>}

      {(detail || detailLoading) && <div className="history-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !detailLoading) setDetail(null) }}>
        <section className="history-dialog" role="dialog" aria-modal="true" aria-labelledby="student-attempt-title">
          <header><h2 id="student-attempt-title">{detailLoading ? 'Loading attempt…' : attempt?.quiz_title}</h2><button type="button" aria-label="Close" disabled={detailLoading} onClick={() => setDetail(null)}>×</button></header>
          {attempt && <>
            <p className="history-subject-name">{attempt.subject} · {attempt.attempt_type} · {attempt.submitted_at}</p>
            <div className="history-summary"><strong>Score: {attempt.score} / {attempt.total_questions}</strong><span>Correct: {attempt.correct_count}</span><span>Wrong: {attempt.wrong_count}</span><span>Skipped: {attempt.skipped_count}</span><span>Percentage: {attempt.percentage}%</span></div>
            <div className="history-answer-list">
              {detail.answers.map((answer) => {
                const status = answer.is_skipped ? 'Skipped' : answer.is_correct ? 'Correct' : 'Incorrect'
                return <article key={answer.question_index}>
                  <div className="history-answer-heading"><h3>Question {answer.question_index + 1}</h3><span className={`answer-status ${status.toLowerCase()}`}>{status}</span></div>
                  <p>{answer.question_text}</p>
                  <small>{answer.is_skipped || answer.selected_answer == null ? 'No answer' : `Student answer: ${answer.selected_answer}`}</small>
                </article>
              })}
            </div>
          </>}
          {!detailLoading && <footer><button type="button" className="history-primary-button" onClick={() => setDetail(null)}>Close</button></footer>}
        </section>
      </div>}
    </main>
  )
}

export default StudentQuizHistory