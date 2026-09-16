import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import api from '../api'
import './TeacherAssessments.css'

const normalizeDate = (value) => {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 10)
  return date.toISOString().slice(0, 10)
}

function TeacherAssessmentScores() {
  const { assessmentId } = useParams()
  const navigate = useNavigate()
  const [assessment, setAssessment] = useState(null)
  const [rows, setRows] = useState([])
  const [published, setPublished] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  useEffect(() => {
    const loadAssessment = async () => {
      try {
        setLoading(true)
        const response = await api.get(`/teacher/paper-assessments/${assessmentId}`)
        setAssessment(response.data.assessment)
        setPublished(response.data.assessment.is_published)
        setRows((response.data.students || []).map((student) => ({
          ...student,
          marks_obtained: student.marks_obtained ?? '',
          remarks: student.remarks || '',
        })))
      } catch (err) {
        setError(err.response?.data?.error || 'Unable to load this assessment.')
      } finally {
        setLoading(false)
      }
    }
    loadAssessment()
  }, [assessmentId])

  const statistics = useMemo(() => {
    const presentRows = rows.filter((row) => !row.is_absent && row.marks_obtained !== '')
    const average = presentRows.length && assessment
      ? presentRows.reduce((sum, row) => sum + Number(row.marks_obtained), 0) / presentRows.length
      : 0
    return {
      recorded: rows.filter((row) => row.is_absent || row.marks_obtained !== '').length,
      absent: rows.filter((row) => row.is_absent).length,
      averagePercent: assessment ? Math.round(1000 * average / assessment.max_marks) / 10 : 0,
    }
  }, [assessment, rows])

  const updateRow = (studentId, field, value) => {
    setRows((current) => current.map((row) => row.student_id === studentId
      ? { ...row, [field]: value }
      : row))
    setError('')
    setSuccess('')
  }

  const toggleAbsent = (studentId, checked) => {
    setRows((current) => current.map((row) => row.student_id === studentId
      ? { ...row, is_absent: checked, marks_obtained: checked ? '' : row.marks_obtained }
      : row))
  }

  const saveScores = async () => {
    const incomplete = rows.find((row) => !row.is_absent && row.marks_obtained === '')
    if (incomplete) {
      setError(`Enter marks or mark ${incomplete.full_name} absent.`)
      return
    }
    const invalid = rows.find((row) => !row.is_absent && (
      Number(row.marks_obtained) < 0 || Number(row.marks_obtained) > assessment.max_marks
    ))
    if (invalid) {
      setError(`${invalid.full_name}'s marks must be between 0 and ${assessment.max_marks}.`)
      return
    }

    try {
      setSaving(true)
      setError('')
      setSuccess('')
      await api.put(`/teacher/paper-assessments/${assessmentId}/scores`, {
        scores: rows.map((row) => ({
          student_id: row.student_id,
          marks_obtained: row.is_absent ? null : Number(row.marks_obtained),
          is_absent: row.is_absent,
          remarks: row.remarks,
        })),
      })
      await api.put(`/teacher/paper-assessments/${assessmentId}`, {
        class_id: assessment.class_id,
        subject: assessment.subject,
        title: assessment.title,
        assessment_type: assessment.assessment_type,
        assessment_date: normalizeDate(assessment.assessment_date),
        max_marks: assessment.max_marks,
        academic_year: assessment.academic_year,
        term: assessment.term,
        is_published: published,
      })
      setAssessment((current) => ({ ...current, is_published: published }))
      setSuccess(published ? 'Marks saved and published successfully.' : 'Draft marks saved successfully.')
    } catch (err) {
      setError(err.response?.data?.error || 'Unable to save assessment marks.')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="paper-page-state">Loading class roster...</div>
  if (!assessment) return <div className="paper-page-state paper-state-error">{error || 'Assessment not found.'}</div>

  return (
    <div className="paper-scores-page">
      <button className="paper-back-button" onClick={() => navigate('/teacher/assessments')}>← Back to Assessments</button>
      <section className="paper-score-hero">
        <div><p>{assessment.assessment_type.replaceAll('_', ' ').toUpperCase()}</p><h1>{assessment.title}</h1><span>{assessment.class_name} · {assessment.subject} · Maximum {assessment.max_marks} marks</span></div>
        <label className="paper-publish-toggle"><input type="checkbox" checked={published} onChange={(event) => setPublished(event.target.checked)} /><span><strong>Publish results</strong><small>Marks are ready for analytics</small></span></label>
      </section>

      <section className="paper-score-summary">
        <article><span>Students</span><strong>{rows.length}</strong></article>
        <article><span>Recorded</span><strong>{statistics.recorded}</strong></article>
        <article><span>Absent</span><strong>{statistics.absent}</strong></article>
        <article><span>Class average</span><strong>{statistics.averagePercent}%</strong></article>
      </section>

      {error && <div className="paper-assessment-error">⚠️ {error}</div>}
      {success && <div className="paper-assessment-success">✓ {success}</div>}

      <section className="paper-marks-section">
        <div className="paper-marks-heading"><div><h2>Class marks sheet</h2><p>Enter every present student’s marks or mark the student absent.</p></div><span>{assessment.academic_year} {assessment.term}</span></div>
        {rows.length === 0 ? <div className="paper-empty-state">No students are enrolled in this class.</div> : (
          <div className="paper-table-wrap">
            <table className="paper-marks-table">
              <thead><tr><th>#</th><th>Student</th><th>Marks / {assessment.max_marks}</th><th>Absent</th><th>Percentage</th><th>Teacher remarks</th></tr></thead>
              <tbody>{rows.map((row, index) => {
                const percentage = !row.is_absent && row.marks_obtained !== ''
                  ? Math.round(1000 * Number(row.marks_obtained) / assessment.max_marks) / 10
                  : null
                return <tr key={row.student_id} className={row.is_absent ? 'paper-absent-row' : ''}>
                  <td>{index + 1}</td><td><strong>{row.full_name}</strong><small>Grade {row.grade}</small></td>
                  <td><input className="paper-mark-input" type="number" min="0" max={assessment.max_marks} step="0.01" disabled={row.is_absent} value={row.marks_obtained} onChange={(event) => updateRow(row.student_id, 'marks_obtained', event.target.value)} placeholder={row.is_absent ? 'Absent' : 'Marks'} /></td>
                  <td><label className="paper-absent-check"><input type="checkbox" checked={row.is_absent} onChange={(event) => toggleAbsent(row.student_id, event.target.checked)} /><span>{row.is_absent ? 'Absent' : 'Present'}</span></label></td>
                  <td><span className={percentage === null ? 'paper-percent empty' : percentage < 40 ? 'paper-percent low' : percentage < 60 ? 'paper-percent developing' : 'paper-percent good'}>{percentage === null ? '—' : `${percentage}%`}</span></td>
                  <td><input className="paper-remark-input" maxLength="500" value={row.remarks} onChange={(event) => updateRow(row.student_id, 'remarks', event.target.value)} placeholder="Optional observation" /></td>
                </tr>
              })}</tbody>
            </table>
          </div>
        )}
        <div className="paper-save-bar"><p>Review the marks before publishing. Draft records remain visible only to the teacher.</p><button className="paper-primary-button" onClick={saveScores} disabled={saving || !rows.length}>{saving ? 'Saving...' : published ? 'Save & Publish Marks' : 'Save Draft Marks'}</button></div>
      </section>
    </div>
  )
}

export default TeacherAssessmentScores
