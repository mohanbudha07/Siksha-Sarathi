import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../api'
import './StudentPracticePlan.css'

function StudentPracticePlan() {
  const [plan, setPlan] = useState(null)
  const [teacherPlans, setTeacherPlans] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const recommendations = plan?.recommendations || []

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
        <p>Review observed learning evidence, choose a next step, then check your progress.</p>
      </section>

      {loading && <p className="practice-plan-state">Preparing your plan...</p>}
      {error && <p className="practice-plan-state practice-plan-error" role="alert">{error}</p>}
      {!loading && !error && plan && (
        <>
          <section className="practice-plan-message">
            <p>{plan.message}</p>
            <small>Topic review suggestions use at least three observations across two distinct tagged questions and accuracy below 60%.</small>
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

          {recommendations.length === 0 ? (
            <section className="practice-plan-empty">
              <h2>Keep building your learning record</h2>
              <p>Your teacher's notes and practice quizzes are available even when there is not enough evidence for a specific next step.</p>
              <div>
                <Link to="/student/notes">Read learning notes</Link>
                <Link to="/student/quiz">Browse practice quizzes</Link>
              </div>
            </section>
          ) : (
            <div className="practice-plan-list">
              <h2 className="practice-plan-recommendations-heading">Recommended next steps</h2>
              {recommendations.map((item, index) => (
                <article key={`${item.kind}-${item.subject || 'all'}-${item.topic || item.title}`} className="practice-plan-card">
                  <div className="practice-plan-card-heading">
                    <div>
                      <span className="practice-plan-rank">NEXT STEP {index + 1}{item.subject ? ` · ${item.subject}` : ''}</span>
                      <h2>{item.title}</h2>
                    </div>
                    {item.evidence?.accuracy_percent !== undefined && (
                      <span className="practice-plan-score">
                        {item.evidence.correct_answers}/{item.evidence.total_questions} correct
                      </span>
                    )}
                  </div>
                  <p className="practice-plan-evidence">{item.reason}</p>
                  <p>{item.next_step}</p>
                  <div className="practice-plan-resources">
                    <div>
                      <h3>Read</h3>
                      {item.resources?.notes?.length ? item.resources.notes.map((note) => (
                        <Link key={note.id} to={`/student/notes?${new URLSearchParams({ subject: item.subject, search: item.topic })}`}>
                          {note.title} · {note.chapter} →
                        </Link>
                      )) : <>
                        <p className="practice-plan-evidence">{item.resources?.note_message || 'No matching note is currently available.'}</p>
                        <Link to={`/student/notes?${new URLSearchParams(item.subject ? { subject: item.subject } : {})}`}>
                          {item.subject ? `Browse ${item.subject} notes →` : 'Browse learning notes →'}
                        </Link>
                      </>}
                    </div>
                    <div>
                      <h3>Practice</h3>
                      {item.resources?.quizzes?.length ? item.resources.quizzes.map((quiz) => (
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
