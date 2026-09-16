import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../api'
import './StudentPracticePlan.css'

function StudentPracticePlan() {
  const [plan, setPlan] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    api.get('/student/practice-plan')
      .then((response) => setPlan(response.data))
      .catch((err) => {
        console.error('Practice plan error:', err)
        setError(err.response?.data?.error || 'Unable to load your practice plan.')
      })
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="practice-plan-page">
      <section className="practice-plan-hero">
        <span>YOUR LEARNING PATH</span>
        <h1>My Practice Plan</h1>
        <p>Pick one topic, read a helpful note, practise, then check your progress. Your plan uses your ten most recent quiz attempts.</p>
      </section>

      {loading && <p className="practice-plan-state">Preparing your plan...</p>}
      {error && <p className="practice-plan-state practice-plan-error" role="alert">{error}</p>}
      {!loading && !error && plan && (
        <>
          <section className="practice-plan-message">
            <p>{plan.message}</p>
            <small>Topic suggestions appear after at least three answers across two different tagged questions in a topic.</small>
          </section>

          {plan.topics.length === 0 ? (
            <section className="practice-plan-empty">
              <h2>Keep building your learning record</h2>
              <p>Your teacher's notes and practice quizzes are available even when there is not enough quiz evidence for a specific topic.</p>
              <div>
                <Link to="/student/notes">Read learning notes</Link>
                <Link to="/student/quiz">Browse practice quizzes</Link>
              </div>
            </section>
          ) : (
            <div className="practice-plan-list">
              {plan.topics.map((item, index) => (
                <article key={`${item.subject}-${item.topic}`} className="practice-plan-card">
                  <div className="practice-plan-card-heading">
                    <div>
                      <span className="practice-plan-rank">TOPIC {index + 1} · {item.subject}</span>
                      <h2>{item.topic}</h2>
                    </div>
                    <span className="practice-plan-score">{item.correct_answers}/{item.total_questions} correct</span>
                  </div>
                  <p className="practice-plan-evidence">{item.skipped_answers} unanswered · Based on recent quiz activity</p>
                  <ol>
                    {item.steps.map((step) => <li key={step}>{step}</li>)}
                  </ol>
                  <div className="practice-plan-resources">
                    <div>
                      <h3>Read</h3>
                      {item.notes.length ? item.notes.map((note) => (
                        <Link key={note.id} to={`/student/notes?${new URLSearchParams({ subject: item.subject, search: item.topic })}`}>
                          {note.title} · {note.chapter} →
                        </Link>
                      )) : <Link to={`/student/notes?${new URLSearchParams({ subject: item.subject })}`}>Browse {item.subject} notes →</Link>}
                    </div>
                    <div>
                      <h3>Practice</h3>
                      {item.quizzes.length ? item.quizzes.map((quiz) => (
                        <Link key={quiz.id} to={`/student/quiz?quiz_id=${quiz.id}`}>
                          {quiz.title} →
                        </Link>
                      )) : <Link to="/student/quiz">Browse practice quizzes →</Link>}
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default StudentPracticePlan
