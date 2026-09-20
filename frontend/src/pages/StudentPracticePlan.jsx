import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../api'
import './StudentPracticePlan.css'

function StudentPracticePlan() {
  const [plan, setPlan] = useState(null)
  const [teacherPlans, setTeacherPlans] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([
      api.get('/student/practice-plan'),
      api.get('/student/interventions'),
    ])
      .then(([practiceResponse, interventionResponse]) => {
        setPlan(practiceResponse.data)
        setTeacherPlans(interventionResponse.data.interventions || [])
      })
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

          <section className="student-support-plans">
            <div className="student-support-heading">
              <div><span>TEACHER GUIDANCE</span><h2>My Support Plans</h2></div>
              <strong>{teacherPlans.filter((item) => item.status !== 'completed').length} active</strong>
            </div>
            {teacherPlans.length === 0 ? <p className="practice-plan-evidence">Your teacher has not assigned a support plan yet.</p> : <div className="student-support-list">
              {teacherPlans.map((item) => <article key={item.id}>
                <div><span>{item.subject} · {String(item.status).replaceAll('_', ' ')}</span><h3>{item.focus_area}</h3></div>
                <p>{item.action_plan}</p>
                {item.success_criteria && <p><strong>Goal:</strong> {item.success_criteria}</p>}
                <small>Review date: {item.review_date || 'To be decided'} · Teacher: {item.teacher_name}</small>
                {item.effectiveness?.available && <div className="student-plan-change">
                  <strong>Progress since plan started</strong>
                  {[['quiz_accuracy', 'Quiz'], ['paper_average', 'Paper'], ['attendance_percent', 'Attendance']].map(([key, label]) => {
                    const delta = item.effectiveness.delta[key]
                    return <span key={key} className={delta > 0 ? 'positive' : delta < 0 ? 'negative' : ''}>{label}: {delta === null ? 'not comparable yet' : `${delta > 0 ? '+' : ''}${delta} points`}</span>
                  })}
                  <small>Change over time does not prove the plan caused the result.</small>
                </div>}
                {item.outcome_note && <blockquote>{item.outcome_note}</blockquote>}
              </article>)}
            </div>}
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
