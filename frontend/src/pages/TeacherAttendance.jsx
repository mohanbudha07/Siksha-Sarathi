import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'
import './TeacherAttendance.css'

const currentMonth = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000)
  .toISOString().slice(0, 7)
const monthLabel = (value) => new Intl.DateTimeFormat(undefined, {
  month: 'long', year: 'numeric',
}).format(new Date(`${String(value).slice(0, 7)}-01T00:00:00`))

function TeacherAttendance() {
  const navigate = useNavigate()
  const [classes, setClasses] = useState([])
  const [summaries, setSummaries] = useState([])
  const [classId, setClassId] = useState('')
  const [month, setMonth] = useState(currentMonth())
  const [schoolDays, setSchoolDays] = useState('22')
  const [showForm, setShowForm] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [deletingId, setDeletingId] = useState(null)
  const [error, setError] = useState('')

  const loadAttendance = async () => {
    try {
      setLoading(true); setError('')
      const response = await api.get('/teacher/monthly-attendance')
      const assigned = response.data.assigned_classes || []
      setClasses(assigned); setSummaries(response.data.summaries || [])
      setClassId((value) => value || String(assigned[0]?.class_id || ''))
    } catch (err) {
      setError(err.response?.data?.error || 'Unable to load monthly attendance.')
    } finally { setLoading(false) }
  }
  useEffect(() => { loadAttendance() }, [])

  const existing = useMemo(() => summaries.find((item) =>
    String(item.class_id) === classId
      && String(item.attendance_month).slice(0, 7) === month
  ), [classId, month, summaries])

  const openMonth = async (event) => {
    event.preventDefault()
    if (existing) return navigate(`/teacher/attendance/${existing.id}`)
    try {
      setSaving(true); setError('')
      const response = await api.post('/teacher/monthly-attendance', {
        class_id: Number(classId), attendance_month: month,
        total_school_days: Number(schoolDays),
      })
      navigate(`/teacher/attendance/${response.data.attendance_summary_id}`)
    } catch (err) {
      setError(err.response?.data?.error || 'Unable to create monthly attendance.')
    } finally { setSaving(false) }
  }

  const remove = async (item) => {
    if (!window.confirm(`Delete ${monthLabel(item.attendance_month)} attendance for ${item.class_name}?`)) return
    try {
      setDeletingId(item.id); setError('')
      await api.delete(`/teacher/monthly-attendance/${item.id}`)
      setSummaries((items) => items.filter((summary) => summary.id !== item.id))
    } catch (err) {
      setError(err.response?.data?.error || 'Unable to delete monthly attendance.')
    } finally { setDeletingId(null) }
  }

  return <div className="attendance-page">
    <section className="attendance-hero"><div><p>MONTHLY PAPER REGISTER</p><h1>Class Attendance</h1><span>Copy one monthly total from the paper register instead of entering attendance every day.</span></div><button onClick={() => setShowForm((value) => !value)}>{showForm ? 'Close Form' : '+ Add Monthly Attendance'}</button></section>
    {error && <div className="attendance-message error">{error}</div>}
    {showForm && <form className="attendance-create-card" onSubmit={openMonth}>
      <div><h2>Open monthly register</h2><p>Enter the month and actual school days from the paper register.</p></div>
      <label>Class<select value={classId} onChange={(event) => setClassId(event.target.value)} required><option value="">Select class</option>{classes.map((item) => <option key={item.class_id} value={item.class_id}>{item.class_name}</option>)}</select></label>
      <label>Month<input type="month" value={month} onChange={(event) => setMonth(event.target.value)} required /></label>
      <label>Total school days<input type="number" min="1" max="31" step="1" value={schoolDays} onChange={(event) => setSchoolDays(event.target.value)} required /></label>
      <button className="attendance-primary" disabled={saving || !classId}>{saving ? 'Opening...' : existing ? 'Open Existing Month' : 'Create Monthly Register'}</button>
    </form>}
    <section className="attendance-list-card"><div className="attendance-section-heading"><div><h2>Monthly registers</h2><p>One summary per class and month.</p></div><button onClick={loadAttendance}>Refresh</button></div>
      {loading ? <div className="attendance-empty">Loading attendance...</div> : summaries.length === 0 ? <div className="attendance-empty"><strong>No monthly attendance yet</strong><span>Add the first month from the paper register.</span></div> : <div className="attendance-card-grid">{summaries.map((item) => {
        const possible = item.total_school_days * item.recorded_students
        const rate = possible ? Math.round(1000 * item.present_days / possible) / 10 : 0
        return <article className="attendance-card" key={item.id}><div className="attendance-card-date"><span>{item.class_name}</span><strong>{monthLabel(item.attendance_month)}</strong></div><div className="attendance-count-grid"><span><strong>{item.total_school_days}</strong>School days</span><span><strong>{item.recorded_students}</strong>Students</span><span><strong>{item.absent_days}</strong>Absences</span><span><strong>{rate}%</strong>Attendance</span></div><p>{item.recorded_students ? 'Monthly totals recorded' : 'Register not completed'}</p><div className="attendance-card-actions"><button onClick={() => navigate(`/teacher/attendance/${item.id}`)}>Open Month</button><button className="attendance-delete" onClick={() => remove(item)} disabled={deletingId === item.id}>{deletingId === item.id ? 'Deleting...' : 'Delete'}</button></div></article>
      })}</div>}
    </section>
  </div>
}

export default TeacherAttendance
