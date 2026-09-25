import { useCallback, useEffect, useState } from 'react'
import api from '../api'
import './AdminSchoolSetup.css'

function AdminSchoolSetup() {
  const [data, setData] = useState({ classes: [], subjects: [], teachers: [], students: [], assignments: [], current_class_teachers: [], class_teacher_history: [] })
  const [classForm, setClassForm] = useState({ name: '', grade: '', section: 'Default' })
  const [subjectForm, setSubjectForm] = useState({ name: '', code: '' })
  const [assignment, setAssignment] = useState({ teacher_user_id: '', class_id: '', subject_id: '' })
  const [classTeacher, setClassTeacher] = useState({ teacher_user_id: '', class_id: '', academic_year: '' })
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
      <form onSubmit={(event) => { event.preventDefault(); run(() => api.post('/admin/subjects', subjectForm), 'Subject created.', () => setSubjectForm({ name: '', code: '' })) }}>
        <h2>Create subject</h2><label>Subject name<input value={subjectForm.name} onChange={(event) => setSubjectForm({ ...subjectForm, name: event.target.value })} placeholder="Science" maxLength="100" required /></label><label>Code<input value={subjectForm.code} onChange={(event) => setSubjectForm({ ...subjectForm, code: event.target.value })} placeholder="SCI" maxLength="30" /></label><button disabled={busy}>Create Subject</button>
      </form>
      <form onSubmit={(event) => { event.preventDefault(); run(() => api.put(`/admin/students/${enrollment.student_id}/class`, { class_id: Number(enrollment.class_id) }), 'Student enrollment updated.') }}>
        <h2>Enroll student</h2><label>Student<select value={enrollment.student_id} onChange={(event) => setEnrollment({ ...enrollment, student_id: event.target.value })} required><option value="">Select student</option>{data.students.map((item) => <option key={`${item.student_id}-${item.class_id || 0}`} value={item.student_id}>{item.full_name}{item.class_name ? ` — ${item.class_name}` : ' — Unassigned'}</option>)}</select></label><label>Class<select value={enrollment.class_id} onChange={(event) => setEnrollment({ ...enrollment, class_id: event.target.value })} required><option value="">Select class</option>{data.classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><button disabled={busy}>Save Enrollment</button>
      </form>
      <form onSubmit={(event) => { event.preventDefault(); run(() => api.post('/admin/teacher-assignments', { ...assignment, teacher_user_id: Number(assignment.teacher_user_id), class_id: Number(assignment.class_id), subject_id: Number(assignment.subject_id) }), 'Subject assignment saved.', () => setAssignment({ teacher_user_id: '', class_id: '', subject_id: '' })) }}>
        <h2>Assign subject teacher</h2><label>Teacher<select value={assignment.teacher_user_id} onChange={(event) => setAssignment({ ...assignment, teacher_user_id: event.target.value })} required><option value="">Select teacher</option>{data.teachers.map((item) => <option key={item.id} value={item.id}>{item.username}</option>)}</select></label><label>Class<select value={assignment.class_id} onChange={(event) => setAssignment({ ...assignment, class_id: event.target.value })} required><option value="">Select class</option>{data.classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Subject<select value={assignment.subject_id} onChange={(event) => setAssignment({ ...assignment, subject_id: event.target.value })} required><option value="">Select subject</option>{data.subjects.map((item) => <option key={item.id} value={item.id}>{item.name}{item.code ? ` (${item.code})` : ''}</option>)}</select></label><button disabled={busy}>Save Subject Assignment</button>
      </form>
      <form onSubmit={(event) => { event.preventDefault(); run(() => api.post('/admin/class-teacher-assignments', { ...classTeacher, teacher_user_id: Number(classTeacher.teacher_user_id), class_id: Number(classTeacher.class_id) }), 'Class teacher assignment saved.', () => setClassTeacher({ teacher_user_id: '', class_id: '', academic_year: '' })) }}>
        <h2>Assign class teacher</h2><label>Teacher<select value={classTeacher.teacher_user_id} onChange={(event) => setClassTeacher({ ...classTeacher, teacher_user_id: event.target.value })} required><option value="">Select teacher</option>{data.teachers.map((item) => <option key={item.id} value={item.id}>{item.username}</option>)}</select></label><label>Class<select value={classTeacher.class_id} onChange={(event) => setClassTeacher({ ...classTeacher, class_id: event.target.value })} required><option value="">Select class</option>{data.classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Academic year<input value={classTeacher.academic_year} onChange={(event) => setClassTeacher({ ...classTeacher, academic_year: event.target.value })} placeholder="2083/84" maxLength="20" required /></label><button disabled={busy}>Save Class Teacher</button>
      </form>
    </div>

    <section className="school-list"><h2>Subjects</h2>{data.subjects.length === 0 ? <p>No subjects yet.</p> : <div className="school-table-wrap"><table><thead><tr><th>Name</th><th>Code</th></tr></thead><tbody>{data.subjects.map((item) => <tr key={item.id}><td>{item.name}</td><td>{item.code || '—'}</td></tr>)}</tbody></table></div>}</section>
    <section className="school-list"><h2>Subject teacher assignments</h2>{data.assignments.length === 0 ? <p>No assignments yet.</p> : <div className="school-table-wrap"><table><thead><tr><th>Teacher</th><th>Class</th><th>Subject</th><th /></tr></thead><tbody>{data.assignments.map((item) => <tr key={item.id}><td>{item.teacher_name}</td><td>{item.class_name}</td><td>{item.subject}</td><td><button onClick={() => run(() => api.delete(`/admin/teacher-assignments/${item.id}`), 'Assignment removed.')}>Remove</button></td></tr>)}</tbody></table></div>}</section>
    <section className="school-list"><h2>Current class teachers</h2>{data.current_class_teachers.length === 0 ? <p>No current class teachers yet.</p> : <div className="school-table-wrap"><table><thead><tr><th>Class</th><th>Teacher</th><th>Academic year</th><th>Started</th><th>Status</th><th>Action</th></tr></thead><tbody>{data.current_class_teachers.map((item) => <tr key={item.id}><td>{item.class_name}</td><td>{item.teacher_name}</td><td>{item.academic_year || 'Unspecified'}</td><td>{item.started_at || '—'}</td><td>Current</td><td><button onClick={() => run(() => api.post(`/admin/class-teacher-assignments/${item.id}/end`), 'Class teacher responsibility ended.')}>End Responsibility</button></td></tr>)}</tbody></table></div>}</section>
    <section className="school-list"><h2>Class teacher history</h2>{data.class_teacher_history.length === 0 ? <p>No class teacher history yet.</p> : <div className="school-table-wrap"><table><thead><tr><th>Class</th><th>Teacher</th><th>Academic year</th><th>Started</th><th>Ended</th><th>Status</th></tr></thead><tbody>{data.class_teacher_history.map((item) => <tr key={item.id}><td>{item.class_name}</td><td>{item.teacher_name}</td><td>{item.academic_year || 'Unspecified'}</td><td>{item.started_at || '—'}</td><td>{item.ended_at || '—'}</td><td>{item.current ? 'Current' : 'Historical'}</td></tr>)}</tbody></table></div>}</section>
  </div>
}

export default AdminSchoolSetup
