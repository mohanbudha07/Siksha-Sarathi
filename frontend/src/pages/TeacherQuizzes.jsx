import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'
import './TeacherQuizzes.css'

function TeacherQuizzes() {
  const navigate = useNavigate()
  const [quizzes, setQuizzes] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [deletingId, setDeletingId] = useState(null)

  const loadQuizzes = async () => {
    try {
      setLoading(true)
      setError('')
      const response = await api.get('/teacher/quizzes')
      setQuizzes(response.data.quizzes || [])
    } catch (err) {
      console.error('Load teacher quizzes error:', err)
      setError(err.response?.data?.error || 'Unable to load your quizzes.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadQuizzes()
  }, [])

  const handleDelete = async (quiz) => {
    const confirmed = window.confirm(
      `Delete “${quiz.title}”? This is allowed only when it has no student attempts.`
    )
    if (!confirmed) return

    try {
      setDeletingId(quiz.id)
      setError('')
      await api.delete(`/teacher/quizzes/${quiz.id}`)
      setQuizzes((current) => current.filter((item) => item.id !== quiz.id))
    } catch (err) {
      console.error('Delete quiz error:', err)
      setError(err.response?.data?.error || 'Unable to delete this quiz.')
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div className="teacher-quizzes-page">
      <section className="quiz-management-hero">
        <div>
          <p className="quiz-management-label">TEACHING MATERIALS</p>
          <h1>Manage Quizzes</h1>
          <p>
            Create structured questions with topics and difficulty levels for
            student learning analysis.
          </p>
        </div>
        <button onClick={() => navigate('/teacher/quizzes/new')}>
          + Create Quiz
        </button>
      </section>

      {error && <div className="quiz-management-error">⚠️ {error}</div>}

      {loading && (
        <div className="quiz-management-state">
          <div className="quiz-management-spinner" />
          <p>Loading your quizzes...</p>
        </div>
      )}

      {!loading && quizzes.length === 0 && (
        <div className="quiz-management-state">
          <div className="quiz-empty-icon">📝</div>
          <h2>No teacher-created quizzes yet</h2>
          <p>
            Existing legacy quizzes remain available to students but are not
            assigned to any teacher. Create your first owned quiz here.
          </p>
          <button onClick={() => navigate('/teacher/quizzes/new')}>
            Create First Quiz
          </button>
        </div>
      )}

      {!loading && quizzes.length > 0 && (
        <section className="teacher-quiz-grid">
          {quizzes.map((quiz) => (
            <article className="teacher-quiz-card" key={quiz.id}>
              <div className="teacher-quiz-card-top">
                <span className="teacher-quiz-subject">{quiz.subject}</span>
                <span className={quiz.is_published ? 'status-published' : 'status-draft'}>
                  {quiz.is_published ? 'Published' : 'Draft'}
                </span>
              </div>

              <h2>{quiz.title}</h2>

              <div className="teacher-quiz-metrics">
                <span><strong>{quiz.question_count}</strong> questions</span>
                <span><strong>{quiz.attempt_count}</strong> attempts</span>
              </div>

              <div className="teacher-quiz-actions">
                <button
                  className="quiz-edit-button"
                  onClick={() => navigate(`/teacher/quizzes/${quiz.id}/edit`)}
                >
                  Edit
                </button>
                <button
                  className="quiz-delete-button"
                  onClick={() => handleDelete(quiz)}
                  disabled={deletingId === quiz.id}
                >
                  {deletingId === quiz.id ? 'Deleting...' : 'Delete'}
                </button>
              </div>
            </article>
          ))}
        </section>
      )}
    </div>
  )
}

export default TeacherQuizzes
