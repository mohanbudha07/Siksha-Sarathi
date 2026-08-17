import { useEffect, useState } from 'react'
import axios from 'axios'

function Quiz() {
  const [quiz, setQuiz] = useState(null)
  const [answers, setAnswers] = useState({})
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  useEffect(() => {
    axios
      .get('/api/student/quiz', {
        withCredentials: true,
      })
      .then((response) => {
        setQuiz(response.data.quiz)
      })
      .catch((error) => {
        console.error(error)
        setError(`API error: ${error.response?.status || error.message}`)
      })
  }, [])

  const handleSubmit = () => {
    axios
      .post(
        '/api/student/quiz/submit',
        {
          quiz_id: quiz.id,
          answers: answers,
        },
        {
          withCredentials: true,
        }
      )
      .then((response) => {
        setResult(response.data)
      })
      .catch((error) => {
        console.error(error)
        setError(`Submission error: ${error.response?.status || error.message}`)
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
    <div>
      <h1>{quiz.title}</h1>
      <p>Subject: {quiz.subject}</p>

      {quiz.questions.map((question, index) => (
        <div key={index}>
          <h3>
            {index + 1}. {question.question}
          </h3>

          {question.options.map((option) => (
            <label key={option}>
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

      <button onClick={handleSubmit}>
        Submit Quiz
      </button>
    </div>
  )
}

export default Quiz
