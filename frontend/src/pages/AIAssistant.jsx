import { useState } from 'react'
import api from '../api'

function AIAssistant() {
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [subject, setSubject] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const askAI = async (e) => {
    e.preventDefault()

    if (!question.trim()) {
      return
    }

    setLoading(true)
    setError('')
    setAnswer('')
    setSubject('')

    try {
      const response = await api.post('/student/ai', {
        question: question.trim(),
      })

      setAnswer(response.data.answer)
      setSubject(response.data.subject)
    } catch (err) {
      console.error(err)

      if (err.response?.data?.error) {
        setError(err.response.data.error)
      } else {
        setError('Unable to connect to the AI Assistant.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={styles.page}>
      <div style={styles.container}>
        <div style={styles.header}>
          <h1>Siksha Sarathi AI Assistant</h1>
          <p>
            Ask questions and get help with your secondary-level
            subjects.
          </p>
        </div>

        <form onSubmit={askAI} style={styles.form}>
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask your question..."
            rows="5"
            style={styles.textarea}
          />

          <button
            type="submit"
            disabled={loading || !question.trim()}
            style={styles.button}
          >
            {loading ? 'Thinking...' : 'Ask AI'}
          </button>
        </form>

        {error && (
          <div style={styles.error}>
            {error}
          </div>
        )}

        {answer && (
          <div style={styles.answerBox}>
            {subject && (
              <div style={styles.subject}>
                Subject: {subject}
              </div>
            )}

            <h2>AI Assistant</h2>

            <p style={styles.answer}>
              {answer}
            </p>
          </div>
        )}

        <button
          onClick={() => {
            window.location.href = '/student/dashboard'
          }}
          style={styles.backButton}
        >
          ← Back to Dashboard
        </button>
      </div>
    </div>
  )
}

const styles = {
  page: {
    minHeight: '100vh',
    background: '#f4f7fb',
    padding: '40px 20px',
    boxSizing: 'border-box',
  },

  container: {
    maxWidth: '850px',
    margin: '0 auto',
  },

  header: {
    background: 'white',
    padding: '30px',
    borderRadius: '12px',
    marginBottom: '20px',
    boxShadow: '0 2px 10px rgba(0,0,0,0.08)',
  },

  form: {
    background: 'white',
    padding: '25px',
    borderRadius: '12px',
    boxShadow: '0 2px 10px rgba(0,0,0,0.08)',
  },

  textarea: {
    width: '100%',
    boxSizing: 'border-box',
    padding: '15px',
    borderRadius: '8px',
    border: '1px solid #ccc',
    fontSize: '16px',
    resize: 'vertical',
    marginBottom: '15px',
  },

  button: {
    padding: '12px 24px',
    border: 'none',
    borderRadius: '8px',
    background: '#2563eb',
    color: 'white',
    fontSize: '16px',
    cursor: 'pointer',
  },

  error: {
    marginTop: '20px',
    padding: '15px',
    background: '#fee2e2',
    color: '#991b1b',
    borderRadius: '8px',
  },

  answerBox: {
    marginTop: '20px',
    background: 'white',
    padding: '25px',
    borderRadius: '12px',
    boxShadow: '0 2px 10px rgba(0,0,0,0.08)',
  },

  subject: {
    fontWeight: 'bold',
    marginBottom: '15px',
  },

  answer: {
    fontSize: '17px',
    lineHeight: '1.7',
  },

  backButton: {
    marginTop: '20px',
    padding: '10px 18px',
    border: '1px solid #ccc',
    borderRadius: '8px',
    background: 'white',
    cursor: 'pointer',
  },
}

export default AIAssistant
