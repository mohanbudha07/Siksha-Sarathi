import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'
import { useToast } from '../components/feedback/useToast'
import { fileExtension, formatFileSize, validateMaterialFiles } from '../utils/learningMaterials'
import './LearningMaterials.css'

function TeacherUploadNote() {
  const navigate = useNavigate()
  const { toast } = useToast()
  const fileInputRef = useRef(null)
  const [options, setOptions] = useState({ assignments: [], students: [] })
  const [optionsLoading, setOptionsLoading] = useState(true)
  const [optionsError, setOptionsError] = useState('')
  const [form, setForm] = useState({
    title: '', chapter: '', content: '', class_id: '', subject_id: '',
    audience: 'class', student_id: '',
  })
  const [files, setFiles] = useState([])
  const [fieldErrors, setFieldErrors] = useState({})
  const [attachmentError, setAttachmentError] = useState('')
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)

  const loadOptions = async () => {
    try {
      setOptionsLoading(true)
      setOptionsError('')
      const response = await api.get('/teacher/notes/options')
      setOptions(response.data)
      const firstAssignment = response.data.assignments[0]
      if (firstAssignment) {
        setForm((current) => ({
          ...current,
          class_id: String(firstAssignment.class_id),
          subject_id: String(firstAssignment.subject_id),
        }))
      }
    } catch {
      setOptionsError('Unable to load your teaching assignments.')
    } finally {
      setOptionsLoading(false)
    }
  }

  useEffect(() => { loadOptions() }, [])

  const classAssignments = options.assignments.filter(
    (assignment) => String(assignment.class_id) === form.class_id
  )
  const selectedAssignment = classAssignments.find(
    (assignment) => String(assignment.subject_id) === form.subject_id
  )
  const classStudents = options.students.filter(
    (student) => String(student.class_id) === form.class_id
  )

  const clearFieldError = (field) => setFieldErrors((current) => {
    const next = { ...current }
    delete next[field]
    return next
  })

  const addFiles = (selected) => {
    const selectedFiles = Array.from(selected || [])
    if (!selectedFiles.length) return
    const nextFiles = [...files, ...selectedFiles]
    const validationError = validateMaterialFiles(nextFiles)
    if (validationError) {
      setAttachmentError(validationError)
      return
    }
    setFiles(nextFiles)
    setAttachmentError('')
  }

  const validateForm = () => {
    const nextErrors = {}
    if (attachmentError) nextErrors.files = attachmentError
    if (!form.title.trim()) nextErrors.title = 'Enter a title.'
    if (!form.class_id) nextErrors.class_id = 'Select a class.'
    if (!selectedAssignment) nextErrors.subject_id = 'Select an assigned subject.'
    if (form.audience === 'student' && !form.student_id) nextErrors.student_id = 'Select a Student.'
    if (!form.content.trim() && files.length === 0) {
      nextErrors.content = 'Add written content or at least one attachment.'
    }
    setFieldErrors(nextErrors)
    return Object.keys(nextErrors).length === 0
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (attachmentError) return
    if (!validateForm()) return
    const payload = new FormData()
    payload.append('title', form.title.trim())
    payload.append('subject', selectedAssignment.subject_name)
    payload.append('chapter', form.chapter.trim())
    payload.append('content', form.content.trim())
    payload.append('class_id', form.class_id)
    if (form.audience === 'student') payload.append('student_id', form.student_id)
    files.forEach((file) => payload.append('files', file))

    try {
      setUploading(true)
      await api.post('/teacher/notes', payload)
      toast.success('Learning material uploaded.')
      navigate('/teacher/notes')
    } catch {
      toast.error('Unable to upload material.')
    } finally {
      setUploading(false)
    }
  }

  return (
    <main className="learning-material-page">
      <header className="learning-material-heading">
        <p>TEACHING MATERIALS</p>
        <h1>Upload Learning Material</h1>
        <span>Choose a class and assigned subject, then share with the whole class or one currently enrolled Student.</span>
      </header>

      {optionsLoading && <p className="learning-material-state">Loading your teaching assignments…</p>}
      {optionsError && <div className="learning-material-load-error" role="alert">
        <span>{optionsError}</span>
        <button type="button" onClick={loadOptions}>Try again</button>
      </div>}
      {!optionsLoading && !optionsError && options.assignments.length === 0 && (
        <p className="learning-material-state">No active class and subject assignments are available for this account.</p>
      )}

      {!optionsLoading && !optionsError && options.assignments.length > 0 && <form className="learning-material-form" onSubmit={handleSubmit}>
        <div className="learning-material-field-grid">
          <label className="learning-material-field">
            Title
            <input
              value={form.title}
              onChange={(event) => { setForm({ ...form, title: event.target.value }); clearFieldError('title') }}
              maxLength="200"
              required
            />
            {fieldErrors.title && <small className="field-error">{fieldErrors.title}</small>}
          </label>
          <label className="learning-material-field">
            Class / Section
            <select value={form.class_id} onChange={(event) => {
              const nextClass = event.target.value
              const firstSubject = options.assignments.find((item) => String(item.class_id) === nextClass)
              setForm({ ...form, class_id: nextClass, subject_id: String(firstSubject?.subject_id || ''), student_id: '' })
              clearFieldError('class_id')
            }} required>
              <option value="">Select an assigned class</option>
              {[...new Map(options.assignments.map((item) => [String(item.class_id), item])).values()].map((item) => (
                <option value={item.class_id} key={item.class_id}>
                  {item.class_name} · Grade {item.grade}{item.section ? ` / ${item.section}` : ''}
                </option>
              ))}
            </select>
            {fieldErrors.class_id && <small className="field-error">{fieldErrors.class_id}</small>}
          </label>
          <label className="learning-material-field">
            Subject
            <select value={form.subject_id} onChange={(event) => {
              setForm({ ...form, subject_id: event.target.value, student_id: '' })
              clearFieldError('subject_id')
            }} required disabled={!classAssignments.length}>
              <option value="">Select an assigned subject</option>
              {classAssignments.map((item) => <option value={item.subject_id} key={item.subject_id}>{item.subject_name}</option>)}
            </select>
            {fieldErrors.subject_id && <small className="field-error">{fieldErrors.subject_id}</small>}
          </label>
          <label className="learning-material-field">
            Chapter
            <input
              value={form.chapter}
              onChange={(event) => setForm({ ...form, chapter: event.target.value })}
              maxLength="100"
              required
              placeholder="e.g. Force and Motion"
            />
          </label>
        </div>

        <fieldset className="learning-material-audience">
          <legend>Audience</legend>
          <label><input type="radio" name="audience" value="class" checked={form.audience === 'class'} onChange={() => setForm({ ...form, audience: 'class', student_id: '' })} /> Entire class</label>
          <label><input type="radio" name="audience" value="student" checked={form.audience === 'student'} onChange={() => setForm({ ...form, audience: 'student' })} /> Specific student</label>
        </fieldset>

        {form.audience === 'student' && <label className="learning-material-field learning-material-student-field">
          Student
          <select value={form.student_id} onChange={(event) => {
            setForm({ ...form, student_id: event.target.value })
            clearFieldError('student_id')
          }} required>
            <option value="">Select a currently enrolled Student</option>
            {classStudents.map((student) => <option value={student.student_id} key={student.student_id}>{student.full_name}</option>)}
          </select>
          {fieldErrors.student_id && <small className="field-error">{fieldErrors.student_id}</small>}
        </label>}

        <label className="learning-material-field">
          Description / Written Note <span className="field-optional">Optional when attachments are added</span>
          <textarea value={form.content} onChange={(event) => {
            setForm({ ...form, content: event.target.value })
            clearFieldError('content')
          }} rows="7" />
          {fieldErrors.content && <small className="field-error">{fieldErrors.content}</small>}
        </label>

        <section className="learning-material-attachments" aria-labelledby="material-attachments-heading">
          <div><h2 id="material-attachments-heading">Attachments</h2><p>PDF, Word, or PowerPoint · up to 10 files · 25 MB each</p></div>
          <label
            className={`learning-material-dropzone ${dragging ? 'is-dragging' : ''}`}
            onDragOver={(event) => { event.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => { event.preventDefault(); setDragging(false); addFiles(event.dataTransfer.files) }}
          >
            <strong>Drop files here or Browse</strong>
            <span>PDF, DOC, DOCX, PPT, PPTX</span>
            <input
              ref={fileInputRef}
              className="learning-material-file-input"
              type="file"
              multiple
              accept=".pdf,.doc,.docx,.ppt,.pptx"
              aria-label="Choose Learning Material attachments"
              onChange={(event) => { addFiles(event.target.files); event.target.value = '' }}
            />
          </label>
          {attachmentError && <p className="field-error" role="alert">{attachmentError}</p>}
          {files.length > 0 && <ul className="learning-material-file-list">
            {files.map((file, index) => <li key={`${file.name}-${file.size}-${index}`}>
              <span className="material-file-badge">{fileExtension(file.name).toUpperCase()}</span>
              <span className="learning-material-file-name" title={file.name}>{file.name}</span>
              <span className="learning-material-file-size">{formatFileSize(file.size)}</span>
              <button type="button" aria-label={`Remove ${file.name}`} onClick={() => {
                setFiles((items) => items.filter((_, fileIndex) => fileIndex !== index))
              }}>Remove</button>
            </li>)}
          </ul>}
          {(files.length > 0 || attachmentError) && <button
            type="button"
            className="material-secondary-button"
            onClick={() => {
              setFiles([])
              setAttachmentError('')
              if (fileInputRef.current) fileInputRef.current.value = ''
            }}
          >Clear attachments</button>}
        </section>

        <footer className="learning-material-form-actions">
          <button type="button" className="material-secondary-button" onClick={() => navigate('/teacher/notes')}>Cancel</button>
          <button type="submit" className="material-primary-button" disabled={uploading}>
            {uploading ? 'Uploading…' : 'Upload Learning Material'}
          </button>
        </footer>
      </form>}
    </main>
  )
}

export default TeacherUploadNote