import { useCallback, useEffect, useState } from 'react'
import api from '../api'
import './AdminSchoolSetup.css'

function AdminSchoolSetup() {
  const [data, setData] = useState({ classes: [], teachers: [], students: [], assignments: [] })
  const [classForm, setClassForm] = useState({ name: '', grade: '', section: 'Default' })
  const [assignment, setAssignment] = useState({ teacher_user_id: '', class_id: '', subject: '', is_class_teacher: false })
  const [enrollment, setEnrollment] = useState({ student_id: '', class_id: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const load = useCallback(async () => {
    try {
      const response = await api.get('/admin/school-setup')
      setData(response.data)
    } catch (err) { setError(err.response?.data?.error || 'Unable to load school setup.') }
  }, [])
  useEffect(() => { load() }, [load])

  const run = async (request, message, reset) => {
    try {
      setBusy(true); setError(''); setSuccess('')
      await request(); setSuccess(message); reset?.(); await load()
    } catch (err) { setError(err.response?.data?.error || 'Unable to save this change.') }
    finally { setBusy(false) }
  }

  return <div className="school-setup-page">
    <section className="school-setup-hero"><p>ADMIN CONTROL</p><h1>School Setup</h1><span>Create the structure that teacher marks, attendance, quizzes and analytics depend on.</span></section>
    {error && <div className="school-message error">{error}</div>}{success && <div className="school-message success">{success}</div>}

    <div className="school-form-grid">
      <form onSubmit={(event) => { event.preventDefault(); run(() => api.post('/admin/classes', classForm), 'Class created.', () => setClassForm({ name: '', grade: '', section: 'Default' })) }}>
        <h2>Create class</h2><label>Class name<input value={classForm.name} onChange={(event) => setClassForm({ ...classForm, name: event.target.value })} placeholder="Grade 10 A" required /></label><label>Grade<input value={classForm.grade} onChange={(event) => setClassForm({ ...classForm, grade: event.target.value })} placeholder="10" required /></label><label>Section<input value={classForm.section} onChange={(event) => setClassForm({ ...classForm, section: event.target.value })} required /></label><button disabled={busy}>Create Class</button>
      </form>
      <form onSubmit={(event) => { event.preventDefault(); run(() => api.put(`/admin/students/${enrollment.student_id}/class`, { class_id: Number(enrollment.class_id) }), 'Student enrollment updated.') }}>
        <h2>Enroll student</h2><label>Student<select value={enrollment.student_id} onChange={(event) => setEnrollment({ ...enrollment, student_id: event.target.value })} required><option value="">Select student</option>{data.students.map((item) => <option key={`${item.student_id}-${item.class_id || 0}`} value={item.student_id}>{item.full_name}{item.class_name ? ` — ${item.class_name}` : ' — Unassigned'}</option>)}</select></label><label>Class<select value={enrollment.class_id} onChange={(event) => setEnrollment({ ...enrollment, class_id: event.target.value })} required><option value="">Select class</option>{data.classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><button disabled={busy}>Save Enrollment</button>
      </form>
      <form onSubmit={(event) => { event.preventDefault(); run(() => api.post('/admin/teacher-assignments', { ...assignment, teacher_user_id: Number(assignment.teacher_user_id), class_id: Number(assignment.class_id) }), 'Teacher assignment created.', () => setAssignment({ teacher_user_id: '', class_id: '', subject: '', is_class_teacher: false })) }}>
        <h2>Assign teacher</h2><label>Teacher<select value={assignment.teacher_user_id} onChange={(event) => setAssignment({ ...assignment, teacher_user_id: event.target.value })} required><option value="">Select teacher</option>{data.teachers.map((item) => <option key={item.id} value={item.id}>{item.username}</option>)}</select></label><label>Class<select value={assignment.class_id} onChange={(event) => setAssignment({ ...assignment, class_id: event.target.value })} required><option value="">Select class</option>{data.classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Subject<input value={assignment.subject} onChange={(event) => setAssignment({ ...assignment, subject: event.target.value })} placeholder="Science" required /></label><label className="school-check"><input type="checkbox" checked={assignment.is_class_teacher} onChange={(event) => setAssignment({ ...assignment, is_class_teacher: event.target.checked })} />Make this teacher responsible for class attendance</label><button disabled={busy}>Save Assignment</button>
      </form>
    </div>

    <section className="school-list"><h2>Teacher assignments</h2>{data.assignments.length === 0 ? <p>No assignments yet.</p> : <div className="school-table-wrap"><table><thead><tr><th>Teacher</th><th>Class</th><th>Subject</th><th>Class teacher</th><th /></tr></thead><tbody>{data.assignments.map((item) => <tr key={item.id}><td>{item.teacher_name}</td><td>{item.class_name}</td><td>{item.subject}</td><td>{item.is_class_teacher ? 'Yes' : 'No'}</td><td><button onClick={() => run(() => api.delete(`/admin/teacher-assignments/${item.id}`), 'Assignment removed.')}>Remove</button></td></tr>)}</tbody></table></div>}</section>
  </div>
}

export default AdminSchoolSetup
