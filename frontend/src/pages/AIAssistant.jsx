import { useEffect, useState } from 'react'
import api from '../api'
import './AIAssistant.css'

function AIAssistant() {
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [fullAnswer, setFullAnswer] = useState('')
  const [subject, setSubject] = useState('')
  const [loading, setLoading] = useState(false)
  const [typing, setTyping] = useState(false)
  const [error, setError] = useState('')

  // Typing animation
  useEffect(() => {
    if (!fullAnswer) return

    setAnswer('')
    setTyping(true)

    let index = 0

    const interval = setInterval(() => {
      index += 1
      setAnswer(fullAnswer.slice(0, index))

      if (index >= fullAnswer.length) {
        clearInterval(interval)
        setTyping(false)
      }
    }, 18)

    return () => clearInterval(interval)
  }, [fullAnswer])

  const askAI = async (e) => {
    e.preventDefault()

    if (!question.trim() || loading) return

    setLoading(true)
    setTyping(false)
    setError('')
    setAnswer('')
    setFullAnswer('')
    setSubject('')

    try {
      const response = await api.post('/student/ai', {
        question: question.trim(),
      })

      setSubject(response.data.subject || '')
      setFullAnswer(response.data.answer || '')
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
    <div className="ai-page">
      <div className="ai-container">

        {/* Header */}
        <section className="ai-header">
          <div className="ai-avatar">
            🤖
          </div>

          <div>
            <h1>Siksha Sarathi AI</h1>
            <p>Your personal learning assistant</p>
          </div>

          <div className="online-status">
            <span></span>
            Online
          </div>
        </section>

        {/* Introduction */}
        {!answer && !loading && !error && (
          <section className="ai-welcome">
            <div className="welcome-icon">✨</div>

            <h2>How can I help you today?</h2>

            <p>
              Ask me anything about Mathematics, Science, English,
              Nepali or Social Studies.
            </p>

            <div className="suggestions">
              <button
                onClick={() =>
                  setQuestion('Explain Newton’s first law of motion.')
                }
              >
                🔬 Explain a science concept
              </button>

              <button
                onClick={() =>
                  setQuestion('How do I solve a quadratic equation?')
                }
              >
                📐 Help with mathematics
              </button>

              <button
                onClick={() =>
                  setQuestion('Explain this English grammar topic.')
                }
              >
                📖 Help with English
              </button>
            </div>
          </section>
        )}

        {/* Thinking */}
        {loading && (
          <div className="ai-message">
            <div className="message-avatar">🤖</div>

            <div className="thinking-box">
              <span>Thinking</span>
              <div className="thinking-dots">
                <i></i>
                <i></i>
                <i></i>
              </div>
            </div>
          </div>
        )}

        {/* Answer */}
        {answer && (
          <section className="answer-section">

            <div className="ai-message">

              <div className="message-avatar">
                🤖
              </div>

              <div className="answer-content">

                <div className="answer-top">
                  <strong>Siksha Sarathi AI</strong>

                  {subject && (
                    <span className="subject-badge">
                      {subject}
                    </span>
                  )}
                </div>

                <div className="answer-text">
                  {answer}
                  {typing && (
                    <span className="typing-cursor">▋</span>
                  )}
                </div>

              </div>

            </div>

          </section>
        )}

        {/* Error */}
        {error && (
          <div className="ai-error">
            ⚠️ {error}
          </div>
        )}

        {/* Input */}
        <form
          onSubmit={askAI}
          className="ai-input-area"
        >
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask your question..."
            rows="3"
            disabled={loading}
          />

          <div className="input-footer">

            <span>
              {loading
                ? 'AI is preparing your answer...'
                : 'Press Ask AI to get help'}
            </span>

            <button
              type="submit"
              disabled={loading || !question.trim()}
            >
              {loading ? (
                <>
                  <span className="button-spinner"></span>
                  Thinking...
                </>
              ) : (
                <>
                  Ask AI
                  <span>→</span>
                </>
              )}
            </button>

          </div>
        </form>

      </div>
    </div>
  )
}

export default AIAssistant  
