import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'
import './TeacherLearningAnalytics.css'

const EMPTY_LIST = []

const statusClass = (status) =>
  `tla-status tla-status-${String(status || 'no-activity')
    .toLowerCase()
    .replaceAll(' ', '-')}`

function TeacherLearningAnalytics() {
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [classFilter, setClassFilter] = useState('all')
  const [subjectFilter, setSubjectFilter] = useState('all')
  const [search, setSearch] = useState('')

  const loadAnalytics = async () => {
    try {
      setLoading(true)
      setError('')
      const response = await api.get('/teacher/learning-analytics')
      setData(response.data)
    } catch (err) {
      console.error('Teacher learning analytics error:', err)
      setError(
        err.response?.data?.error ||
          'Unable to load learning analytics. Make sure Flask is running.'
      )
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAnalytics()
  }, [])

  const assignments = data?.assignments || EMPTY_LIST
  const students = data?.students || EMPTY_LIST
  const topicPriorities = data?.topic_priorities || EMPTY_LIST

  const classes = useMemo(() => {
    const unique = new Map()
    assignments.forEach((assignment) => {
      unique.set(String(assignment.class_id), assignment)
    })
    return [...unique.values()]
  }, [assignments])

  const subjects = useMemo(() => {
    const available = assignments
      .filter(
        (assignment) =>
          classFilter === 'all' || String(assignment.class_id) === classFilter
      )
      .map((assignment) => assignment.subject)
    return [...new Set(available)]
  }, [assignments, classFilter])

  useEffect(() => {
    if (subjectFilter !== 'all' && !subjects.includes(subjectFilter)) {
      setSubjectFilter('all')
    }
  }, [subjectFilter, subjects])

  const filteredStudents = useMemo(() => {
    const term = search.trim().toLowerCase()
    return students.filter((student) => {
      const matchesClass =
        classFilter === 'all' || String(student.class_id) === classFilter
      const matchesSubject =
        subjectFilter === 'all' || student.subject === subjectFilter
      const matchesSearch =
        !term || student.full_name?.toLowerCase().includes(term)
      return matchesClass && matchesSubject && matchesSearch
    })
  }, [classFilter, search, students, subjectFilter])

  const filteredStatistics = useMemo(() => {
    const studentIds = new Set(filteredStudents.map((student) => student.student_id))
    return {
      students: studentIds.size,
      active: new Set(
        filteredStudents
          .filter((student) => student.total_questions > 0)
          .map((student) => student.student_id)
      ).size,
      attention: filteredStudents.filter(
        (student) => student.status === 'Needs attention'
      ).length,
      paper: filteredStudents.filter(
        (student) => student.paper_assessments?.recorded_assessments > 0
      ).length,
      attendance: new Set(
        filteredStudents
          .filter((student) => student.attendance?.recorded_days > 0)
          .map((student) => student.student_id)
      ).size,
    }
  }, [filteredStudents])

  const visiblePriorities = useMemo(() => topicPriorities.filter((item) =>
    (classFilter === 'all' || String(item.class_id) === classFilter) &&
    (subjectFilter === 'all' || item.subject === subjectFilter) &&
    (!search.trim() || item.students_to_support.some((student) =>
      student.full_name.toLowerCase().includes(search.trim().toLowerCase())
    ))
  ), [topicPriorities, classFilter, subjectFilter, search])

  const openProfile = (student) => {
    const subject = encodeURIComponent(student.subject)
    navigate(
      `/teacher/analytics/students/${student.student_id}?subject=${subject}`
    )
  }

  if (loading) {
    return (
      <div className="tla-page">
        <div className="tla-state">
          <div className="tla-spinner" />
          <p>Preparing class learning analytics...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="tla-page">
        <div className="tla-state tla-error">
          <h2>Analytics unavailable</h2>
          <p>{error}</p>
          <button onClick={loadAnalytics}>Try Again</button>
        </div>
      </div>
    )
  }

  return (
    <div className="tla-page">
      <section className="tla-hero">
        <div>
          <p className="tla-eyebrow">LEARNING EVIDENCE</p>
          <h1>Learning Insights</h1>
          <p>
            Compare online quiz evidence, paper marks and monthly attendance
            without hiding them inside one unclear score.
          </p>
        </div>
        <div className="tla-hero-scope">
          <span>{assignments.length}</span>
          <small>class-subject assignments</small>
        </div>
      </section>

      {assignments.length === 0 ? (
        <section className="tla-state tla-empty">
          <div className="tla-empty-icon">📊</div>
          <h2>No class-subject assignment</h2>
          <p>
            Ask the administrator to assign you to a class and subject before
            viewing student analytics.
          </p>
        </section>
      ) : (
        <>
          <section className="tla-stat-grid">
            <article>
              <span>Assigned students</span>
              <strong>{filteredStatistics.students}</strong>
              <small>Visible in this selection</small>
            </article>
            <article>
              <span>With activity</span>
              <strong>{filteredStatistics.active}</strong>
              <small>Students who attempted questions</small>
            </article>
            <article className="tla-stat-alert">
              <span>Needs attention</span>
              <strong>{filteredStatistics.attention}</strong>
              <small>Profiles requiring teacher support</small>
            </article>
            <article>
              <span>Paper evidence</span>
              <strong>{filteredStatistics.paper}</strong>
              <small>Profiles with published marks</small>
            </article>
            <article>
              <span>Attendance tracked</span>
              <strong>{filteredStatistics.attendance}</strong>
              <small>Students with monthly records</small>
            </article>
          </section>

          <section className="tla-content">
            <div className="tla-section-heading">
              <div>
                <h2>Explore learning evidence</h2>
                <p>Filter by class, subject or student to focus your review.</p>
              </div>
            </div>

            <div className="tla-filters">
              <label>
                Class
                <select
                  value={classFilter}
                  onChange={(event) => setClassFilter(event.target.value)}
                >
                  <option value="all">All assigned classes</option>
                  {classes.map((item) => (
                    <option key={item.class_id} value={item.class_id}>
                      {item.class_name} · {item.section}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Subject
                <select
                  value={subjectFilter}
                  onChange={(event) => setSubjectFilter(event.target.value)}
                >
                  <option value="all">All assigned subjects</option>
                  {subjects.map((subject) => (
                    <option key={subject} value={subject}>
                      {subject}
                    </option>
                  ))}
                </select>
              </label>

              <label className="tla-search-label">
                Student
                <input
                  type="search"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search by name"
                />
              </label>
            </div>

            <div className="tla-section-heading">
              <div>
                <h2>Topics to review with the class</h2>
                <p>Based on tagged quiz answers. A student needs at least three answers across two different questions, with accuracy below 60%.</p>
              </div>
            </div>
            {visiblePriorities.length ? (
              <div className="tla-priority-grid">
                {visiblePriorities.map((item) => (
                  <article key={`${item.class_id}-${item.subject}-${item.topic}`}>
                    <small>{classes.find((entry) => entry.class_id === item.class_id)?.class_name} · {item.subject}</small>
                    <h3>{item.topic}</h3>
                    <p>{item.correct_answers}/{item.total_questions} correct · {item.skipped_answers} skipped</p>
                    <strong>{item.students_to_support.length} {item.students_to_support.length === 1 ? 'student needs' : 'students need'} practice</strong>
                    <div className="tla-priority-students">
                      {item.students_to_support.map((student) => (
                        <button key={student.student_id} type="button" onClick={() => openProfile({ ...student, subject: item.subject })}>
                          {student.full_name} →
                        </button>
                      ))}
                    </div>
                    <small>Review the concept together, then check a new practice question.</small>
                  </article>
                ))}
              </div>
            ) : (
              <p className="tla-muted tla-priority-empty">No topic meets the review threshold in this selection. Add topic tags to quiz questions to get specific suggestions.</p>
            )}

            <div className="tla-section-heading tla-profiles-heading">
              <div><h2>Student learning profiles</h2><p>Open a profile to see the evidence and suggested next steps.</p></div>
            </div>

            {filteredStudents.length === 0 ? (
              <div className="tla-no-results">
                <h3>No matching learning profiles</h3>
                <p>Change the filters or wait for assigned students to be enrolled.</p>
              </div>
            ) : (
              <div className="tla-table-wrap">
                <table className="tla-table">
                  <thead>
                    <tr>
                      <th>Student</th>
                      <th>Class & subject</th>
                      <th>Online quiz</th>
                      <th>Paper marks</th>
                      <th>Attendance</th>
                      <th>Status</th>
                      <th aria-label="Profile action" />
                    </tr>
                  </thead>
                  <tbody>
                    {filteredStudents.map((student) => (
                      <tr key={`${student.student_id}-${student.class_id}-${student.subject}`}>
                        <td>
                          <div className="tla-student">
                            <span>{student.full_name?.charAt(0).toUpperCase()}</span>
                            <div>
                              <strong>{student.full_name}</strong>
                              <small>Grade {student.grade}</small>
                            </div>
                          </div>
                        </td>
                        <td>
                          <strong>{student.class_name}</strong>
                          <small className="tla-cell-note"><span className="tla-subject">{student.subject}</span></small>
                        </td>
                        <td>
                          <strong>{student.total_questions ? `${student.accuracy_percent}%` : '—'}</strong>
                          <small className="tla-cell-note">
                            {student.attempts} attempts · {student.skip_percent}% skipped
                          </small>
                        </td>
                        <td><strong>{student.paper_assessments?.graded_assessments ? `${student.paper_assessments.average_percent}%` : '—'}</strong><small className="tla-cell-note">{student.paper_assessments?.recorded_assessments || 0} recorded entries</small></td>
                        <td><strong>{student.attendance?.recorded_days ? `${student.attendance.attendance_percent}%` : '—'}</strong><small className="tla-cell-note">{student.attendance?.recorded_days || 0} school days</small></td>
                        <td><span className={statusClass(student.status)}>{student.status}</span></td>
                        <td>
                          <button
                            className="tla-view-button"
                            onClick={() => openProfile(student)}
                          >
                            View profile
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}

export default TeacherLearningAnalytics
