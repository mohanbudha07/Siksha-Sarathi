import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import api from '../api'
import './TeacherAttendance.css'

const monthLabel = (value) => new Intl.DateTimeFormat(undefined, {
  month: 'long', year: 'numeric',
}).format(new Date(`${String(value).slice(0, 7)}-01T00:00:00`))

function TeacherAttendanceRegister() {
  const { attendanceId } = useParams()
  const navigate = useNavigate()
  const [summary, setSummary] = useState(null)
  const [records, setRecords] = useState([])
  const [schoolDays, setSchoolDays] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const loadRegister = useCallback(async () => {
    try {
      setLoading(true); setError('')
      const response = await api.get(`/teacher/monthly-attendance/${attendanceId}`)
      setSummary(response.data.summary)
      setSchoolDays(String(response.data.summary.total_school_days))
      setRecords((response.data.students || []).map((student) => ({
        ...student, present_days: student.present_days ?? '', note: student.note || '',
      })))
    } catch (err) {
      setError(err.response?.data?.error || 'Unable to load monthly attendance.')
    } finally { setLoading(false) }
  }, [attendanceId])
  useEffect(() => { loadRegister() }, [loadRegister])

  const totals = useMemo(() => {
    const entered = records.filter((item) => item.present_days !== '')
    const present = entered.reduce((sum, item) => sum + Number(item.present_days), 0)
    const total = summary ? entered.length * summary.total_school_days : 0
    return { entered: entered.length, present, absent: total - present, rate: total ? Math.round(1000 * present / total) / 10 : 0 }
  }, [records, summary])

  const update = (studentId, field, value) => {
    setRecords((items) => items.map((item) => item.student_id === studentId ? { ...item, [field]: value } : item))
    setMessage(''); setError('')
  }
  const fillAllPresent = () => {
    setRecords((items) => items.map((item) => ({ ...item, present_days: String(summary.total_school_days) })))
    setMessage(''); setError('')
  }
  const updateSchoolDays = async () => {
    const value = Number(schoolDays)
    if (!Number.isInteger(value) || value < 1 || value > 31) {
      return setError('Total school days must be a whole number from 1 to 31.')
    }
    try {
      setSaving(true); setError(''); setMessage('')
      await api.put(`/teacher/monthly-attendance/${attendanceId}`, {
        total_school_days: value,
      })
      setSummary((item) => ({ ...item, total_school_days: value }))
      setMessage('Total school days updated.')
    } catch (err) {
      setError(err.response?.data?.error || 'Unable to update total school days.')
    } finally { setSaving(false) }
  }
  const save = async () => {
    const missing = records.find((item) => item.present_days === '')
    if (missing) return setError(`Enter present days for ${missing.full_name}.`)
    const invalid = records.find((item) => !Number.isInteger(Number(item.present_days)) || Number(item.present_days) < 0 || Number(item.present_days) > summary.total_school_days)
    if (invalid) return setError(`${invalid.full_name}'s present days must be a whole number from 0 to ${summary.total_school_days}.`)
    try {
      setSaving(true); setError('')
      await api.put(`/teacher/monthly-attendance/${attendanceId}/records`, {
        records: records.map(({ student_id, present_days, note }) => ({ student_id, present_days: Number(present_days), note })),
      })
      setMessage('Monthly attendance saved successfully.')
    } catch (err) {
      setError(err.response?.data?.error || 'Unable to save monthly attendance.')
    } finally { setSaving(false) }
  }

  if (loading) return <div className="attendance-page-state">Loading monthly register...</div>
  if (!summary) return <div className="attendance-page-state error">{error || 'Monthly register not found.'}</div>
  return <div className="attendance-page attendance-register-page">
    <button className="attendance-back" onClick={() => navigate('/teacher/attendance')}>← Back to Attendance</button>
    <section className="attendance-register-hero"><div><p>MONTHLY CLASS REGISTER</p><h1>{summary.class_name}</h1><span>{monthLabel(summary.attendance_month)} · {summary.total_school_days} school days</span></div><div className="attendance-register-actions"><label>School days<input type="number" min="1" max="31" step="1" value={schoolDays} onChange={(event) => setSchoolDays(event.target.value)} /></label><button onClick={updateSchoolDays} disabled={saving}>Update Days</button><button onClick={fillAllPresent}>Set All Fully Present</button></div></section>
    {error && <div className="attendance-message error">{error}</div>}{message && <div className="attendance-message success">{message}</div>}
    <section className="attendance-summary"><article className="status-present"><span>Students entered</span><strong>{totals.entered}/{records.length}</strong></article><article className="status-present"><span>Present days</span><strong>{totals.present}</strong></article><article className="status-absent"><span>Absent days</span><strong>{totals.absent}</strong></article><article className="status-excused"><span>Attendance</span><strong>{totals.rate}%</strong></article></section>
    <section className="attendance-roster-card"><div className="attendance-section-heading"><div><h2>Monthly totals from paper register</h2><p>Enter present days; absence and percentage are calculated automatically.</p></div><span>{records.length} students</span></div>
      <div className="attendance-table-wrap"><table className="attendance-table"><thead><tr><th>#</th><th>Student</th><th>Present / {summary.total_school_days}</th><th>Absent</th><th>Percentage</th><th>Optional note</th></tr></thead><tbody>{records.map((record, index) => {
        const valid = record.present_days !== '' && Number.isInteger(Number(record.present_days)) && Number(record.present_days) >= 0 && Number(record.present_days) <= summary.total_school_days
        const absent = valid ? summary.total_school_days - Number(record.present_days) : null
        const rate = valid ? Math.round(1000 * Number(record.present_days) / summary.total_school_days) / 10 : null
        return <tr key={record.student_id}><td>{index + 1}</td><td><strong>{record.full_name}</strong><small>Grade {record.grade}</small></td><td><input type="number" min="0" max={summary.total_school_days} step="1" value={record.present_days} onChange={(event) => update(record.student_id, 'present_days', event.target.value)} placeholder="Days" /></td><td>{absent ?? '—'}</td><td>{rate === null ? '—' : `${rate}%`}</td><td><input value={record.note} onChange={(event) => update(record.student_id, 'note', event.target.value)} maxLength="255" placeholder="Optional follow-up note" /></td></tr>
      })}</tbody></table></div><div className="attendance-save-bar"><p>Check the totals against the paper attendance register.</p><button className="attendance-primary" onClick={save} disabled={saving || !records.length}>{saving ? 'Saving...' : 'Save Monthly Attendance'}</button></div>
    </section>
  </div>
}

export default TeacherAttendanceRegister
