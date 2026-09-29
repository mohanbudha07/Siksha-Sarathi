import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import api from '../api'
import { useToast } from '../components/feedback/useToast'
import { downloadBlobResponse, fileExtension, formatFileSize, validateMaterialFiles } from '../utils/learningMaterials'
import './LearningMaterials.css'

function TeacherEditNote() {
  const { noteId } = useParams()
  const navigate = useNavigate()
  const { confirm, toast } = useToast()
  const fileInputRef = useRef(null)
  const [note, setNote] = useState(null)
  const [options, setOptions] = useState({ assignments: [], students: [] })
  const [form, setForm] = useState({
    title: '', chapter: '', content: '', class_id: '', subject_id: '',
    audience: 'class', student_id: '',
  })
  const [files, setFiles] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [busyAttachmentId, setBusyAttachmentId] = useState(null)
  const [fieldError, setFieldError] = useState('')
  const [loadVersion, setLoadVersion] = useState(0)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        setLoading(true)
        setLoadError('')
        const [noteResponse, optionsResponse] = await Promise.all([
          api.get(`/teacher/notes/${noteId}`),
          api.get('/teacher/notes/options'),
        ])
        if (cancelled) return
        const material = noteResponse.data.note
        const assignments = optionsResponse.data.assignments || []
        setNote(material)
        setOptions({
          assignments,
          students: optionsResponse.data.students || [],
        })
        const matchingAssignment = assignments.find((item) =>
          String(item.class_id) === String(material.target_class_id)
          && item.subject_name.toLowerCase() === String(material.subject || '').toLowerCase()
        )
        setForm({
          title: material.title || '',
          chapter: material.chapter || '',
          content: material.content || '',
          class_id: material.target_class_id ? String(material.target_class_id) : '',
          subject_id: matchingAssignment ? String(matchingAssignment.subject_id) : '',
          audience: material.target_student_id ? 'student' : 'class',
          student_id: material.target_student_id ? String(material.target_student_id) : '',
        })
      } catch {
        if (!cancelled) setLoadError('Unable to load this Learning Material.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [noteId, loadVersion])

  const classAssignments = options.assignments.filter(
    (assignment) => String(assignment.class_id) === form.class_id
  )
  const selectedAssignment = classAssignments.find(
    (assignment) => String(assignment.subject_id) === form.subject_id
  )
  const classStudents = options.students.filter(
    (student) => String(student.class_id) === form.class_id
  )

  const handleSave = async (event) => {
    event.preventDefault()
    if (!form.title.trim() || !form.chapter.trim() || !selectedAssignment) {
      setFieldError('Enter the required details and choose an assigned class and subject.')
      return
    }
    if (form.audience === 'student' && !form.student_id) {
      setFieldError('Select a currently enrolled Student.')
      return
    }
    if (!form.content.trim() && !(note?.attachments?.length > 0)) {
      setFieldError('Add written content or at least one attachment.')
      return
    }
    setFieldError('')
    setSaving(true)
    try {
      await api.put(`/teacher/notes/${noteId}`, {
        title: form.title.trim(),
        subject: selectedAssignment.subject_name,
        chapter: form.chapter.trim(),
        content: form.content.trim(),
        class_id: Number(form.class_id),
        student_id: form.audience === 'student' ? Number(form.student_id) : null,
      })
      toast.success('Learning Material updated.')
      setLoadVersion((version) => version + 1)
    } catch {
      toast.error('Unable to update Learning Material.')
    } finally {
      setSaving(false)
    }
  }

  const addAttachments = async () => {
    if (!selectedAssignment) {
      setFieldError('Choose a class and subject you are currently assigned to before adding files.')
      return
    }
    const validationError = validateMaterialFiles(files, note.attachments.length)
    if (validationError) {
      setFieldError(validationError)
      return
    }
    if (!files.length) {
      setFieldError('Choose at least one file to add.')
      return
    }
    const payload = new FormData()
    files.forEach((file) => payload.append('files', file))
    try {
      setUploading(true)
      await api.post(`/teacher/notes/${noteId}/attachments`, payload)
      const response = await api.get(`/teacher/notes/${noteId}`)
      setNote(response.data.note)
      setFiles([])
      if (fileInputRef.current) fileInputRef.current.value = ''
      setFieldError('')
      toast.success('Attachments added.')
    } catch {
      toast.error('Unable to add attachments.')
    } finally {
      setUploading(false)
    }
  }

  const removeAttachment = async (attachment) => {
    if (!form.content.trim() && note.attachments.length === 1) {
      toast.warning('Add written content before removing the final attachment.')
      return
    }
    const accepted = await confirm({
      title: 'Remove attachment?',
      description: `Remove ${attachment.original_filename} from this Learning Material?`,
      confirmLabel: 'Remove Attachment',
      variant: 'danger',
    })
    if (!accepted) return
    try {
      setBusyAttachmentId(attachment.id)
      await api.delete(`/teacher/notes/${noteId}/attachments/${attachment.id}`)
      setNote((current) => ({
        ...current,
        attachments: current.attachments.filter((item) => item.id !== attachment.id),
      }))
      toast.success('Attachment removed.')
    } catch {
      toast.error('Unable to remove attachment.')
    } finally {
      setBusyAttachmentId(null)
    }
  }

  const downloadAttachment = async (attachment) => {
    try {
      setBusyAttachmentId(attachment.id)
      const response = await api.get(
        `/teacher/notes/${noteId}/attachments/${attachment.id}/download`,
        { responseType: 'blob' }
      )
      downloadBlobResponse(response, attachment.original_filename)
    } catch {
      toast.error('Unable to download this attachment.')
    } finally {
      setBusyAttachmentId(null)
    }
  }

  if (loading) return <main className="learning-material-page"><p className="learning-material-state">Loading Learning Material…</p></main>
  if (loadError || !note) return (
    <main className="learning-material-page">
      <div className="learning-material-load-error" role="alert">
        <span>{loadError || 'Learning Material not found.'}</span>
        <button type="button" onClick={() => setLoadVersion((version) => version + 1)}>Try again</button>
      </div>
    </main>
  )

  return (
    <main className="learning-material-page">
      <header className="learning-material-heading">
        <p>TEACHING MATERIALS</p>
        <h1>Edit Learning Material</h1>
        <span>{note.target_class_name || 'Legacy subject access'}{note.target_student_name ? ` · ${note.target_student_name}` : ''}</span>
      </header>
      {!note.target_class_id && <p className="learning-material-state">Choose an assigned class and subject to scope this legacy material before saving.</p>}

      <form className="learning-material-form" onSubmit={handleSave}>
        <div className="learning-material-field-grid">
          <label className="learning-material-field">Title
            <input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} maxLength="200" required />
          </label>
          <label className="learning-material-field">Class / Section
            <select value={form.class_id} onChange={(event) => {
              const classId = event.target.value
              const firstSubject = options.assignments.find((item) => String(item.class_id) === classId)
              setForm({ ...form, class_id: classId, subject_id: String(firstSubject?.subject_id || ''), student_id: '' })
            }} required>
              <option value="">Select an assigned class</option>
              {[...new Map(options.assignments.map((item) => [String(item.class_id), item])).values()].map((item) => (
                <option key={item.class_id} value={item.class_id}>{item.class_name} · Grade {item.grade}{item.section ? ` / ${item.section}` : ''}</option>
              ))}
            </select>
          </label>
          <label className="learning-material-field">Subject
            <select value={form.subject_id} onChange={(event) => setForm({ ...form, subject_id: event.target.value, student_id: '' })} required disabled={!classAssignments.length}>
              <option value="">Select an assigned subject</option>
              {classAssignments.map((item) => <option key={item.subject_id} value={item.subject_id}>{item.subject_name}</option>)}
            </select>
          </label>
          <label className="learning-material-field">Chapter
            <input value={form.chapter} onChange={(event) => setForm({ ...form, chapter: event.target.value })} maxLength="100" required />
          </label>
        </div>

        <fieldset className="learning-material-audience">
          <legend>Audience</legend>
          <label><input type="radio" name="audience" checked={form.audience === 'class'} onChange={() => setForm({ ...form, audience: 'class', student_id: '' })} /> Entire class</label>
          <label><input type="radio" name="audience" checked={form.audience === 'student'} onChange={() => setForm({ ...form, audience: 'student' })} /> Specific student</label>
        </fieldset>
        {form.audience === 'student' && <label className="learning-material-field learning-material-student-field">Student
          <select value={form.student_id} onChange={(event) => setForm({ ...form, student_id: event.target.value })} required>
            <option value="">Select a currently enrolled Student</option>
            {classStudents.map((student) => <option key={student.student_id} value={student.student_id}>{student.full_name}</option>)}
          </select>
        </label>}

        <label className="learning-material-field">Description / Written Note <span className="field-optional">Optional when attachments exist</span>
          <textarea value={form.content} onChange={(event) => setForm({ ...form, content: event.target.value })} rows="7" required={note.attachments.length === 0} />
        </label>
        {fieldError && <p className="field-error" role="alert">{fieldError}</p>}

        <footer className="learning-material-form-actions">
          <button type="button" className="material-secondary-button" onClick={() => navigate('/teacher/notes')}>Cancel</button>
          <button type="submit" className="material-primary-button" disabled={saving}>{saving ? 'Saving…' : 'Save Material Details'}</button>
        </footer>
      </form>

      <section className="learning-material-attachments">
        <div><h2>Attachments</h2><p>{note.attachments.length} of 10 files · 25 MB maximum per file</p></div>
        {note.attachments.length > 0 && <ul className="learning-material-file-list">
          {note.attachments.map((attachment) => <li key={attachment.id}>
            <span className="material-file-badge">{fileExtension(attachment.original_filename).toUpperCase()}</span>
            <span className="learning-material-file-name" title={attachment.original_filename}>{attachment.original_filename}</span>
            <span className="learning-material-file-size">{formatFileSize(attachment.size_bytes)}</span>
            <button type="button" className="material-download-button" onClick={() => downloadAttachment(attachment)} disabled={busyAttachmentId === attachment.id}>Download</button>
            <button type="button" onClick={() => removeAttachment(attachment)} disabled={busyAttachmentId === attachment.id}>Remove</button>
          </li>)}
        </ul>}
        <label className="learning-material-dropzone">
          <strong>Select additional files or Browse</strong>
          <span>PDF, DOC, DOCX, PPT, PPTX</span>
          <input ref={fileInputRef} className="learning-material-file-input" type="file" multiple accept=".pdf,.doc,.docx,.ppt,.pptx" aria-label="Choose attachments to add" onChange={(event) => {
            const nextFiles = [...files, ...Array.from(event.target.files || [])]
            const error = validateMaterialFiles(nextFiles, note.attachments.length)
            setFieldError(error)
            if (!error) setFiles(nextFiles)
            event.target.value = ''
          }} />
        </label>
        {files.length > 0 && <ul className="learning-material-file-list">{files.map((file, index) => <li key={`${file.name}-${file.size}-${index}`}>
          <span className="material-file-badge">{fileExtension(file.name).toUpperCase()}</span>
          <span className="learning-material-file-name">{file.name}</span>
          <span className="learning-material-file-size">{formatFileSize(file.size)}</span>
          <button type="button" onClick={() => setFiles((current) => current.filter((_, fileIndex) => fileIndex !== index))}>Remove</button>
        </li>)}</ul>}
        <button type="button" className="material-primary-button" onClick={addAttachments} disabled={uploading || files.length === 0}>
          {uploading ? 'Uploading…' : 'Add Attachments'}
        </button>
      </section>
    </main>
  )
}

export default TeacherEditNote