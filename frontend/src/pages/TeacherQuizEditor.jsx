import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import api from '../api'
import './TeacherQuizEditor.css'

const emptyQuestion = () => ({
  question: '',
  topic: '',
  difficulty: 'easy',
  options: ['', '', '', ''],
  correctOptionIndex: 0,
  explanation: '',
})

function TeacherQuizEditor() {
  const { quizId } = useParams()
  const navigate = useNavigate()
  const editing = Boolean(quizId)
  const [form, setForm] = useState({
    title: '',
    subject: '',
    questions: [emptyQuestion()],
  })
  const [loading, setLoading] = useState(editing)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!editing) return

    api
      .get(`/teacher/quizzes/${quizId}`)
      .then((response) => {
        const quiz = response.data.quiz
        setForm({
          title: quiz.title || '',
          subject: quiz.subject || '',
          questions: quiz.questions.map((question) => ({
            ...question,
            options: question.options || ['', ''],
            correctOptionIndex: Math.max(
              0,
              (question.options || []).indexOf(question.answer)
            ),
            explanation: question.explanation || '',
          })),
          is_published: Boolean(quiz.is_published),
        })
      })
      .catch((err) => {
        console.error('Load quiz error:', err)
        setError(err.response?.data?.error || 'Unable to load this quiz.')
      })
      .finally(() => setLoading(false))
  }, [editing, quizId])

  const updateQuestion = (questionIndex, field, value) => {
    setForm((current) => ({
      ...current,
      questions: current.questions.map((question, index) =>
        index === questionIndex ? { ...question, [field]: value } : question
      ),
    }))
  }

  const updateOption = (questionIndex, optionIndex, value) => {
    setForm((current) => ({
      ...current,
      questions: current.questions.map((question, index) => {
        if (index !== questionIndex) return question
        const options = [...question.options]
        options[optionIndex] = value
        return { ...question, options }
      }),
    }))
  }

  const addQuestion = () => {
    setForm((current) => ({
      ...current,
      questions: [...current.questions, emptyQuestion()],
    }))
  }

  const removeQuestion = (questionIndex) => {
    if (form.questions.length === 1) return
    setForm((current) => ({
      ...current,
      questions: current.questions.filter((_, index) => index !== questionIndex),
    }))
  }

  const addOption = (questionIndex) => {
    const question = form.questions[questionIndex]
    if (question.options.length >= 6) return
    updateQuestion(questionIndex, 'options', [...question.options, ''])
  }

  const removeOption = (questionIndex, optionIndex) => {
    const question = form.questions[questionIndex]
    if (question.options.length <= 2) return
    const options = question.options.filter((_, index) => index !== optionIndex)
    let correctOptionIndex = question.correctOptionIndex
    if (optionIndex === correctOptionIndex) correctOptionIndex = 0
    if (optionIndex < correctOptionIndex) correctOptionIndex -= 1
    setForm((current) => ({
      ...current,
      questions: current.questions.map((item, index) =>
        index === questionIndex
          ? { ...item, options, correctOptionIndex }
          : item
      ),
    }))
  }

  const saveQuiz = async (event, isPublished) => {
    event.preventDefault()
    setSaving(true)
    setError('')

    const payload = {
      title: form.title,
      subject: form.subject,
      is_published: isPublished,
      questions: form.questions.map((question) => ({
        question: question.question,
        topic: question.topic,
        difficulty: question.difficulty,
        options: question.options,
        answer: question.options[question.correctOptionIndex],
        explanation: question.explanation,
      })),
    }

    try {
      if (editing) {
        await api.put(`/teacher/quizzes/${quizId}`, payload)
      } else {
        await api.post('/teacher/quizzes', payload)
      }
      navigate('/teacher/quizzes')
    } catch (err) {
      console.error('Save quiz error:', err)
      setError(err.response?.data?.error || 'Unable to save this quiz.')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className="quiz-editor-state">Loading quiz...</div>
  }

  return (
    <div className="teacher-quiz-editor-page">
      <header className="quiz-editor-header">
        <div>
          <p>QUIZ BUILDER</p>
          <h1>{editing ? 'Edit Quiz' : 'Create Quiz'}</h1>
          <span>Every question needs a topic and difficulty for learning analysis.</span>
        </div>
        <button type="button" onClick={() => navigate('/teacher/quizzes')}>
          ← Back to Quizzes
        </button>
      </header>

      {error && <div className="quiz-editor-error">⚠️ {error}</div>}

      <form
        className="quiz-editor-form"
        onSubmit={(event) => saveQuiz(event, true)}
      >
        <section className="quiz-basics-card">
          <h2>Quiz Details</h2>
          <div className="quiz-basics-grid">
            <label>
              Quiz title
              <input
                value={form.title}
                onChange={(event) => setForm({ ...form, title: event.target.value })}
                maxLength="200"
                required
                placeholder="e.g. Force and Motion Practice"
              />
            </label>
            <label>
              Subject
              <input
                value={form.subject}
                onChange={(event) => setForm({ ...form, subject: event.target.value })}
                maxLength="100"
                required
                placeholder="e.g. Science"
              />
            </label>
          </div>
        </section>

        <div className="quiz-questions-heading">
          <div>
            <h2>Questions</h2>
            <p>{form.questions.length} question{form.questions.length === 1 ? '' : 's'}</p>
          </div>
          <button type="button" onClick={addQuestion}>+ Add Question</button>
        </div>

        {form.questions.map((question, questionIndex) => (
          <section className="quiz-question-editor" key={questionIndex}>
            <div className="question-editor-top">
              <h3>Question {questionIndex + 1}</h3>
              <button
                type="button"
                onClick={() => removeQuestion(questionIndex)}
                disabled={form.questions.length === 1}
              >
                Remove
              </button>
            </div>

            <label>
              Question text
              <textarea
                value={question.question}
                onChange={(event) => updateQuestion(questionIndex, 'question', event.target.value)}
                required
                rows="3"
                placeholder="Write the question clearly"
              />
            </label>

            <div className="question-classification-grid">
              <label>
                Topic
                <input
                  value={question.topic}
                  onChange={(event) => updateQuestion(questionIndex, 'topic', event.target.value)}
                  maxLength="100"
                  required
                  placeholder="e.g. Force"
                />
              </label>
              <label>
                Difficulty
                <select
                  value={question.difficulty}
                  onChange={(event) => updateQuestion(questionIndex, 'difficulty', event.target.value)}
                >
                  <option value="easy">Easy</option>
                  <option value="medium">Medium</option>
                  <option value="hard">Hard</option>
                </select>
              </label>
            </div>

            <div className="question-options-heading">
              <strong>Answer options</strong>
              <span>Select the radio button beside the correct option.</span>
            </div>

            <div className="question-option-editors">
              {question.options.map((option, optionIndex) => (
                <div className="question-option-editor" key={optionIndex}>
                  <input
                    type="radio"
                    name={`correct-answer-${questionIndex}`}
                    checked={question.correctOptionIndex === optionIndex}
                    onChange={() => updateQuestion(
                      questionIndex,
                      'correctOptionIndex',
                      optionIndex
                    )}
                    aria-label={`Mark option ${optionIndex + 1} as correct`}
                  />
                  <span>{String.fromCharCode(65 + optionIndex)}</span>
                  <input
                    type="text"
                    value={option}
                    onChange={(event) => updateOption(
                      questionIndex,
                      optionIndex,
                      event.target.value
                    )}
                    required
                    placeholder={`Option ${optionIndex + 1}`}
                  />
                  <button
                    type="button"
                    onClick={() => removeOption(questionIndex, optionIndex)}
                    disabled={question.options.length <= 2}
                    aria-label={`Remove option ${optionIndex + 1}`}
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>

            <button
              type="button"
              className="add-option-button"
              onClick={() => addOption(questionIndex)}
              disabled={question.options.length >= 6}
            >
              + Add Option
            </button>

            <label className="explanation-field">
              Explanation (optional)
              <textarea
                value={question.explanation}
                onChange={(event) => updateQuestion(
                  questionIndex,
                  'explanation',
                  event.target.value
                )}
                rows="2"
                placeholder="Explain why the selected answer is correct"
              />
            </label>
          </section>
        ))}

        <footer className="quiz-editor-actions">
          <button
            type="button"
            className="save-draft-button"
            disabled={saving}
            onClick={(event) => saveQuiz(event, false)}
          >
            {saving ? 'Saving...' : 'Save as Draft'}
          </button>
          <button
            type="submit"
            className="publish-quiz-button"
            disabled={saving}
          >
            {saving ? 'Saving...' : editing ? 'Save and Publish' : 'Create and Publish'}
          </button>
        </footer>
      </form>
    </div>
  )
}

export default TeacherQuizEditor
