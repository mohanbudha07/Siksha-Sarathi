import { useEffect, useState } from 'react'
import api from '../api'
import './Quiz.css'

function Quiz() {
  const [quiz, setQuiz] = useState(null)
  const [answers, setAnswers] = useState({})
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    api
      .get('/student/quiz')
      .then((response) => {
        setQuiz(response.data.quiz)
      })
      .catch((error) => {
        console.error(error)
        setError(`API error: ${error.response?.status || error.message}`)
      })
  }, [])

  const handleAnswer = (index, option) => {
    setAnswers({
      ...answers,
      [index]: option,
    })

    setError('')
  }

  const handleSubmit = async () => {
    if (Object.keys(answers).length !== quiz.questions.length) {
      setError('Please answer all questions before submitting the quiz.')
      return
    }

    setSubmitting(true)
    setError('')

    try {
      const response = await api.post('/student/quiz/submit', {
        quiz_id: quiz.id,
        answers,
      })

      setResult(response.data)
    } catch (error) {
      console.error(error)
      setError(
        `Submission error: ${error.response?.status || error.message}`
      )
    } finally {
      setSubmitting(false)
    }
  }

  if (error && !quiz) {
    return <div className="quiz-state error-state">{error}</div>
  }

  if (!quiz) {
    return (
      <div className="quiz-state">
        <div className="quiz-spinner" />
        <p>Loading quiz...</p>
      </div>
    )
  }

  if (result) {
    const percentage = Math.round(
      (result.score / result.total) * 100
    )

    return (
      <div className="quiz-page">
        <section className="result-card">
          <div className="result-icon">
            {percentage >= 80 ? '🎉' : percentage >= 50 ? '👍' : '📚'}
          </div>

          <p className="result-label">QUIZ COMPLETED</p>

          <h1>Great job!</h1>

          <div className="score-circle">
            <strong>{percentage}%</strong>
            <span>Score</span>
          </div>

          <h2>
            {result.score} / {result.total}
          </h2>

          <p className="result-message">
            {result.message}
          </p>

          <button
            className="retry-button"
            onClick={() => window.location.reload()}
          >
            Take Quiz Again
          </button>
        </section>
      </div>
    )
  }

  const answeredCount = Object.keys(answers).length
  const progress = Math.round(
    (answeredCount / quiz.questions.length) * 100
  )

  return (
    <div className="quiz-page">

      <section className="quiz-hero">
        <div>
          <p className="quiz-label">STUDENT QUIZ</p>
          <h1>{quiz.title}</h1>
          <p>
            Subject: <strong>{quiz.subject}</strong>
          </p>
        </div>

        <div className="quiz-icon">📝</div>
      </section>

      <section className="quiz-progress-card">
        <div>
          <strong>
            {answeredCount} of {quiz.questions.length} answered
          </strong>
          <span>{progress}% complete</span>
        </div>

        <div className="quiz-progress-track">
          <div
            className="quiz-progress-fill"
            style={{ width: `${progress}%` }}
          />
        </div>
      </section>

      {error && (
        <div className="quiz-error">
          ⚠️ {error}
        </div>
      )}

      <main className="questions-container">

        {quiz.questions.map((question, index) => (
          <section className="question-card" key={index}>

            <div className="question-number">
              Question {index + 1}
            </div>

            <h2>{question.question}</h2>

            <div className="options-list">
              {question.options.map((option) => (
                <label
                  className={`quiz-option ${
                    answers[index] === option ? 'selected' : ''
                  }`}
                  key={option}
                >
                  <input
                    type="radio"
                    name={`question-${index}`}
                    value={option}
                    checked={answers[index] === option}
                    onChange={() =>
                      handleAnswer(index, option)
                    }
                  />

                  <span className="option-letter">
                    {String.fromCharCode(
                      65 + question.options.indexOf(option)
                    )}
                  </span>

                  <span>{option}</span>

                  {answers[index] === option && (
                    <span className="check-mark">✓</span>
                  )}
                </label>
              ))}
            </div>
          </section>
        ))}

        <div className="submit-area">
          <button
            className="submit-quiz-button"
            onClick={handleSubmit}
            disabled={submitting}
          >
            {submitting ? 'Submitting...' : 'Submit Quiz →'}
          </button>

          <p>
            Make sure you have answered every question before submitting.
          </p>
        </div>

      </main>
    </div>
  )
}

export default Quiz
