import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import api from '../api'
import './TeacherAttendance.css'

const statuses = [
  ['present', 'Present'],
  ['absent', 'Absent'],
  ['late', 'Late'],
  ['excused', 'Excused'],
]

function TeacherAttendanceRegister() {
  const { attendanceId } = useParams()
  const navigate = useNavigate()
  const [attendance, setAttendance] = useState(null)
  const [records, setRecords] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const loadRegister = useCallback(async () => {
    try {
      setLoading(true)
      setError('')
      const response = await api.get(`/teacher/attendance-sessions/${attendanceId}`)
      setAttendance(response.data.session)
      setRecords((response.data.students || []).map((student) => ({
        student_id: student.student_id,
        full_name: student.full_name,
        grade: student.grade,
        status: student.status || 'present',
        note: student.note || '',
      })))
    } catch (err) {
      setError(err.response?.data?.error || 'Unable to load this attendance register.')
    } finally {
      setLoading(false)
    }
  }, [attendanceId])

  useEffect(() => { loadRegister() }, [loadRegister])

  const counts = useMemo(() => records.reduce((summary, record) => {
    summary[record.status] = (summary[record.status] || 0) + 1
    return summary
  }, { present: 0, absent: 0, late: 0, excused: 0 }), [records])

  const updateRecord = (studentId, field, value) => {
    setRecords((current) => current.map((record) => (
      record.student_id === studentId ? { ...record, [field]: value } : record
    )))
    setMessage('')
  }

  const markAllPresent = () => {
    setRecords((current) => current.map((record) => ({ ...record, status: 'present' })))
    setMessage('')
  }

  const saveRegister = async () => {
    try {
      setSaving(true)
      setError('')
      setMessage('')
      await api.put(`/teacher/attendance-sessions/${attendanceId}/records`, {
        records: records.map(({ student_id, status, note }) => ({ student_id, status, note })),
      })
      setMessage('Daily attendance saved successfully.')
    } catch (err) {
      setError(err.response?.data?.error || 'Unable to save daily attendance.')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="attendance-page-state">Loading register...</div>
  if (!attendance) return <div className="attendance-page-state error">{error || 'Attendance register not found.'}</div>

  return (
    <div className="attendance-page attendance-register-page">
      <button className="attendance-back" onClick={() => navigate('/teacher/attendance')}>← Back to Attendance</button>
      <section className="attendance-register-hero">
        <div><p>DAILY CLASS REGISTER</p><h1>{attendance.class_name}</h1><span>{attendance.attendance_date}</span></div>
        <button onClick={markAllPresent}>Mark All Present</button>
      </section>

      {error && <div className="attendance-message error">{error}</div>}
      {message && <div className="attendance-message success">{message}</div>}

      <section className="attendance-summary">
        {statuses.map(([value, label]) => <article key={value} className={`status-${value}`}><span>{label}</span><strong>{counts[value]}</strong></article>)}
      </section>

      <section className="attendance-roster-card">
        <div className="attendance-section-heading"><div><h2>Student roster</h2><p>Every enrolled student must have one attendance status.</p></div><span>{records.length} students</span></div>
        {!records.length ? <div className="attendance-empty">No students are enrolled in this class.</div> : (
          <div className="attendance-table-wrap">
            <table className="attendance-table">
              <thead><tr><th>#</th><th>Student</th><th>Status</th><th>Optional note</th></tr></thead>
              <tbody>
                {records.map((record, index) => (
                  <tr key={record.student_id} className={`attendance-row-${record.status}`}>
                    <td>{index + 1}</td>
                    <td><strong>{record.full_name}</strong><small>Grade {record.grade}</small></td>
                    <td><select value={record.status} onChange={(event) => updateRecord(record.student_id, 'status', event.target.value)}>{statuses.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></td>
                    <td><input value={record.note} onChange={(event) => updateRecord(record.student_id, 'note', event.target.value)} maxLength="255" placeholder="Reason or follow-up note" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="attendance-save-bar"><p>Check the paper register before saving.</p><button className="attendance-primary" onClick={saveRegister} disabled={saving || !records.length}>{saving ? 'Saving...' : 'Save Daily Attendance'}</button></div>
      </section>
    </div>
  )
}

export default TeacherAttendanceRegister
