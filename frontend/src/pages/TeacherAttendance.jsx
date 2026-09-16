import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'
import './TeacherAttendance.css'

const localToday = () => {
  const now = new Date()
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000)
    .toISOString().slice(0, 10)
}

const formatDate = (value) => {
  if (!value) return 'No date'
  const normalized = /^\d{4}-\d{2}-\d{2}$/.test(value)
    ? `${value}T00:00:00`
    : value
  const date = new Date(normalized)
  if (Number.isNaN(date.getTime())) return String(value)
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' })
    .format(date)
}

function TeacherAttendance() {
  const navigate = useNavigate()
  const [classes, setClasses] = useState([])
  const [sessions, setSessions] = useState([])
  const [classId, setClassId] = useState('')
  const [attendanceDate, setAttendanceDate] = useState(localToday())
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [deletingId, setDeletingId] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [error, setError] = useState('')

  const loadAttendance = async () => {
    try {
      setLoading(true)
      setError('')
      const response = await api.get('/teacher/attendance-sessions')
      const assignedClasses = response.data.assigned_classes || []
      setClasses(assignedClasses)
      setSessions(response.data.sessions || [])
      setClassId((current) => current || String(assignedClasses[0]?.class_id || ''))
    } catch (err) {
      console.error('Load attendance error:', err)
      setError(err.response?.data?.error || 'Unable to load daily attendance.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadAttendance() }, [])

  const existingForSelection = useMemo(
    () => sessions.find((item) => (
      String(item.class_id) === classId && item.attendance_date === attendanceDate
    )),
    [attendanceDate, classId, sessions]
  )

  const createRegister = async (event) => {
    event.preventDefault()
    if (existingForSelection) {
      navigate(`/teacher/attendance/${existingForSelection.id}`)
      return
    }
    try {
      setSaving(true)
      setError('')
      const response = await api.post('/teacher/attendance-sessions', {
        class_id: Number(classId),
        attendance_date: attendanceDate,
      })
      navigate(`/teacher/attendance/${response.data.attendance_session_id}`)
    } catch (err) {
      setError(err.response?.data?.error || 'Unable to create the attendance register.')
    } finally {
      setSaving(false)
    }
  }

  const deleteRegister = async (item) => {
    if (!window.confirm(`Delete attendance for ${item.class_name} on ${formatDate(item.attendance_date)}?`)) return
    try {
      setDeletingId(item.id)
      setError('')
      await api.delete(`/teacher/attendance-sessions/${item.id}`)
      setSessions((current) => current.filter((session) => session.id !== item.id))
    } catch (err) {
      setError(err.response?.data?.error || 'Unable to delete this attendance register.')
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div className="attendance-page">
      <section className="attendance-hero">
        <div>
          <p>DAILY PAPER REGISTER</p>
          <h1>Class Attendance</h1>
          <span>Digitize the class teacher&apos;s daily paper attendance—once per class and date.</span>
        </div>
        <button onClick={() => setShowForm((current) => !current)}>
          {showForm ? 'Close Form' : '+ Take Attendance'}
        </button>
      </section>

      {error && <div className="attendance-message error">{error}</div>}

      {showForm && (
        <form className="attendance-create-card" onSubmit={createRegister}>
          <div>
            <h2>Open daily register</h2>
            <p>Select your assigned class and the date from the paper register.</p>
          </div>
          <label>
            Class
            <select value={classId} onChange={(event) => setClassId(event.target.value)} required>
              <option value="">Select class</option>
              {classes.map((item) => (
                <option key={item.class_id} value={item.class_id}>{item.class_name}</option>
              ))}
            </select>
          </label>
          <label>
            Attendance date
            <input type="date" value={attendanceDate} onChange={(event) => setAttendanceDate(event.target.value)} required />
          </label>
          <button className="attendance-primary" disabled={saving || !classId}>
            {saving ? 'Opening...' : existingForSelection ? 'Open Existing Register' : 'Create Register'}
          </button>
          {!classes.length && <span className="attendance-warning">You must be designated as a class teacher before recording attendance.</span>}
        </form>
      )}

      <section className="attendance-list-card">
        <div className="attendance-section-heading">
          <div><h2>Daily registers</h2><p>Each class can have only one register per date.</p></div>
          <button onClick={loadAttendance}>Refresh</button>
        </div>
        {loading ? (
          <div className="attendance-empty">Loading attendance...</div>
        ) : sessions.length === 0 ? (
          <div className="attendance-empty"><strong>No attendance recorded yet</strong><span>Open the first daily register from the paper record.</span></div>
        ) : (
          <div className="attendance-card-grid">
            {sessions.map((item) => (
              <article className="attendance-card" key={item.id}>
                <div className="attendance-card-date"><span>{item.class_name}</span><strong>{formatDate(item.attendance_date)}</strong></div>
                <div className="attendance-count-grid">
                  <span><strong>{item.present_count}</strong>Present</span>
                  <span><strong>{item.absent_count}</strong>Absent</span>
                  <span><strong>{item.late_count}</strong>Late</span>
                  <span><strong>{item.excused_count}</strong>Excused</span>
                </div>
                <p>{item.recorded_students ? `${item.recorded_students} students recorded` : 'Register not completed'}</p>
                <div className="attendance-card-actions">
                  <button onClick={() => navigate(`/teacher/attendance/${item.id}`)}>Open Register</button>
                  <button className="attendance-delete" onClick={() => deleteRegister(item)} disabled={deletingId === item.id}>{deletingId === item.id ? 'Deleting...' : 'Delete'}</button>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

export default TeacherAttendance
