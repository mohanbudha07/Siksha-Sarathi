import { useCallback, useEffect, useState } from 'react'
import api from '../api'
import { useToast } from '../components/feedback/useToast'
import './TeacherQuestionBank.css'

const cognitiveLevels = [
  ['unspecified', 'Unspecified'],
  ['recall', 'Recall'],
  ['understanding', 'Understanding'],
  ['application', 'Application'],
  ['higher_order', 'Higher Order'],
]

const blankQuestion = () => ({
  question_text: '', topic: '', difficulty: 'easy', curriculum_code: 'unspecified',
  cognitive_level: 'unspecified', options: ['', ''], correct_option_index: 0,
  explanation: '',
})

function TeacherQuestionBank() {
  const { confirm, toast } = useToast()
  const [subjects, setSubjects] = useState([])
  const [subjectId, setSubjectId] = useState('')
  const [questions, setQuestions] = useState([])
  const [topics, setTopics] = useState([])
  const [pagination, setPagination] = useState({ page: 1, page_size: 25, total: 0, total_pages: 0 })
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [topic, setTopic] = useState('')
  const [difficulty, setDifficulty] = useState('')
  const [loading, setLoading] = useState(true)
  const [pageError, setPageError] = useState('')
  const [questionDialog, setQuestionDialog] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [questionForm, setQuestionForm] = useState(blankQuestion)
  const [savingQuestion, setSavingQuestion] = useState(false)
  const [importDialog, setImportDialog] = useState(false)
  const [csvFile, setCsvFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [previewing, setPreviewing] = useState(false)
  const [importing, setImporting] = useState(false)
  const [fileError, setFileError] = useState('')
  const [showColumns, setShowColumns] = useState(false)
  const [showErrorDetails, setShowErrorDetails] = useState(false)
  const [visibleErrorCount, setVisibleErrorCount] = useState(10)
  const [draggingFile, setDraggingFile] = useState(false)

  useEffect(() => {
    api.get('/teacher/question-bank/options')
      .then((response) => {
        const available = response.data.subjects || []
        setSubjects(available)
        if (available.length) setSubjectId(String(available[0].id))
      })
        .catch(() => setPageError('Unable to load your assigned subjects.'))
  }, [])

      const loadQuestions = useCallback(async () => {
    if (!subjectId) {
      setQuestions([])
      setLoading(false)
      return
    }
    try {
      setLoading(true)
      setPageError('')
      const response = await api.get('/teacher/question-bank', {
        params: { subject_id: subjectId, search, topic, difficulty, page: pagination.page, page_size: pagination.page_size },
      })
      setQuestions(response.data.questions || [])
      setTopics(response.data.topics || [])
      setPagination(response.data.pagination)
    } catch (error) {
      setPageError(error.response?.data?.error || 'Unable to load Question Bank.')
    } finally {
      setLoading(false)
    }
  }, [subjectId, search, topic, difficulty, pagination.page, pagination.page_size])

  useEffect(() => { loadQuestions() }, [loadQuestions])

  const openCreate = () => {
    setEditingId(null)
    setQuestionForm(blankQuestion())
    setQuestionDialog(true)
  }

  const openEdit = (question) => {
    setEditingId(question.id)
    setQuestionForm({
      question_text: question.question,
      topic: question.topic,
      difficulty: question.difficulty,
      curriculum_code: question.curriculum_code,
      cognitive_level: question.cognitive_level,
      options: [...question.options],
      correct_option_index: question.correct_option_index,
      explanation: question.explanation || '',
    })
    setQuestionDialog(true)
  }

  const changeQuestion = (field, value) => setQuestionForm((current) => ({ ...current, [field]: value }))

  const saveQuestion = async (event) => {
    event.preventDefault()
    setSavingQuestion(true)
    try {
      const payload = { ...questionForm, subject_id: Number(subjectId) }
      if (editingId) await api.put(`/teacher/question-bank/${editingId}`, payload)
      else await api.post('/teacher/question-bank', payload)
      toast.success(editingId ? 'Question updated.' : 'Question added to the bank.')
      setQuestionDialog(false)
      setPagination((current) => ({ ...current, page: 1 }))
      if (pagination.page === 1) await loadQuestions()
    } catch (error) {
      toast.error(error.response?.data?.error || 'Unable to save question.')
    } finally {
      setSavingQuestion(false)
    }
  }

  const deleteQuestion = async (question) => {
    if (!await confirm({
      title: 'Delete question?',
      description: 'This removes the Question Bank entry only. Quizzes already saved with this question remain unchanged.',
      confirmLabel: 'Delete Question',
      variant: 'danger',
    })) return
    try {
      await api.delete(`/teacher/question-bank/${question.id}`)
      toast.success('Question deleted.')
      await loadQuestions()
    } catch (error) {
      toast.error(error.response?.data?.error || 'Unable to delete question.')
    }
  }

  const downloadTemplate = async () => {
    try {
      const response = await api.get('/teacher/question-bank/template', { responseType: 'blob' })
      const url = URL.createObjectURL(response.data)
      const link = document.createElement('a')
      link.href = url
      link.download = 'question_bank_template.csv'
      link.click()
      URL.revokeObjectURL(url)
    } catch {
      toast.error('Unable to download the CSV template.')
    }
  }

  const openImport = () => {
    setCsvFile(null)
    setPreview(null)
    setFileError('')
    setShowColumns(false)
    setShowErrorDetails(false)
    setVisibleErrorCount(10)
    setImportDialog(true)
  }

  const chooseCsvFile = (file) => {
    setPreview(null)
    setShowErrorDetails(false)
    setVisibleErrorCount(10)
    if (!file) {
      setCsvFile(null)
      setFileError('')
      return
    }
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setCsvFile(null)
      setFileError('Please choose a .csv file.')
      return
    }
    if (file.size > 5 * 1024 * 1024) {
      setCsvFile(null)
      setFileError('CSV files must be 5 MB or smaller.')
      return
    }
    setFileError('')
    setCsvFile(file)
  }

  const previewCsv = async () => {
    if (!csvFile) return
    const payload = new FormData()
    payload.append('subject_id', subjectId)
    payload.append('file', csvFile)
    try {
      setPreviewing(true)
      const response = await api.post('/teacher/question-bank/import/preview', payload)
      setPreview(response.data)
    } catch (error) {
      setPreview(error.response?.data || { error: 'Unable to validate this CSV.' })
    } finally {
      setPreviewing(false)
    }
  }

  const importCsv = async () => {
    if (!csvFile || !preview?.can_import) return
    const payload = new FormData()
    payload.append('subject_id', subjectId)
    payload.append('file', csvFile)
    try {
      setImporting(true)
      const response = await api.post('/teacher/question-bank/import', payload)
      toast.success(`${response.data.imported_count} questions imported successfully.`)
      setImportDialog(false)
      setPagination((current) => ({ ...current, page: 1 }))
      setSearch('')
      setSearchInput('')
      setTopic('')
      setDifficulty('')
      await loadQuestions()
    } catch (error) {
      toast.error(error.response?.data?.error || 'Unable to import questions.')
      setPreview(null)
    } finally {
      setImporting(false)
    }
  }

  const submitSearch = (event) => {
    event.preventDefault()
    setPagination((current) => ({ ...current, page: 1 }))
    setSearch(searchInput.trim())
  }

  const selectedSubject = subjects.find((subjectItem) => String(subjectItem.id) === subjectId)
  const previewErrors = preview?.errors || []
  const previewProblemCount = preview?.invalid_count || preview?.error_count || 0
  const visiblePreviewErrors = previewErrors.slice(0, visibleErrorCount)
  const existingDuplicateErrors = previewErrors.filter((item) => item.message.toLowerCase().includes('already exists'))
  const duplicateOnly = Boolean(
    preview && preview.total_rows > 0 && preview.valid_count === 0
    && preview.duplicate_count >= preview.total_rows
    && existingDuplicateErrors.length >= preview.total_rows
  )
  const errorGroups = (() => {
    const groups = new Map()
    previewErrors.forEach((item) => {
      const message = item.message.toLowerCase()
      let label = 'other questions need attention'
      let key = 'other'
      if (message.includes('already exists')) { key = 'existing'; label = 'questions already exist in this Subject' }
      else if (message.includes('duplicate question')) { key = 'duplicate'; label = 'duplicate questions appear in the file' }
      else if (item.field === 'difficulty' || message.includes('difficulty')) { key = 'difficulty'; label = 'questions have an invalid difficulty' }
      else if (item.field === 'correct_option' || message.includes('correct option')) { key = 'answer'; label = 'questions have no valid correct answer' }
      else if (item.field === 'question' && message.includes('required')) { key = 'question'; label = 'questions are missing question text' }
      if (!groups.has(key)) groups.set(key, { label, rows: new Set() })
      groups.get(key).rows.add(item.row)
    })
    return [...groups.values()]
  })()

  return (
    <main className="question-bank-page">
      <header className="question-bank-header">
        <div>
          <p>TEACHING RESOURCES</p>
          <h1>Question Bank</h1>
          <span>Build a reusable collection of questions for your assigned subjects.</span>
        </div>
        <label className="question-bank-subject">
          Subject
          <select value={subjectId} onChange={(event) => {
            setSubjectId(event.target.value)
            setPagination((current) => ({ ...current, page: 1 }))
          }} disabled={!subjects.length}>
            {subjects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </label>
      </header>

      {subjects.length === 0 && !loading ? <p className="question-bank-empty">No assigned subjects are available for Question Bank access.</p> : <>
        {pageError && <p className="question-bank-error" role="alert">{pageError}</p>}
        <section className="question-bank-toolbar" aria-label="Question Bank controls">
          <form className="question-bank-search" onSubmit={submitSearch}>
            <input value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Search question or topic" aria-label="Search question or topic" />
            <button type="submit">Search</button>
          </form>
          <label>Topic
            <select value={topic} onChange={(event) => { setTopic(event.target.value); setPagination((current) => ({ ...current, page: 1 })) }}>
              <option value="">All topics</option>
              {topics.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <label>Difficulty
            <select value={difficulty} onChange={(event) => { setDifficulty(event.target.value); setPagination((current) => ({ ...current, page: 1 })) }}>
              <option value="">All difficulties</option><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option>
            </select>
          </label>
          <div className="question-bank-actions">
            <button type="button" className="question-bank-button secondary" onClick={downloadTemplate}>Download Template</button>
            <button type="button" className="question-bank-button secondary" onClick={openImport} disabled={!subjectId}>Import CSV</button>
            <button type="button" className="question-bank-button primary" onClick={openCreate} disabled={!subjectId}>Add Question</button>
          </div>
        </section>

        <div className="question-bank-count">{pagination.total || 0} questions · {selectedSubject?.name || 'Select a subject'}</div>
        {loading ? <p className="question-bank-empty">Loading questions…</p> : questions.length === 0 ? <p className="question-bank-empty">No questions match these filters.</p> : (
          <div className="question-bank-list">
            {questions.map((question) => <article className="question-bank-row" key={question.id}>
              <div className="question-bank-row-heading">
                <h2>{question.question}</h2>
                <div className="question-bank-row-actions">
                  <button type="button" onClick={() => openEdit(question)}>Edit</button>
                  <button type="button" className="danger" onClick={() => deleteQuestion(question)}>Delete</button>
                </div>
              </div>
              <div className="question-bank-meta">
                <span>{question.topic}</span><span className={`difficulty-${question.difficulty}`}>{question.difficulty}</span>
                <span>{question.options.length} options</span><span>Answer: {question.correct_answer}</span>
                <span>Curriculum: {question.curriculum_code}</span><span>{question.cognitive_level.replace('_', ' ')}</span>
                <time>{question.updated_at}</time>
              </div>
            </article>)}
          </div>
        )}

        {pagination.total_pages > 0 && <footer className="question-bank-pagination">
          <label>Rows per page:
            <select value={pagination.page_size} onChange={(event) => setPagination((current) => ({ ...current, page_size: Number(event.target.value), page: 1 }))}>
              {[10, 25, 50, 100].map((size) => <option key={size}>{size}</option>)}
            </select>
          </label>
          <div className="question-bank-page-controls">
            <button type="button" disabled={pagination.page <= 1} onClick={() => setPagination((current) => ({ ...current, page: current.page - 1 }))}>← Previous</button>
            <span>Page {pagination.page} of {pagination.total_pages}</span>
            <button type="button" disabled={pagination.page >= pagination.total_pages} onClick={() => setPagination((current) => ({ ...current, page: current.page + 1 }))}>Next →</button>
          </div>
        </footer>}
      </>}

      {questionDialog && <div className="question-bank-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setQuestionDialog(false) }}>
        <section className="question-bank-dialog" role="dialog" aria-modal="true" aria-labelledby="question-form-heading">
          <header><h2 id="question-form-heading">{editingId ? 'Edit Question' : 'Add Question'}</h2><button type="button" aria-label="Close" onClick={() => setQuestionDialog(false)}>×</button></header>
          <form onSubmit={saveQuestion}>
            <label>Question<textarea value={questionForm.question_text} onChange={(event) => changeQuestion('question_text', event.target.value)} required rows="3" /></label>
            <div className="question-bank-form-grid">
              <label>Topic<input value={questionForm.topic} onChange={(event) => changeQuestion('topic', event.target.value)} maxLength="100" required /></label>
              <label>Difficulty<select value={questionForm.difficulty} onChange={(event) => changeQuestion('difficulty', event.target.value)}><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option></select></label>
              <label>Curriculum code<input value={questionForm.curriculum_code} onChange={(event) => changeQuestion('curriculum_code', event.target.value)} maxLength="50" /></label>
              <label>Cognitive level<select value={questionForm.cognitive_level} onChange={(event) => changeQuestion('cognitive_level', event.target.value)}>{cognitiveLevels.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            </div>
            <fieldset className="question-bank-options"><legend>Answer options · select the correct answer</legend>
              {questionForm.options.map((option, index) => <div key={index}>
                <input type="radio" name="bank-correct" checked={questionForm.correct_option_index === index} onChange={() => changeQuestion('correct_option_index', index)} aria-label={`Set option ${String.fromCharCode(65 + index)} as correct`} />
                <span>{String.fromCharCode(65 + index)}</span>
                <input value={option} onChange={(event) => changeQuestion('options', questionForm.options.map((item, itemIndex) => itemIndex === index ? event.target.value : item))} maxLength="1000" required />
                <button type="button" aria-label={`Remove option ${String.fromCharCode(65 + index)}`} disabled={questionForm.options.length <= 2} onClick={() => setQuestionForm((current) => {
                  const options = current.options.filter((_, itemIndex) => itemIndex !== index)
                  let correct = current.correct_option_index
                  if (index === correct) correct = 0
                  else if (index < correct) correct -= 1
                  return { ...current, options, correct_option_index: correct }
                })}>Remove</button>
              </div>)}
              <button type="button" disabled={questionForm.options.length >= 6} onClick={() => changeQuestion('options', [...questionForm.options, ''])}>Add option</button>
            </fieldset>
            <label>Explanation<textarea value={questionForm.explanation} onChange={(event) => changeQuestion('explanation', event.target.value)} rows="2" /></label>
            <footer><button type="button" className="secondary" onClick={() => setQuestionDialog(false)}>Cancel</button><button type="submit" className="primary" disabled={savingQuestion}>{savingQuestion ? 'Saving…' : 'Save Question'}</button></footer>
          </form>
        </section>
      </div>}

      {importDialog && <div className="question-bank-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setImportDialog(false) }}>
        <section className="question-bank-dialog import-dialog" role="dialog" aria-modal="true" aria-labelledby="question-import-heading">
          <header><h2 id="question-import-heading">Import Questions</h2><button type="button" aria-label="Close" onClick={() => setImportDialog(false)}>×</button></header>
          <p className="question-import-subtitle">Upload many questions at once using our CSV template.</p>
          <p className="question-import-subject"><strong>Importing into:</strong> {selectedSubject?.name}</p>
          <ol className="question-import-steps">
            <li>Download the template</li><li>Fill your questions in Excel or Google Sheets</li><li>Upload the completed CSV</li>
          </ol>
          <section className="question-import-template">
            <div><strong>CSV Template</strong><p>Use our template so your questions are in the correct format.</p></div>
            <button type="button" className="question-bank-button secondary" onClick={downloadTemplate}>Download Template</button>
            <small>Supports up to 5,000 questions per file.</small>
            <button type="button" className="question-import-columns-toggle" aria-expanded={showColumns} onClick={() => setShowColumns((value) => !value)}>{showColumns ? 'Hide required columns' : 'View required columns'}</button>
            {showColumns && <ul className="question-import-columns">
              {['Question', 'Topic', 'Difficulty', 'Curriculum Code', 'Cognitive Level', 'Option A', 'Option B', 'Option C', 'Option D', 'Option E', 'Option F', 'Correct Option', 'Explanation'].map((label) => <li key={label}>{label}</li>)}
            </ul>}
          </section>
          <section className="question-import-example">
            <h3>Example</h3>
            <dl>
              <div><dt>Question</dt><dd>What is the SI unit of force?</dd></div>
              <div><dt>Topic</dt><dd>Force and Motion</dd></div>
              <div><dt>Difficulty</dt><dd>Easy</dd></div>
              <div><dt>Options</dt><dd>A. Newton<br />B. Joule<br />C. Watt<br />D. Pascal</dd></div>
              <div><dt>Correct answer</dt><dd>A — Newton</dd></div>
            </dl>
          </section>
          <p className="question-bank-academic-note">Please review your questions and answers for academic accuracy before importing.</p>
          <div
            className={`question-import-dropzone ${draggingFile ? 'is-dragging' : ''} ${csvFile ? 'has-file' : ''}`}
            onDragOver={(event) => { event.preventDefault(); setDraggingFile(true) }}
            onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setDraggingFile(false) }}
            onDrop={(event) => { event.preventDefault(); setDraggingFile(false); chooseCsvFile(event.dataTransfer.files?.[0]) }}
          >
            <strong>{csvFile ? '✓ File selected' : 'Upload your CSV file'}</strong>
            {!csvFile && <><span>Drag and drop a CSV here</span><span>or</span></>}
            <label className="question-import-choose-file">
              {csvFile ? 'Change file' : 'Choose CSV File'}
              <input type="file" accept=".csv,text/csv" onChange={(event) => { chooseCsvFile(event.target.files?.[0]); event.target.value = '' }} />
            </label>
            <small>{csvFile ? <span className="question-import-filename" title={csvFile.name}>{csvFile.name}</span> : 'CSV only · Maximum 5 MB'}</small>
          </div>
          {fileError && <p className="question-bank-error" role="alert">{fileError}</p>}
          {preview?.error && <p className="question-bank-error" role="alert">{preview.error}</p>}
          {preview && !preview.error && <section className={`question-import-preview ${preview.can_import ? 'is-valid' : 'is-invalid'}`}>
            {preview.can_import ? <>
              <h3>✓ File is ready to import</h3>
              <strong className="question-import-total">{preview.total_rows} questions found</strong>
              <div className="question-import-simple-counts"><span>{preview.valid_count} valid</span><span>{preview.invalid_count} problems</span></div>
            </> : <>
              <h3>⚠ {duplicateOnly ? 'Nothing to import' : 'Some questions need attention'}</h3>
              <div className="question-import-simple-counts"><span>{preview.total_rows} questions found</span><span>{preview.valid_count} ready</span><span>{previewProblemCount} problems</span></div>
              {duplicateOnly ? <p className="question-import-duplicate-only">All {preview.total_rows} questions already exist in this {selectedSubject?.name} Question Bank. No changes were made.</p> : <>
                {preview.valid_count > 0 && <p className="question-import-blocked-copy">{preview.valid_count} questions are valid, but the whole file must be valid before it can be imported.</p>}
                {errorGroups.length > 0 && <div className="question-import-problem-summary"><strong>Problems found</strong><ul>{errorGroups.map((group) => <li key={group.label}>{group.rows.size} {group.label}</li>)}</ul></div>}
                {previewErrors.length > 0 && <button type="button" className="question-import-details-toggle" aria-expanded={showErrorDetails} onClick={() => setShowErrorDetails((value) => !value)}>{showErrorDetails ? 'Hide details' : `Show ${previewProblemCount} Problems`}</button>}
                {showErrorDetails && <div className="question-import-error-details">
                  <ul>{visiblePreviewErrors.map((error, index) => <li key={`${error.row}-${error.field}-${index}`}>Row {error.row} — {error.message}</li>)}</ul>
                  {preview.error_count > visiblePreviewErrors.length && <p>Showing {visiblePreviewErrors.length} of {preview.error_count} problems.</p>}
                  {visiblePreviewErrors.length < previewErrors.length && <button type="button" onClick={() => setVisibleErrorCount((count) => count + 10)}>Show more</button>}
                  {preview.errors_truncated && visiblePreviewErrors.length === previewErrors.length && <p>Only the first {previewErrors.length} problem details are available here.</p>}
                </div>}
              </>}
            </>}
          </section>}
          <footer>
            <button type="button" className="secondary" onClick={() => setImportDialog(false)}>Cancel</button>
            {!preview && <button type="button" className="primary" onClick={previewCsv} disabled={!csvFile || previewing}>{previewing ? 'Checking questions…' : 'Check File'}</button>}
            {preview?.can_import && <button type="button" className="primary" disabled={importing} onClick={importCsv}>{importing ? 'Importing…' : `Import ${preview.valid_count} Questions`}</button>}
            {preview && !preview.error && !preview.can_import && <button type="button" className="primary" disabled>{duplicateOnly ? 'Nothing to Import' : 'Fix File First'}</button>}
            {preview?.error && <button type="button" className="primary" disabled>Fix File First</button>}
          </footer>
        </section>
      </div>}
    </main>
  )
}

export default TeacherQuestionBank