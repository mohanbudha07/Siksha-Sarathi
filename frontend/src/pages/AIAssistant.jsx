import { useEffect, useState } from 'react'
import api from '../api'
import './AIAssistant.css'

function AIAssistant() {
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [fullAnswer, setFullAnswer] = useState('')
  const [subject, setSubject] = useState('')
  const [selectedSubject, setSelectedSubject] = useState('')
  const [availableSubjects, setAvailableSubjects] = useState([])
  const [grounding, setGrounding] = useState(null)
  const [mode, setMode] = useState('')
  const [loading, setLoading] = useState(false)
  const [typing, setTyping] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const loadSubjects = async () => {
      try {
        const response = await api.get('/student/ai/context-options')
        const subjects = response.data?.subjects || []
        const next = subjects.filter(Boolean)
        setAvailableSubjects(next)
      } catch (err) {
        console.error(err)
      }
    }
    loadSubjects()
  }, [])

  useEffect(() => {
    if (availableSubjects.length > 0 && !selectedSubject) {
      setSelectedSubject('')
    }
  }, [availableSubjects, selectedSubject])

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
    setGrounding(null)
    setMode('')

    try {
      const response = await api.post('/student/ai', {
        question: question.trim(),
        subject: selectedSubject || undefined,
      })

      setSubject(response.data.subject || '')
      setMode(response.data.mode || 'offline')
      setFullAnswer(response.data.answer || '')
      setGrounding(response.data.grounding || null)
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
            Ready
          </div>
        </section>

        {/* Introduction */}
        {!answer && !loading && !error && (
          <section className="ai-welcome">
            <div className="welcome-icon">✨</div>

            <h2>How can I help you today?</h2>

            <p>
              Ask about Mathematics, Science, English, Nepali or Social Studies.
              Gemini is used when configured; limited offline help remains available.
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

                  <span className={`assistant-mode ${mode}`}>
                    {mode === 'gemini' ? 'Gemini response' : 'Offline helper'}
                  </span>
                </div>

                <div className="grounding-indicator">
                  {grounding?.status === 'grounded' && 'Grounded in school context'}
                  {grounding?.status === 'partial_grounding' && 'Partly grounded'}
                  {grounding?.status === 'general_only' && 'General tutor response'}
                  {grounding?.status === 'offline' && 'Offline helper'}
                </div>

                {grounding?.sources?.length > 0 && (
                  <div className="grounding-sources">
                    {grounding.sources.map((source, index) => (
                      <span key={`${source.kind}-${index}`} className="source-chip">
                        {source.kind === 'note' ? 'Teacher note' : source.kind === 'recommendation' ? 'Recommendation' : source.kind === 'support_plan' ? 'Teacher plan' : 'General'} · {source.title || source.focus_area || 'Learning source'}
                      </span>
                    ))}
                  </div>
                )}

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
          <div className="subject-picker-wrap">
            <label htmlFor="ai-subject-select">Subject</label>
            <select
              id="ai-subject-select"
              value={selectedSubject}
              onChange={(e) => setSelectedSubject(e.target.value)}
              disabled={loading || availableSubjects.length === 0}
            >
              <option value="">Auto / General</option>
              {availableSubjects.map((subject) => (
                <option key={subject} value={subject}>{subject}</option>
              ))}
            </select>
          </div>

          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask your question..."
            rows="3"
            disabled={loading}
            maxLength={1000}
          />

          <div className="input-footer">

            <span>
              {loading
                ? 'AI is preparing your answer...'
                : `${question.length}/1000 characters`}
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
