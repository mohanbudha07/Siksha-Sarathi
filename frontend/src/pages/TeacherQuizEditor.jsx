import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import api from '../api'
import { useToast } from '../components/feedback/useToast'
import './TeacherQuizEditor.css'

const emptyQuestion = () => ({
  question: '',
  topic: '',
  difficulty: 'easy',
  curriculum_code: 'unspecified',
  cognitive_level: 'unspecified',
  options: ['', '', '', ''],
  correctOptionIndex: 0,
  explanation: '',
})

const normalizeQuestion = (value) => String(value || '').trim().replace(/\s+/g, ' ').toLowerCase()

const isPristineQuestion = (question) => (
  !String(question.question || '').trim()
  && !String(question.topic || '').trim()
  && !String(question.explanation || '').trim()
  && ['', 'unspecified'].includes(String(question.curriculum_code || '').trim().toLowerCase())
  && ['', 'unspecified'].includes(String(question.cognitive_level || '').trim().toLowerCase())
  && question.difficulty === 'easy'
  && Array.isArray(question.options)
  && question.options.every((option) => !String(option || '').trim())
)

function TeacherQuizEditor() {
  const { quizId } = useParams()
  const navigate = useNavigate()
  const { confirm, toast } = useToast()
  const editing = Boolean(quizId)
  const titleFieldRef = useRef(null)
  const questionFieldRefs = useRef([])
  const pendingFocusIndex = useRef(null)
  const [form, setForm] = useState({
    title: '',
    subject: '',
    questions: [emptyQuestion()],
  })
  const [subjectOptions, setSubjectOptions] = useState([])
  const [selectedSubjectId, setSelectedSubjectId] = useState('')
  const [bankPickerOpen, setBankPickerOpen] = useState(false)
  const [bankQuestions, setBankQuestions] = useState([])
  const [bankTopics, setBankTopics] = useState([])
  const [bankPagination, setBankPagination] = useState({ page: 1, total_pages: 0, total: 0 })
  const [bankSearch, setBankSearch] = useState('')
  const [bankTopic, setBankTopic] = useState('')
  const [bankDifficulty, setBankDifficulty] = useState('')
  const [bankLoading, setBankLoading] = useState(false)
  const [bankError, setBankError] = useState('')
  const [selectedBankIds, setSelectedBankIds] = useState([])
  const [randomCount, setRandomCount] = useState('20')
  const [randomTopic, setRandomTopic] = useState('')
  const [randomDifficulty, setRandomDifficulty] = useState('')
  const [loading, setLoading] = useState(editing)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [titleError, setTitleError] = useState('')

  useEffect(() => {
    api.get('/teacher/question-bank/options')
      .then((response) => {
        const available = response.data.subjects || []
        setSubjectOptions(available)
      })
      .catch(() => setError('Unable to load assigned quiz subjects.'))
  }, [])

  useEffect(() => {
    if (pendingFocusIndex.current === null) return
    const field = questionFieldRefs.current[pendingFocusIndex.current]?.question
    if (!field) return
    field.scrollIntoView({ behavior: 'smooth', block: 'center' })
    field.focus({ preventScroll: true })
    pendingFocusIndex.current = null
  }, [form.questions.length])

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
            curriculum_code: question.curriculum_code || 'unspecified',
            cognitive_level: question.cognitive_level || 'unspecified',
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

  useEffect(() => {
    const matching = subjectOptions.find((subject) => subject.name === form.subject)
    if (matching && selectedSubjectId !== String(matching.id)) {
      setSelectedSubjectId(String(matching.id))
    } else if (!form.subject && subjectOptions[0]) {
      setSelectedSubjectId(String(subjectOptions[0].id))
      setForm((current) => current.subject ? current : ({ ...current, subject: subjectOptions[0].name }))
    }
  }, [subjectOptions, form.subject, selectedSubjectId])

  useEffect(() => {
    if (!bankPickerOpen || !selectedSubjectId) return
    let active = true
    const load = async () => {
      try {
        setBankLoading(true)
        setBankError('')
        const response = await api.get('/teacher/question-bank', {
          params: {
            subject_id: selectedSubjectId,
            search: bankSearch,
            topic: bankTopic,
            difficulty: bankDifficulty,
            page: bankPagination.page,
            page_size: 10,
          },
        })
        if (!active) return
        setBankQuestions(response.data.questions || [])
        setBankTopics(response.data.topics || [])
        setBankPagination(response.data.pagination)
      } catch (requestError) {
        if (active) setBankError(requestError.response?.data?.error || 'Unable to load bank questions.')
      } finally {
        if (active) setBankLoading(false)
      }
    }
    load()
    return () => { active = false }
  }, [bankPickerOpen, selectedSubjectId, bankSearch, bankTopic, bankDifficulty, bankPagination.page])

  const updateQuestion = (questionIndex, field, value) => {
    setForm((current) => ({
      ...current,
      questions: current.questions.map((question, index) =>
        index === questionIndex ? { ...question, [field]: value } : question
      ),
    }))
  }

  const setQuestionFieldRef = (questionIndex, fieldName, element) => {
    const fields = questionFieldRefs.current[questionIndex] || {}
    fields[fieldName] = element
    questionFieldRefs.current[questionIndex] = fields
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
    const realQuestions = form.questions.filter((question) => !isPristineQuestion(question))
    if (realQuestions.length >= 100) {
      toast.warning('A Quiz can contain at most 100 questions.')
      return
    }
    pendingFocusIndex.current = realQuestions.length
    setForm((current) => ({
      ...current,
      questions: [...current.questions.filter((question) => !isPristineQuestion(question)), emptyQuestion()],
    }))
  }

  const handleSubjectChange = async (nextSubjectId) => {
    const nextSubject = subjectOptions.find((subject) => String(subject.id) === nextSubjectId)
    if (!nextSubject) return
    const realQuestions = form.questions.filter((question) => !isPristineQuestion(question))
    const subjectChanged = nextSubject.name !== form.subject
    setForm((current) => ({ ...current, subject: nextSubject.name }))
    setSelectedSubjectId(nextSubjectId)
    if (subjectChanged && realQuestions.length) {
      toast.warning(`Subject changed to ${nextSubject.name}. Existing questions were kept. Please review them.`)
    }
  }

  const appendSnapshots = (snapshots, sourceIds = []) => {
    const retainedQuestions = form.questions.filter((question) => !isPristineQuestion(question))
    const existing = new Set(retainedQuestions.map((question) => normalizeQuestion(question.question)))
    const additions = []
    let duplicateCount = 0
    snapshots.forEach((snapshot, index) => {
      const normalized = normalizeQuestion(snapshot.question)
      if (!normalized || existing.has(normalized)) {
        duplicateCount += 1
        return
      }
      existing.add(normalized)
      additions.push({
        question: snapshot.question,
        topic: snapshot.topic,
        difficulty: snapshot.difficulty,
        curriculum_code: snapshot.curriculum_code || 'unspecified',
        cognitive_level: snapshot.cognitive_level || 'unspecified',
        options: [...snapshot.options],
        correctOptionIndex: snapshot.options.indexOf(snapshot.answer),
        explanation: snapshot.explanation || '',
        ...(sourceIds[index] ? { sourceBankId: sourceIds[index] } : {}),
      })
    })
    if (duplicateCount) toast.warning(`${duplicateCount} selected questions are already in this Quiz.`)
    const remaining = 100 - retainedQuestions.length
    if (additions.length > remaining) {
      toast.error(`You can add at most ${remaining} more questions to this Quiz.`)
      return false
    }
    if (additions.length) {
      setForm((current) => ({
        ...current,
        questions: [...current.questions.filter((question) => !isPristineQuestion(question)), ...additions],
      }))
      toast.success(`${additions.length} question${additions.length === 1 ? '' : 's'} added.`)
    }
    setBankPickerOpen(false)
    setSelectedBankIds([])
    return true
  }

  const addSelectedBankQuestions = async () => {
    if (!selectedBankIds.length) return
    const selectedSubject = subjectOptions.find((subject) => String(subject.id) === selectedSubjectId)
    if (!selectedSubject || selectedSubject.name !== form.subject) {
      toast.error('Choose the current Quiz Subject before selecting bank questions.')
      return
    }
    try {
      const response = await api.post('/teacher/question-bank/resolve', {
        subject_id: selectedSubject.id,
        question_ids: selectedBankIds,
      })
      appendSnapshots(response.data.questions, selectedBankIds)
    } catch (requestError) {
      toast.error(requestError.response?.data?.error || 'Unable to add selected questions.')
    }
  }

  const addRandomBankQuestions = async () => {
    const selectedSubject = subjectOptions.find((subject) => String(subject.id) === selectedSubjectId)
    if (!selectedSubject || selectedSubject.name !== form.subject) {
      toast.error('Choose the current Quiz Subject before selecting bank questions.')
      return
    }
    try {
      const response = await api.get('/teacher/question-bank/random', {
        params: {
          subject_id: selectedSubject.id,
          count: randomCount,
          topic: randomTopic,
          difficulty: randomDifficulty,
        },
      })
      appendSnapshots(response.data.questions)
    } catch (requestError) {
      toast.error(requestError.response?.data?.error || 'Unable to choose random questions.')
    }
  }

  const removeQuestion = async (questionIndex) => {
    if (form.questions.length === 1) return
    const question = form.questions[questionIndex]
    const hasContent = question.question.trim() || question.topic.trim()
      || question.explanation.trim() || question.options.some((option) => option.trim())
    if (hasContent && !await confirm({
      title: 'Remove question?',
      description: 'This question has entered content. Removing it will discard that content.',
      confirmLabel: 'Remove Question',
      variant: 'danger',
    })) return
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
    setError('')
    setTitleError('')

    if (!form.title.trim()) {
      setTitleError('Quiz title is required.')
      toast.error('Enter a Quiz title before saving.')
      titleFieldRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      titleFieldRef.current?.focus({ preventScroll: true })
      return
    }
    if (form.title.trim().length > 200) {
      setError('Quiz title must be 200 characters or fewer.')
      titleFieldRef.current?.focus()
      return
    }
    const selectedSubject = subjectOptions.find((subject) => String(subject.id) === selectedSubjectId)
    if (!selectedSubject || selectedSubject.name !== form.subject) {
      setError('Choose a currently assigned Subject for this Quiz.')
      return
    }

    const realQuestions = form.questions
      .map((question, index) => ({ question, index }))
      .filter(({ question }) => !isPristineQuestion(question))
    if (!realQuestions.length) {
      setError('Add at least one complete question before saving.')
      return
    }
    if (realQuestions.length > 100) {
      setError('A Quiz can contain at most 100 questions.')
      return
    }
    for (const { question, index } of realQuestions) {
      const prefix = `Question ${index + 1}: `
      let fieldName = 'question'
      let message = ''
      const prompt = String(question.question || '').trim()
      const topicValue = String(question.topic || '').trim()
      const difficultyValue = String(question.difficulty || '').trim().toLowerCase()
      const curriculumCode = String(question.curriculum_code || 'unspecified').trim()
      const cognitiveLevel = String(question.cognitive_level || 'unspecified').trim().toLowerCase()
      const options = Array.isArray(question.options)
        ? question.options.map((option) => String(option || '').trim())
        : []
      if (!prompt) message = 'Question text is required.'
      else if (!topicValue) { fieldName = 'topic'; message = 'Topic is required.' }
      else if (topicValue.length > 100) { fieldName = 'topic'; message = 'Topic must be 100 characters or fewer.' }
      else if (!['easy', 'medium', 'hard'].includes(difficultyValue)) { fieldName = 'difficulty'; message = 'Difficulty must be easy, medium, or hard.' }
      else if (!curriculumCode || curriculumCode.length > 50) { fieldName = 'curriculum_code'; message = 'Curriculum code must be 50 characters or fewer and cannot be blank.' }
      else if (!['recall', 'understanding', 'application', 'higher_order', 'unspecified'].includes(cognitiveLevel)) { fieldName = 'cognitive_level'; message = 'Cognitive level is invalid.' }
      else if (options.length < 2 || options.length > 6) { fieldName = 'option_0'; message = 'Use between 2 and 6 answer options.' }
      else if (options.some((option) => !option)) { fieldName = `option_${options.findIndex((option) => !option)}`; message = 'All answer options must contain text.' }
      else if (new Set(options).size !== options.length) { fieldName = 'option_0'; message = 'Answer options must be unique.' }
      else if (!Number.isInteger(question.correctOptionIndex) || question.correctOptionIndex < 0 || question.correctOptionIndex >= options.length) { fieldName = 'option_0'; message = 'Select the correct answer.' }
      if (message) {
        const validationMessage = `${prefix}${message}`
        setError(validationMessage)
        toast.error(validationMessage)
        const field = questionFieldRefs.current[index]?.[fieldName]
          || questionFieldRefs.current[index]?.question
        field?.scrollIntoView({ behavior: 'smooth', block: 'center' })
        field?.focus({ preventScroll: true })
        return
      }
    }
    setSaving(true)

    const payload = {
      title: form.title.trim(),
      subject: selectedSubject.name,
      is_published: isPublished,
      questions: realQuestions.map(({ question }) => ({
        question: question.question.trim(),
        topic: question.topic.trim(),
        difficulty: question.difficulty.trim().toLowerCase(),
        curriculum_code: question.curriculum_code.trim() || 'unspecified',
        cognitive_level: question.cognitive_level.trim().toLowerCase() || 'unspecified',
        options: question.options.map((option) => option.trim()),
        answer: question.options[question.correctOptionIndex].trim(),
        explanation: question.explanation.trim(),
      })),
    }

    try {
      if (editing) {
        await api.put(`/teacher/quizzes/${quizId}`, payload)
      } else {
        await api.post('/teacher/quizzes', payload)
      }
      toast.success(isPublished ? 'Quiz published.' : 'Quiz saved.')
      navigate('/teacher/quizzes')
    } catch (err) {
      console.error('Save quiz error:', err)
      const message = err.response?.data?.error || 'Unable to save quiz.'
      setError(message)
      toast.error(message)
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
                ref={titleFieldRef}
                value={form.title}
                onChange={(event) => { setForm({ ...form, title: event.target.value }); setTitleError('') }}
                maxLength="200"
                placeholder="e.g. Force and Motion Practice"
              />
              {titleError && <small className="quiz-field-error" role="alert">{titleError}</small>}
            </label>
            <label>
              Subject
              <select value={selectedSubjectId} onChange={(event) => handleSubjectChange(event.target.value)} disabled={!subjectOptions.length}>
                <option value="">Select an assigned subject</option>
                {subjectOptions.map((subject) => <option value={subject.id} key={subject.id}>{subject.name}</option>)}
              </select>
            </label>
          </div>
        </section>

        <div className="quiz-questions-heading">
          <div>
            <h2>Questions</h2>
            <p>{form.questions.filter((question) => !isPristineQuestion(question)).length} question{form.questions.filter((question) => !isPristineQuestion(question)).length === 1 ? '' : 's'}</p>
            {form.questions.filter((question) => !isPristineQuestion(question)).length > 50 && <p className="quiz-large-set-hint">For very large question sets, bulk Question Bank import is recommended.</p>}
          </div>
          <div className="quiz-editor-question-actions">
            <button type="button" onClick={() => {
              const currentSubject = subjectOptions.find((subject) => String(subject.id) === selectedSubjectId)
              if (!currentSubject || currentSubject.name !== form.subject) { toast.warning('Choose a Quiz Subject first.'); return }
              setSelectedBankIds([])
              setBankPickerOpen(true)
            }}>Add from Question Bank</button>
            <button type="button" onClick={addQuestion} disabled={form.questions.filter((question) => !isPristineQuestion(question)).length >= 100}>+ Add Question</button>
          </div>
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
                ref={(field) => setQuestionFieldRef(questionIndex, 'question', field)}
                value={question.question}
                onChange={(event) => updateQuestion(questionIndex, 'question', event.target.value)}
                rows="3"
                placeholder="Write the question clearly"
              />
            </label>

            <div className="question-classification-grid">
              <label>
                Topic
                <input
                  ref={(field) => setQuestionFieldRef(questionIndex, 'topic', field)}
                  value={question.topic}
                  onChange={(event) => updateQuestion(questionIndex, 'topic', event.target.value)}
                  maxLength="100"
                  placeholder="e.g. Force"
                />
              </label>
              <label>
                Difficulty
                <select
                  ref={(field) => setQuestionFieldRef(questionIndex, 'difficulty', field)}
                  value={question.difficulty}
                  onChange={(event) => updateQuestion(questionIndex, 'difficulty', event.target.value)}
                >
                  <option value="easy">Easy</option>
                  <option value="medium">Medium</option>
                  <option value="hard">Hard</option>
                </select>
              </label>
              <label>
                Curriculum code
                <input ref={(field) => setQuestionFieldRef(questionIndex, 'curriculum_code', field)} value={question.curriculum_code || ''} maxLength="50" onChange={(event) => updateQuestion(questionIndex, 'curriculum_code', event.target.value)} />
              </label>
              <label>
                Cognitive level
                <select ref={(field) => setQuestionFieldRef(questionIndex, 'cognitive_level', field)} value={question.cognitive_level || 'unspecified'} onChange={(event) => updateQuestion(questionIndex, 'cognitive_level', event.target.value)}>
                  <option value="unspecified">Unspecified</option><option value="recall">Recall</option><option value="understanding">Understanding</option><option value="application">Application</option><option value="higher_order">Higher Order</option>
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
                    ref={(field) => setQuestionFieldRef(questionIndex, `option_${optionIndex}`, field)}
                    value={option}
                    onChange={(event) => updateOption(
                      questionIndex,
                      optionIndex,
                      event.target.value
                    )}
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
          <button type="button" className="add-question-sticky-button" onClick={addQuestion}>
            + Add Question
          </button>
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

      {bankPickerOpen && <div className="quiz-bank-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setBankPickerOpen(false) }}>
        <section className="quiz-bank-dialog" role="dialog" aria-modal="true" aria-labelledby="quiz-bank-heading">
          <header><h2 id="quiz-bank-heading">Add from Question Bank</h2><button type="button" aria-label="Close" onClick={() => setBankPickerOpen(false)}>×</button></header>
          <div className="quiz-bank-filters">
            <label>Search<input value={bankSearch} onChange={(event) => { setBankSearch(event.target.value); setBankPagination((current) => ({ ...current, page: 1 })) }} placeholder="Question or topic" /></label>
            <label>Topic<select value={bankTopic} onChange={(event) => { setBankTopic(event.target.value); setBankPagination((current) => ({ ...current, page: 1 })) }}><option value="">All topics</option>{bankTopics.map((item) => <option key={item}>{item}</option>)}</select></label>
            <label>Difficulty<select value={bankDifficulty} onChange={(event) => { setBankDifficulty(event.target.value); setBankPagination((current) => ({ ...current, page: 1 })) }}><option value="">All</option><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option></select></label>
          </div>
          <p className="quiz-bank-selected">Selected: {selectedBankIds.length}</p>
          {bankError && <p className="quiz-editor-error" role="alert">{bankError}</p>}
          {bankLoading ? <p>Loading questions…</p> : bankQuestions.length === 0 ? <p>No questions match these filters.</p> : <div className="quiz-bank-list">
            {bankQuestions.map((question) => <label key={question.id} className="quiz-bank-item">
              <input type="checkbox" checked={selectedBankIds.includes(question.id)} onChange={(event) => setSelectedBankIds((current) => {
                if (!event.target.checked) return current.filter((id) => id !== question.id)
                const realQuestionCount = form.questions.filter((item) => !isPristineQuestion(item)).length
                const remaining = Math.max(0, 100 - realQuestionCount)
                if (current.length >= remaining) {
                  toast.warning(`You can add at most ${remaining} more questions to this Quiz.`)
                  return current
                }
                return [...current, question.id]
              })} />
              <span><strong>{question.question}</strong><small>{question.topic} · {question.difficulty} · {question.options.length} options</small></span>
            </label>)}
          </div>}
          <div className="quiz-bank-pagination"><span>Page {bankPagination.page} of {bankPagination.total_pages || 1}</span><button type="button" disabled={bankPagination.page <= 1} onClick={() => setBankPagination((current) => ({ ...current, page: current.page - 1 }))}>Previous</button><button type="button" disabled={bankPagination.page >= bankPagination.total_pages} onClick={() => setBankPagination((current) => ({ ...current, page: current.page + 1 }))}>Next</button></div>
          <section className="quiz-bank-random">
            <h3>Random selection</h3>
            <label>Questions<input type="number" min="1" max="100" value={randomCount} onChange={(event) => setRandomCount(event.target.value)} /></label>
            <label>Topic<select value={randomTopic} onChange={(event) => setRandomTopic(event.target.value)}><option value="">Any topic</option>{bankTopics.map((item) => <option key={item}>{item}</option>)}</select></label>
            <label>Difficulty<select value={randomDifficulty} onChange={(event) => setRandomDifficulty(event.target.value)}><option value="">Any difficulty</option><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option></select></label>
            <button type="button" onClick={addRandomBankQuestions}>Add Random Questions</button>
          </section>
          <footer><button type="button" onClick={() => setBankPickerOpen(false)}>Cancel</button><button type="button" disabled={!selectedBankIds.length} onClick={addSelectedBankQuestions}>Add Selected Questions</button></footer>
        </section>
      </div>}
    </div>
  )
}

export default TeacherQuizEditor
