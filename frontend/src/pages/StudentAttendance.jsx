import { useEffect, useState } from 'react'
import api from '../api'
import './StudentAttendance.css'

const formatMonth = (value) => new Intl.DateTimeFormat(undefined, {
  month: 'long', year: 'numeric',
}).format(new Date(`${String(value).slice(0, 7)}-01T00:00:00`))

function StudentAttendance() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    api.get('/student/attendance')
      .then((response) => setData(response.data))
      .catch((err) => setError(
        err.response?.data?.error || 'Unable to load attendance history.'
      ))
      .finally(() => setLoading(false))
  }, [])

  const summary = data?.summary
  const records = data?.records || []

  return <div className="student-attendance-page">
    <header className="student-attendance-heading">
      <div><p>PERSONAL SCHOOL RECORD</p><h1>My Attendance</h1><span>Monthly attendance recorded for your classes.</span></div>
    </header>
    {error && <div className="student-attendance-error">{error}</div>}
    {loading ? <div className="student-attendance-empty">Loading attendance history...</div> : !records.length ? <div className="student-attendance-empty"><strong>No attendance recorded</strong><span>Your monthly records will appear here when they are available.</span></div> : <>
      <section className="student-attendance-summary" aria-label="Attendance summary">
        <article><span>Attendance</span><strong>{summary.attendance_percent === null ? '—' : `${summary.attendance_percent}%`}</strong></article>
        <article><span>Present days</span><strong>{summary.present_days}</strong></article>
        <article><span>Absent days</span><strong>{summary.absent_days}</strong></article>
        <article><span>Recorded months</span><strong>{summary.recorded_months}</strong></article>
      </section>
      <section className="student-attendance-history">
        <div className="student-attendance-section-heading"><h2>Monthly history</h2><span>{records.length} register{records.length === 1 ? '' : 's'}</span></div>
        <div className="student-attendance-table-wrap"><table>
          <thead><tr><th>Month</th><th>Class</th><th>Present</th><th>Absent</th><th>School days</th><th>Percentage</th><th>Note</th></tr></thead>
          <tbody>{records.map((record, index) => <tr key={`${record.class_id}-${record.attendance_month}-${index}`}>
            <td>{formatMonth(record.attendance_month)}</td>
            <td><strong>{record.class_name}</strong><small>Grade {record.grade}{record.section ? ` · Section ${record.section}` : ''}</small></td>
            <td>{record.present_days}</td><td>{record.absent_days}</td><td>{record.total_school_days}</td>
            <td>{record.attendance_percent === null ? '—' : `${record.attendance_percent}%`}</td>
            <td>{record.note || '—'}</td>
          </tr>)}</tbody>
        </table></div>
      </section>
    </>}
  </div>
}

export default StudentAttendance