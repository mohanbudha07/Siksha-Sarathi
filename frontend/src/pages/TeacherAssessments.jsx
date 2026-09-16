import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'
import './TeacherAssessments.css'

const assessmentTypes = [
  ['class_test', 'Class Test'],
  ['unit_test', 'Unit Test'],
  ['terminal_exam', 'Terminal Examination'],
  ['assignment', 'Assignment'],
  ['practical', 'Practical'],
]

const today = () => {
  const date = new Date()
  const offset = date.getTimezoneOffset()
  return new Date(date.getTime() - offset * 60000).toISOString().slice(0, 10)
}

const formatDate = (value) => {
  if (!value) return 'No date'
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(value))
}

function TeacherAssessments() {
  const navigate = useNavigate()
  const [assignments, setAssignments] = useState([])
  const [assessments, setAssessments] = useState([])
  const [assignmentKey, setAssignmentKey] = useState('')
  const [form, setForm] = useState({
    title: '', assessment_type: 'class_test', assessment_date: today(),
    max_marks: '50', academic_year: '2083 BS', term: '', is_published: false,
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [deletingId, setDeletingId] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [error, setError] = useState('')

  const selectedAssignment = useMemo(
    () => assignments.find((item) => `${item.class_id}|${item.subject}` === assignmentKey),
    [assignmentKey, assignments]
  )

  const loadData = async () => {
    try {
      setLoading(true)
      setError('')
      const [analyticsResponse, assessmentResponse] = await Promise.all([
        api.get('/teacher/learning-analytics'),
        api.get('/teacher/paper-assessments'),
      ])
      const availableAssignments = analyticsResponse.data.assignments || []
      setAssignments(availableAssignments)
      setAssessments(assessmentResponse.data.assessments || [])
      if (!assignmentKey && availableAssignments[0]) {
        setAssignmentKey(`${availableAssignments[0].class_id}|${availableAssignments[0].subject}`)
      }
    } catch (err) {
      console.error('Load paper assessments error:', err)
      setError(err.response?.data?.error || 'Unable to load paper assessments.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  const updateForm = (field, value) => setForm((current) => ({ ...current, [field]: value }))

  const createAssessment = async (event) => {
    event.preventDefault()
    if (!selectedAssignment) return
    try {
      setSaving(true)
      setError('')
      const response = await api.post('/teacher/paper-assessments', {
        ...form,
        class_id: selectedAssignment.class_id,
        subject: selectedAssignment.subject,
        max_marks: Number(form.max_marks),
      })
      navigate(`/teacher/assessments/${response.data.assessment_id}/scores`)
    } catch (err) {
      console.error('Create paper assessment error:', err)
      setError(err.response?.data?.error || 'Unable to create this assessment.')
    } finally {
      setSaving(false)
    }
  }

  const deleteAssessment = async (assessment) => {
    if (!window.confirm(`Delete “${assessment.title}” and all recorded marks?`)) return
    try {
      setDeletingId(assessment.id)
      setError('')
      await api.delete(`/teacher/paper-assessments/${assessment.id}`)
      setAssessments((current) => current.filter((item) => item.id !== assessment.id))
    } catch (err) {
      setError(err.response?.data?.error || 'Unable to delete this assessment.')
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div className="paper-assessments-page">
      <section className="paper-assessment-hero">
        <div><p>PAPER-BASED LEARNING RECORDS</p><h1>Assessments & Marks</h1><span>Record school examinations, assignments, practicals and class tests for your assigned students.</span></div>
        <button onClick={() => setShowForm((current) => !current)}>{showForm ? 'Close Form' : '+ New Assessment'}</button>
      </section>

      {error && <div className="paper-assessment-error">⚠️ {error}</div>}

      {showForm && (
        <form className="paper-assessment-form" onSubmit={createAssessment}>
          <div className="paper-form-heading"><div><h2>Create assessment</h2><p>The class roster will be loaded automatically after creation.</p></div><span>Draft first, publish after checking marks</span></div>
          <div className="paper-form-grid">
            <label>Assigned class and subject<select value={assignmentKey} onChange={(event) => setAssignmentKey(event.target.value)} required><option value="">Select assignment</option>{assignments.map((item) => <option key={`${item.class_id}-${item.subject}`} value={`${item.class_id}|${item.subject}`}>{item.class_name} — {item.subject}</option>)}</select></label>
            <label>Assessment title<input value={form.title} onChange={(event) => updateForm('title', event.target.value)} placeholder="Example: First Terminal Examination" minLength="2" maxLength="150" required /></label>
            <label>Assessment type<select value={form.assessment_type} onChange={(event) => updateForm('assessment_type', event.target.value)}>{assessmentTypes.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <label>Assessment date<input type="date" value={form.assessment_date} onChange={(event) => updateForm('assessment_date', event.target.value)} required /></label>
            <label>Maximum marks<input type="number" min="0.01" max="1000" step="0.01" value={form.max_marks} onChange={(event) => updateForm('max_marks', event.target.value)} required /></label>
            <label>Academic year<input value={form.academic_year} onChange={(event) => updateForm('academic_year', event.target.value)} placeholder="Example: 2083 BS" maxLength="20" /></label>
            <label>Term<input value={form.term} onChange={(event) => updateForm('term', event.target.value)} placeholder="Example: First Term" maxLength="50" /></label>
          </div>
          <button className="paper-primary-button" disabled={saving || !assignments.length}>{saving ? 'Creating...' : 'Create & Enter Marks →'}</button>
          {!assignments.length && <p className="paper-form-warning">You need a class-subject assignment before creating assessments.</p>}
        </form>
      )}

      <section className="paper-assessment-list-section">
        <div className="paper-list-heading"><div><h2>Assessment records</h2><p>Online quiz results remain separate from these teacher-entered marks.</p></div><button onClick={loadData}>Refresh</button></div>
        {loading ? <div className="paper-empty-state">Loading assessments...</div> : assessments.length === 0 ? <div className="paper-empty-state"><strong>No paper assessments yet</strong><span>Create the first record for your assigned class.</span></div> : (
          <div className="paper-assessment-grid">
            {assessments.map((item) => (
              <article className="paper-assessment-card" key={item.id}>
                <div className="paper-card-top"><span className="paper-type-badge">{item.assessment_type.replaceAll('_', ' ')}</span><span className={item.is_published ? 'paper-published' : 'paper-draft'}>{item.is_published ? 'Published' : 'Draft'}</span></div>
                <h3>{item.title}</h3><p>{item.class_name} · {item.subject}</p>
                <dl><div><dt>Date</dt><dd>{formatDate(item.assessment_date)}</dd></div><div><dt>Maximum</dt><dd>{item.max_marks} marks</dd></div><div><dt>Recorded</dt><dd>{item.recorded_students} students</dd></div></dl>
                <div className="paper-card-actions"><button onClick={() => navigate(`/teacher/assessments/${item.id}/scores`)}>Enter / Review Marks</button><button className="paper-delete-button" onClick={() => deleteAssessment(item)} disabled={deletingId === item.id}>{deletingId === item.id ? 'Deleting...' : 'Delete'}</button></div>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

export default TeacherAssessments
