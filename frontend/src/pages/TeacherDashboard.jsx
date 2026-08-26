import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'
import './TeacherDashboard.css'

function TeacherDashboard() {
  const navigate = useNavigate()

  const [teacher, setTeacher] = useState(null)
  const [statistics, setStatistics] = useState({
  total_notes: 0,
  total_students: 0,
  total_quiz_attempts: 0,
  average_quiz_score: 0,
  students_needing_improvement: 0,
  total_predictions: 0,
})
  const [recentNotes, setRecentNotes] = useState([])
  const [studentPerformance, setStudentPerformance] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const loadDashboard = async () => {
      try {
        const response = await api.get('/teacher/dashboard')

        setTeacher(response.data.teacher)
        setStatistics(response.data.statistics)
        setRecentNotes(response.data.recent_notes || [])
        setStudentPerformance(response.data.student_performance || [])
        console.log(
          'Student Performance:',
          response.data.student_performance
       )
      } catch (err) {
        console.error('Teacher dashboard error:', err)

        setError(
          err.response?.data?.error ||
            'Unable to load teacher dashboard.'
        )
      } finally {
        setLoading(false)
      }
    }

    loadDashboard()
  }, [])

  if (loading) {
    return (
      <div className="teacher-loading">
        <div className="teacher-spinner"></div>
        <p>Loading your dashboard...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="teacher-error">
        <div>⚠️</div>
        <h2>Something went wrong</h2>
        <p>{error}</p>
        <button onClick={() => window.location.reload()}>
          Try Again
        </button>
      </div>
    )
  }

  return (
    <div className="teacher-dashboard">

      <section className="teacher-hero">

        <div>
          <p className="teacher-label">
            TEACHER PANEL
          </p>

          <h1>
            Welcome, {teacher?.name || 'Teacher'} 👋
          </h1>

          <p>
            Manage your learning resources and support your
            students from one place.
          </p>
        </div>

        <div className="teacher-hero-icon">
          👨‍🏫
        </div>

      </section>

      <main className="teacher-content">

        {/* STATISTICS */}

      
<section className="teacher-stats">

  <div className="teacher-stat-card">

    <div className="stat-icon">
      👨‍🎓
    </div>

    <div>
      <p>Total Students</p>

      <h2>
        {statistics.total_students}
      </h2>
    </div>

  </div>

  <div className="teacher-stat-card">

    <div className="stat-icon">
      📝
    </div>

    <div>
      <p>Quiz Attempts</p>

      <h2>
        {statistics.total_quiz_attempts}
      </h2>
    </div>

  </div>

  <div className="teacher-stat-card">

    <div className="stat-icon">
      📊
    </div>

    <div>
      <p>Average Quiz Score</p>

      <h2>
        {statistics.average_quiz_score}
      </h2>
    </div>

  </div>
  <div className="teacher-stat-card">

  <div className="stat-icon">
    ⚠️
  </div>

  <div>
    <p>Needs Improvement</p>

    <h2>
      {statistics.students_needing_improvement}
    </h2>
  </div>

</div>

</section>
       {/* QUICK ACTIONS */}

        <section className="teacher-section">

          <div className="teacher-section-heading">
            <div>
              <h2>Quick Actions</h2>
              <p>
                Manage your teaching resources.
              </p>
            </div>
          </div>

          <section className="teacher-cards">

            <div
              className="teacher-card"
              onClick={() => navigate('/teacher/upload')}
            >
              <div className="teacher-card-icon">
                📤
              </div>

              <h3>Upload Notes</h3>

              <p>
                Upload new study materials, chapters and
                subject notes for your students.
              </p>

              <button>
                Upload Notes →
              </button>
            </div>

            <div
              className="teacher-card"
              onClick={() => navigate('/teacher/notes')}
            >
              <div className="teacher-card-icon">
                📚
              </div>

              <h3>My Notes</h3>

              <p>
                View and manage the learning resources you
                have uploaded for students.
              </p>

              <button>
                View Notes →
              </button>
            </div>

          </section>

        </section>
                {/* STUDENT PERFORMANCE */}

        <section className="student-performance-section">

          <div className="student-performance-heading">
            <div>
              <h2>Student Performance</h2>
              <p>
                Monitor your students' learning progress and performance.
              </p>
            </div>
          </div>

          {studentPerformance.length === 0 ? (

            <div className="empty-performance">

              <div>📊</div>

              <h3>No student performance data yet</h3>

              <p>
                Student performance will appear here after students
                complete quizzes and receive predictions.
              </p>

            </div>

          ) : (

            <div className="student-performance-table">

              <table>

                <thead>

                  <tr>
                    <th>Student</th>
                    <th>Grade</th>
                    <th>Quiz Attempts</th>
                    <th>Average Score</th>
                    <th>Attendance</th>
                    <th>Assignment</th>
                    <th>Prediction</th>
                    <th>Action</th>
                  </tr>

                </thead>

                <tbody>

                  {studentPerformance.map((student) => (

                    <tr key={student.student_id}>

                      <td>
                        <strong>
                          {student.full_name}
                        </strong>
                      </td>

                      <td>
                        {student.grade}
                      </td>

                      <td>
                        {student.quiz_attempts}
                      </td>

                      <td>
                        {(
                          Number(student.average_quiz_score) * 100
                        ).toFixed(1)}%
                      </td>

                      <td>
                        {student.attendance ?? '—'}%
                      </td>

                      <td>
                        {student.assignment_score ?? '—'}%
                      </td>

                      <td>
  <span
    className={
      student.prediction === 'Needs Improvement'
        ? 'prediction-warning'
        : 'prediction-good'
    }
  >
    {student.prediction || 'Not Predicted'}
  </span>
</td>

<td>
  <button
    className="view-student-btn"
    onClick={() => setSelectedStudent(student)}
  >
    View Details
  </button>
</td>

                    </tr>

                  ))}

                </tbody>

              </table>

            </div>

          )}

        </section>

        

        {/* RECENT NOTES */}

        <section className="recent-notes-section">

          <div className="recent-heading">

            <div>
              <h2>Recent Notes</h2>

              <p>
                Your latest uploaded learning materials.
              </p>
            </div>

            <button
              onClick={() => navigate('/teacher/notes')}
            >
              View All
            </button>

          </div>

          {recentNotes.length === 0 ? (

            <div className="empty-notes">

              <div>📚</div>

              <h3>No notes uploaded yet</h3>

              <p>
                Start by uploading your first learning resource.
              </p>

              <button
                onClick={() => navigate('/teacher/upload')}
              >
                Upload Your First Note
              </button>

            </div>

          ) : (

            <div className="recent-notes-list">

              {recentNotes.map((note) => (

                <div
                  className="recent-note"
                  key={note.id}
                >

                  <div className="recent-note-icon">
                    📖
                  </div>

                  <div className="recent-note-info">

                    <h3>
                      {note.title}
                    </h3>

                    <p>
                      {note.subject} • {note.chapter}
                    </p>

                  </div>

                  <div className="recent-note-date">
                    {note.created_at
                      ? new Date(
                          note.created_at
                        ).toLocaleDateString()
                      : ''}
                  </div>

                </div>

              ))}

            </div>

          )}

        </section>

        {/* TEACHER TIP */}

        <section className="teacher-info-panel">

          <div className="info-icon">
            💡
          </div>

          <div>
            <h3>Teacher Tip</h3>

            <p>
              Keep your learning materials organized by
              subject and chapter so students can find them
              easily.
            </p>
          </div>

        </section>

        {selectedStudent && (
  <div
    className="student-modal-overlay"
    onClick={() => setSelectedStudent(null)}
  >
    <div
      className="student-modal"
      onClick={(e) => e.stopPropagation()}
    >

      <div className="student-modal-header">
        <div>
          <h2>{selectedStudent.full_name}</h2>
          <p>Grade {selectedStudent.grade}</p>
        </div>

        <button
          className="student-modal-close"
          onClick={() => setSelectedStudent(null)}
        >
          ×
        </button>
      </div>

      <div className="student-modal-grid">

        <div className="student-detail-card">
          <span>📝</span>
          <p>Quiz Attempts</p>
          <strong>{selectedStudent.quiz_attempts}</strong>
        </div>

        <div className="student-detail-card">
          <span>📊</span>
          <p>Average Quiz Score</p>
          <strong>
            {selectedStudent.average_quiz_score}
          </strong>
        </div>

        <div className="student-detail-card">
          <span>📅</span>
          <p>Attendance</p>
          <strong>
            {selectedStudent.attendance ?? '—'}%
          </strong>
        </div>

        <div className="student-detail-card">
          <span>📚</span>
          <p>Assignment Score</p>
          <strong>
            {selectedStudent.assignment_score ?? '—'}%
          </strong>
        </div>

        <div className="student-detail-card">
          <span>⏱️</span>
          <p>Study Hours</p>
          <strong>
            {selectedStudent.study_hours ?? '—'}
          </strong>
        </div>

        <div className="student-detail-card">
          <span>🤖</span>
          <p>ML Prediction</p>

          <strong
            className={
              selectedStudent.prediction === 'Needs Improvement'
                ? 'prediction-warning'
                : 'prediction-good'
            }
          >
            {selectedStudent.prediction || 'Not Predicted'}
          </strong>
        </div>

      </div>

    </div>
  </div>
)}

      </main>

    </div>
  )
}

export default TeacherDashboard
