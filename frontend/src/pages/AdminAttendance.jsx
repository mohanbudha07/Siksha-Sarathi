import { useCallback, useEffect, useState } from 'react'
import api from '../api'
import './AdminAttendance.css'

const formatMonth = (value) => new Intl.DateTimeFormat(undefined, {
  month: 'long', year: 'numeric',
}).format(new Date(`${String(value).slice(0, 7)}-01T00:00:00`))

function AdminAttendance() {
  const [classes, setClasses] = useState([])
  const [summaries, setSummaries] = useState([])
  const [classId, setClassId] = useState('')
  const [month, setMonth] = useState('')
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      setLoading(true); setError(''); setSelected(null)
      const response = await api.get('/admin/attendance', {
        params: { class_id: classId || undefined, month: month || undefined },
      })
      setClasses(response.data.classes || [])
      setSummaries(response.data.summaries || [])
    } catch (err) {
      setError(err.response?.data?.error || 'Unable to load attendance overview.')
    } finally { setLoading(false) }
  }, [classId, month])
  useEffect(() => { load() }, [load])

  const openRegister = async (id) => {
    try {
      setError('')
      const response = await api.get(`/admin/attendance/${id}`)
      setSelected(response.data)
    } catch (err) {
      setError(err.response?.data?.error || 'Unable to load this register.')
    }
  }

  return <div className="admin-attendance-page">
    <header className="admin-attendance-heading"><div><p>SCHOOL RECORDS</p><h1>Attendance Overview</h1><span>Read-only monthly register oversight.</span></div></header>
    {error && <div className="admin-attendance-error">{error}</div>}
    <section className="admin-attendance-filters" aria-label="Attendance filters">
      <label>Class<select value={classId} onChange={(event) => setClassId(event.target.value)}><option value="">All classes</option>{classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <label>Month<input type="month" value={month} onChange={(event) => setMonth(event.target.value)} /></label>
      <button type="button" onClick={load}>Apply filters</button>
    </section>
    <section className="admin-attendance-section"><div className="admin-attendance-section-heading"><h2>Monthly registers</h2><span>{summaries.length} register{summaries.length === 1 ? '' : 's'}</span></div>
      {loading ? <p className="admin-attendance-empty">Loading attendance registers...</p> : summaries.length === 0 ? <p className="admin-attendance-empty">No attendance registers match these filters.</p> : <div className="admin-attendance-table-wrap"><table><thead><tr><th>Class</th><th>Month</th><th>Students</th><th>School days</th><th>Attendance</th><th>Class teacher</th><th>Created by</th><th /></tr></thead><tbody>{summaries.map((item) => <tr key={item.id}><td><strong>{item.class_name}</strong><small>Grade {item.grade} · Section {item.section}</small></td><td>{formatMonth(item.attendance_month)}</td><td>{item.recorded_students}</td><td>{item.total_school_days}</td><td>{item.attendance_percent === null ? '—' : `${item.attendance_percent}%`}</td><td>{item.class_teacher || 'Unassigned'}</td><td>{item.created_by || 'Unknown'}</td><td><button type="button" onClick={() => openRegister(item.id)}>View register</button></td></tr>)}</tbody></table></div>}
    </section>
    {selected && <section className="admin-attendance-section admin-attendance-detail"><div className="admin-attendance-section-heading"><div><h2>{selected.summary.class_name} · {formatMonth(selected.summary.attendance_month)}</h2><p>{selected.summary.class_teacher || 'Unassigned'} · Created by {selected.summary.created_by || 'Unknown'} · {selected.summary.total_school_days} school days</p></div><button type="button" onClick={() => setSelected(null)}>Close</button></div>
      {selected.students.length === 0 ? <p className="admin-attendance-empty">No student records have been saved for this register.</p> : <div className="admin-attendance-table-wrap"><table><thead><tr><th>Student</th><th>Present</th><th>Absent</th><th>Percentage</th><th>Note</th></tr></thead><tbody>{selected.students.map((student) => <tr key={student.student_id}><td>{student.full_name}</td><td>{student.present_days}</td><td>{student.absent_days}</td><td>{student.attendance_percent === null ? '—' : `${student.attendance_percent}%`}</td><td>{student.note || '—'}</td></tr>)}</tbody></table></div>}
    </section>}
  </div>
}

export default AdminAttendance