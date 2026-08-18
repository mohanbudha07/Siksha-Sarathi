import { useEffect, useState } from 'react'
import api from '../api'
import './Quiz.css'

function Quiz() {
  const [quiz, setQuiz] = useState(null)
  const [answers, setAnswers] = useState({})
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  useEffect(() => {
    api
      .get('/student/quiz')
      .then((response) => {
        setQuiz(response.data.quiz)
      })
      .catch((error) => {
        console.error(error)
        setError(
          `API error: ${error.response?.status || error.message}`
        )
      })
  }, [])

  const handleSubmit = () => {
    if (Object.keys(answers).length !== quiz.questions.length) {
      setError('Please answer all questions before submitting the quiz.')
      return
    }

    setError('')

    api
      .post('/student/quiz/submit', {
        quiz_id: quiz.id,
        answers: answers,
      })
      .then((response) => {
        setResult(response.data)
      })
      .catch((error) => {
        console.error(error)
        setError(
          `Submission error: ${
            error.response?.status || error.message
          }`
        )
      })
  }

  if (error) {
    return <p>{error}</p>
  }

  if (!quiz) {
    return <p>Loading quiz...</p>
  }

  if (result) {
    return (
      <div>
        <h1>Quiz Result</h1>
        <h2>
          Score: {result.score} / {result.total}
        </h2>
        <p>{result.message}</p>
      </div>
    )
  }

  return (
    <div className="quiz-page">
      <header className="quiz-header">
        <h1>Siksha Sarathi</h1>
        <p>Student Quiz</p>
      </header>

      <main className="quiz-content">
        <div className="quiz-info">
          <h2>{quiz.title}</h2>
          <p>Subject: {quiz.subject}</p>
        </div>

        {quiz.questions.map((question, index) => (
          <div className="question-card" key={index}>
            <h3>
              {index + 1}. {question.question}
            </h3>

            {question.options.map((option) => (
              <label className="option" key={option}>
                <input
                  type="radio"
                  name={`question-${index}`}
                  value={option}
                  checked={answers[index] === option}
                  onChange={() =>
                    setAnswers({
                      ...answers,
                      [index]: option,
                    })
                  }
                />
                {option}
              </label>
            ))}
          </div>
        ))}

        <button
          className="submit-button"
          onClick={handleSubmit}
        >
          Submit Quiz
        </button>
      </main>
    </div>
  )
}

export default Quiz
