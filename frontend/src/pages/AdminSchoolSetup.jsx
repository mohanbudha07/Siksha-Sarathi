import { useCallback, useEffect, useState } from 'react'
import api from '../api'
import './AdminSchoolSetup.css'

function AdminSchoolSetup() {
  const [data, setData] = useState({ classes: [], subjects: [], teachers: [], students: [], assignments: [], current_class_teachers: [], class_teacher_history: [] })
  const [classForm, setClassForm] = useState({ name: '', grade: '', section: 'Default' })
  const [subjectForm, setSubjectForm] = useState({ name: '', code: '' })
  const [assignment, setAssignment] = useState({ teacher_user_id: '', class_id: '', subject_id: '' })
  const [classTeacher, setClassTeacher] = useState({ teacher_user_id: '', class_id: '', academic_year: '' })
  const [enrollment, setEnrollment] = useState({ student_id: '', class_id: '', academic_year: '', transfer_note: '' })
  const [historyStudentId, setHistoryStudentId] = useState('')
  const [enrollmentHistory, setEnrollmentHistory] = useState([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [activeArea, setActiveArea] = useState('structure')

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

  const selectedStudent = data.students.find((item) => String(item.student_id) === enrollment.student_id)
  const selectedClassId = Number(enrollment.class_id)
  const isTransfer = Boolean(selectedStudent?.class_id && selectedClassId && selectedStudent.class_id !== selectedClassId)
  const alreadyEnrolled = Boolean(selectedStudent?.class_id && selectedClassId && selectedStudent.class_id === selectedClassId)

  const loadEnrollmentHistory = async () => {
    if (!historyStudentId) return
    try {
      setHistoryLoading(true)
      setError('')
      const response = await api.get(`/admin/students/${historyStudentId}/enrollment-history`)
      setEnrollmentHistory(response.data.history)
    } catch (err) {
      setError(err.response?.data?.error || 'Unable to load enrollment history.')
      setEnrollmentHistory([])
    } finally { setHistoryLoading(false) }
  }

  return <div className="school-setup-page">
    <section className="school-setup-hero"><p>ADMIN CONTROL</p><h1>School Setup</h1><span>Create the structure that teacher marks, attendance, quizzes and analytics depend on.</span></section>
    {error && <div className="school-message error">{error}</div>}{success && <div className="school-message success">{success}</div>}

    <nav className="school-setup-tabs" aria-label="School setup areas">
      {[
        ['structure', 'Classes & Subjects'],
        ['assignments', 'Teacher Assignments'],
        ['students', 'Student Enrollment'],
      ].map(([area, label]) => (
        <button type="button" key={area} className={activeArea === area ? 'active' : ''} aria-pressed={activeArea === area} onClick={() => setActiveArea(area)}>{label}</button>
      ))}
    </nav>

    <div className="school-form-grid">
      <form hidden={activeArea !== 'structure'} onSubmit={(event) => { event.preventDefault(); run(() => api.post('/admin/classes', classForm), 'Class created.', () => setClassForm({ name: '', grade: '', section: 'Default' })) }}>
        <h2>Create class</h2><label>Class name<input value={classForm.name} onChange={(event) => setClassForm({ ...classForm, name: event.target.value })} placeholder="Grade 10 A" required /></label><label>Grade<input value={classForm.grade} onChange={(event) => setClassForm({ ...classForm, grade: event.target.value })} placeholder="10" required /></label><label>Section<input value={classForm.section} onChange={(event) => setClassForm({ ...classForm, section: event.target.value })} required /></label><button disabled={busy}>Create Class</button>
      </form>
      <form hidden={activeArea !== 'structure'} onSubmit={(event) => { event.preventDefault(); run(() => api.post('/admin/subjects', subjectForm), 'Subject created.', () => setSubjectForm({ name: '', code: '' })) }}>
        <h2>Create subject</h2><label>Subject name<input value={subjectForm.name} onChange={(event) => setSubjectForm({ ...subjectForm, name: event.target.value })} placeholder="Science" maxLength="100" required /></label><label>Code<input value={subjectForm.code} onChange={(event) => setSubjectForm({ ...subjectForm, code: event.target.value })} placeholder="SCI" maxLength="30" /></label><button disabled={busy}>Create Subject</button>
      </form>
      <form hidden={activeArea !== 'students'} onSubmit={(event) => {
        event.preventDefault()
        if (isTransfer && !window.confirm(`Transfer ${selectedStudent.full_name} from ${selectedStudent.class_name} to ${data.classes.find((item) => item.id === selectedClassId)?.name}?`)) return
        run(() => api.put(`/admin/students/${enrollment.student_id}/class`, {
          class_id: selectedClassId,
          academic_year: enrollment.academic_year,
          transfer_note: enrollment.transfer_note,
        }), isTransfer ? 'Student transferred.' : alreadyEnrolled ? 'Student is already enrolled in this class.' : 'Student enrolled.')
      }}>
        <h2>Student Enrollment / Transfer</h2><label>Student<select value={enrollment.student_id} onChange={(event) => setEnrollment({ ...enrollment, student_id: event.target.value })} required><option value="">Select student</option>{data.students.map((item) => <option key={item.student_id} value={item.student_id}>{item.full_name}{item.class_name ? ` — ${item.class_name}` : ' — Unassigned'}</option>)}</select></label><label>Current class<input value={selectedStudent?.class_name || 'Unassigned'} readOnly /></label><label>New class<select value={enrollment.class_id} onChange={(event) => setEnrollment({ ...enrollment, class_id: event.target.value })} required><option value="">Select class</option>{data.classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Academic year<input value={enrollment.academic_year} onChange={(event) => setEnrollment({ ...enrollment, academic_year: event.target.value })} placeholder="2083/84" maxLength="20" /></label><label>Transfer note<input value={enrollment.transfer_note} onChange={(event) => setEnrollment({ ...enrollment, transfer_note: event.target.value })} maxLength="255" /></label><button disabled={busy || !enrollment.student_id || !enrollment.class_id}>{isTransfer ? 'Transfer Student' : alreadyEnrolled ? 'Already Enrolled' : 'Enroll Student'}</button>
      </form>
      <form hidden={activeArea !== 'assignments'} onSubmit={(event) => { event.preventDefault(); run(() => api.post('/admin/teacher-assignments', { ...assignment, teacher_user_id: Number(assignment.teacher_user_id), class_id: Number(assignment.class_id), subject_id: Number(assignment.subject_id) }), 'Subject assignment saved.', () => setAssignment({ teacher_user_id: '', class_id: '', subject_id: '' })) }}>
        <h2>Assign subject teacher</h2><label>Teacher<select value={assignment.teacher_user_id} onChange={(event) => setAssignment({ ...assignment, teacher_user_id: event.target.value })} required><option value="">Select teacher</option>{data.teachers.map((item) => <option key={item.id} value={item.id}>{item.username}</option>)}</select></label><label>Class<select value={assignment.class_id} onChange={(event) => setAssignment({ ...assignment, class_id: event.target.value })} required><option value="">Select class</option>{data.classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Subject<select value={assignment.subject_id} onChange={(event) => setAssignment({ ...assignment, subject_id: event.target.value })} required><option value="">Select subject</option>{data.subjects.map((item) => <option key={item.id} value={item.id}>{item.name}{item.code ? ` (${item.code})` : ''}</option>)}</select></label><button disabled={busy}>Save Subject Assignment</button>
      </form>
      <form hidden={activeArea !== 'assignments'} onSubmit={(event) => { event.preventDefault(); run(() => api.post('/admin/class-teacher-assignments', { ...classTeacher, teacher_user_id: Number(classTeacher.teacher_user_id), class_id: Number(classTeacher.class_id) }), 'Class teacher assignment saved.', () => setClassTeacher({ teacher_user_id: '', class_id: '', academic_year: '' })) }}>
        <h2>Assign class teacher</h2><label>Teacher<select value={classTeacher.teacher_user_id} onChange={(event) => setClassTeacher({ ...classTeacher, teacher_user_id: event.target.value })} required><option value="">Select teacher</option>{data.teachers.map((item) => <option key={item.id} value={item.id}>{item.username}</option>)}</select></label><label>Class<select value={classTeacher.class_id} onChange={(event) => setClassTeacher({ ...classTeacher, class_id: event.target.value })} required><option value="">Select class</option>{data.classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Academic year<input value={classTeacher.academic_year} onChange={(event) => setClassTeacher({ ...classTeacher, academic_year: event.target.value })} placeholder="2083/84" maxLength="20" required /></label><button disabled={busy}>Save Class Teacher</button>
      </form>
    </div>

    <section hidden={activeArea !== 'structure'} className="school-list"><h2>Teaching structure</h2><div className="school-table-wrap"><table><thead><tr><th>Grade</th><th>Section</th><th>Class</th><th>Class Teacher</th><th>Subject</th><th>Subject Teacher</th></tr></thead><tbody>{data.classes.flatMap((classItem) => {
      const subjectRows = data.assignments.filter((item) => item.class_id === classItem.id)
      const rows = subjectRows.length ? subjectRows : [null]
      const classTeacherName = data.current_class_teachers.find((item) => item.class_id === classItem.id)?.teacher_name || 'Unassigned'
      return rows.map((subjectItem, index) => <tr key={`${classItem.id}-${subjectItem?.id || 'unassigned'}`}><td>{classItem.grade}</td><td>{classItem.section || '—'}</td><td>{classItem.name}</td>{index === 0 && <td rowSpan={rows.length}>{classTeacherName}</td>}<td>{subjectItem?.subject || 'Unassigned'}</td><td>{subjectItem?.teacher_name || 'Unassigned'}</td></tr>)
    })}</tbody></table></div></section>

    <section hidden={activeArea !== 'students'} className="school-list"><h2>Student enrollment history</h2><div className="history-controls"><label>Student<select value={historyStudentId} onChange={(event) => { setHistoryStudentId(event.target.value); setEnrollmentHistory([]) }}><option value="">Select student</option>{data.students.map((item) => <option key={item.student_id} value={item.student_id}>{item.full_name}</option>)}</select></label><button disabled={!historyStudentId || historyLoading} onClick={loadEnrollmentHistory}>{historyLoading ? 'Loading…' : 'View history'}</button></div>{enrollmentHistory.length > 0 && <div className="school-table-wrap"><table><thead><tr><th>Class</th><th>Academic year</th><th>Started</th><th>Ended</th><th>Status</th><th>Transfer note</th></tr></thead><tbody>{enrollmentHistory.map((item) => <tr key={item.id}><td>{item.class_name} ({item.grade}{item.section ? ` / ${item.section}` : ''})</td><td>{item.academic_year || '—'}</td><td>{item.started_at || '—'}</td><td>{item.ended_at || '—'}</td><td>{item.current ? 'Current' : 'Historical'}</td><td>{item.transfer_note || '—'}</td></tr>)}</tbody></table></div>}</section>

    <section hidden={activeArea !== 'structure'} className="school-list"><h2>Subjects</h2>{data.subjects.length === 0 ? <p>No subjects yet.</p> : <div className="school-table-wrap"><table><thead><tr><th>Name</th><th>Code</th></tr></thead><tbody>{data.subjects.map((item) => <tr key={item.id}><td>{item.name}</td><td>{item.code || '—'}</td></tr>)}</tbody></table></div>}</section>
    <section hidden={activeArea !== 'assignments'} className="school-list"><h2>Subject teacher assignments</h2>{data.assignments.length === 0 ? <p>No assignments yet.</p> : <div className="school-table-wrap"><table><thead><tr><th>Teacher</th><th>Class</th><th>Subject</th><th /></tr></thead><tbody>{data.assignments.map((item) => <tr key={item.id}><td>{item.teacher_name}</td><td>{item.class_name}</td><td>{item.subject}</td><td><button onClick={() => run(() => api.delete(`/admin/teacher-assignments/${item.id}`), 'Assignment removed.')}>Remove</button></td></tr>)}</tbody></table></div>}</section>
    <section hidden={activeArea !== 'assignments'} className="school-list"><h2>Current class teachers</h2>{data.current_class_teachers.length === 0 ? <p>No current class teachers yet.</p> : <div className="school-table-wrap"><table><thead><tr><th>Class</th><th>Teacher</th><th>Academic year</th><th>Started</th><th>Status</th><th>Action</th></tr></thead><tbody>{data.current_class_teachers.map((item) => <tr key={item.id}><td>{item.class_name}</td><td>{item.teacher_name}</td><td>{item.academic_year || 'Unspecified'}</td><td>{item.started_at || '—'}</td><td>Current</td><td><button onClick={() => run(() => api.post(`/admin/class-teacher-assignments/${item.id}/end`), 'Class teacher responsibility ended.')}>End Responsibility</button></td></tr>)}</tbody></table></div>}</section>
    <section hidden={activeArea !== 'assignments'} className="school-list"><h2>Class teacher history</h2>{data.class_teacher_history.length === 0 ? <p>No class teacher history yet.</p> : <div className="school-table-wrap"><table><thead><tr><th>Class</th><th>Teacher</th><th>Academic year</th><th>Started</th><th>Ended</th><th>Status</th></tr></thead><tbody>{data.class_teacher_history.map((item) => <tr key={item.id}><td>{item.class_name}</td><td>{item.teacher_name}</td><td>{item.academic_year || 'Unspecified'}</td><td>{item.started_at || '—'}</td><td>{item.ended_at || '—'}</td><td>{item.current ? 'Current' : 'Historical'}</td></tr>)}</tbody></table></div>}</section>
  </div>
}

export default AdminSchoolSetup
