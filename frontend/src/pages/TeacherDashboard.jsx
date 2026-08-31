import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api";
import "./TeacherDashboard.css";

function TeacherDashboard() {
  const navigate = useNavigate();

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchDashboard();
  }, []);

  const fetchDashboard = async () => {
    try {
      setLoading(true);
      setError("");

      const response = await api.get("/teacher/dashboard");
      setData(response.data);
    } catch (err) {
      console.error("Teacher dashboard error:", err);

      if (err.response) {
        setError(
          err.response.data?.error ||
            `Server error: ${err.response.status}`
        );
      } else {
        setError(
          "Unable to connect to the server. Make sure Flask is running."
        );
      }
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = async () => {
    try {
      await api.post("/logout");
    } catch (err) {
      console.error("Logout error:", err);
    } finally {
      navigate("/login");
    }
  };

  if (loading) {
    return (
      <div className="teacher-dashboard-page">
        <div className="teacher-loading">
          <div className="loading-spinner"></div>
          <p>Loading teacher dashboard...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="teacher-dashboard-page">
        <div className="teacher-error">
          <h2>Unable to load dashboard</h2>
          <p>{error}</p>
          <button onClick={fetchDashboard}>Try Again</button>
        </div>
      </div>
    );
  }

  const teacher = data?.teacher || {};
  const statistics = data?.statistics || {};
  const recentNotes = data?.recent_notes || [];
  const studentPerformance = data?.student_performance || [];

  return (
    <div className="teacher-dashboard-page">
      {/* HEADER */}
      <header className="teacher-header">
        <div>
          <h1>Siksha Sarathi</h1>
          <p>Teacher Dashboard</p>
        </div>

        <div className="teacher-header-right">
          <div className="teacher-profile">
            <div className="teacher-avatar">
              {(teacher.name || "T").charAt(0).toUpperCase()}
            </div>

            <div>
              <strong>{teacher.name || "Teacher"}</strong>
              <span>Teacher</span>
            </div>
          </div>

          <button className="logout-button" onClick={handleLogout}>
            Logout
          </button>
        </div>
      </header>

      {/* MAIN CONTENT */}
      <main className="teacher-main">
        {/* WELCOME */}
        <section className="teacher-welcome">
          <div>
            <h2>Welcome, {teacher.name || "Teacher"} 👋</h2>
            <p>Monitor student learning progress and performance.</p>
          </div>

          <button
            className="notes-button"
            onClick={() => navigate("/teacher/notes")}
          >
            Manage Notes
          </button>
        </section>

        {/* STATISTICS */}
        <section className="statistics-grid">
          <div className="stat-card">
            <div className="stat-icon">👨‍🎓</div>
            <div>
              <span>Total Students</span>
              <h3>{statistics.total_students ?? 0}</h3>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-icon">📝</div>
            <div>
              <span>Quiz Attempts</span>
              <h3>{statistics.total_quiz_attempts ?? 0}</h3>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-icon">📊</div>
            <div>
              <span>Average Quiz Score</span>
              <h3>{statistics.average_quiz_score ?? 0}</h3>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-icon">📚</div>
            <div>
              <span>My Notes</span>
              <h3>{statistics.total_notes ?? 0}</h3>
            </div>
          </div>

          <div className="stat-card warning-card">
            <div className="stat-icon">⚠️</div>
            <div>
              <span>Needs Improvement</span>
              <h3>{statistics.students_needing_improvement ?? 0}</h3>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-icon">🤖</div>
            <div>
              <span>ML Predictions</span>
              <h3>{statistics.total_predictions ?? 0}</h3>
            </div>
          </div>
        </section>

        {/* STUDENT PERFORMANCE */}
        <section className="dashboard-section">
          <div className="section-header">
            <div>
              <h2>Student Performance</h2>
              <p>Overview of individual student learning performance</p>
            </div>
          </div>

          {studentPerformance.length === 0 ? (
            <div className="empty-state">
              <div>👨‍🎓</div>
              <h3>No student performance data</h3>
              <p>
                Student performance data will appear here once students
                complete learning activities.
              </p>
            </div>
          ) : (
            <div className="performance-table-wrapper">
              <table className="performance-table">
                <thead>
                  <tr>
                    <th>Student</th>
                    <th>Grade</th>
                    <th>Quiz Attempts</th>
                    <th>Avg. Quiz Score</th>
                    <th>Attendance</th>
                    <th>Assignment</th>
                    <th>Study Hours</th>
                    <th>ML Prediction</th>
                  </tr>
                </thead>

                <tbody>
                  {studentPerformance.map((student) => (
                    <tr key={student.student_id}>
                      <td>
                        <div className="student-name">
                          <div className="student-avatar">
                            {student.full_name?.charAt(0).toUpperCase()}
                          </div>
                          <strong>{student.full_name}</strong>
                        </div>
                      </td>

                      <td>
                        <span className="grade-badge">
                          Grade {student.grade}
                        </span>
                      </td>

                      <td>{student.quiz_attempts ?? 0}</td>
                      <td>{student.average_quiz_score ?? 0}</td>
                      <td>{student.attendance ?? 0}%</td>
                      <td>{student.assignment_score ?? 0}%</td>
                      <td>{student.study_hours ?? 0} hrs</td>

                      <td>
                        <span
                          className={`prediction-badge ${
                            student.prediction === "Needs Improvement"
                              ? "prediction-warning"
                              : student.prediction === "Good"
                              ? "prediction-good"
                              : "prediction-normal"
                          }`}
                        >
                          {student.prediction || "Not Available"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* RECENT NOTES */}
        <section className="dashboard-section">
          <div className="section-header">
            <div>
              <h2>Recent Notes</h2>
              <p>Notes uploaded by you</p>
            </div>

            <button
              className="section-button"
              onClick={() => navigate("/teacher/notes")}
            >
              View All Notes
            </button>
          </div>

          {recentNotes.length === 0 ? (
            <div className="empty-state compact">
              <div>📚</div>
              <h3>No notes uploaded yet</h3>
              <p>Upload your first learning note to get started.</p>

              <button onClick={() => navigate("/teacher/notes")}>
                Upload Note
              </button>
            </div>
          ) : (
            <div className="notes-grid">
              {recentNotes.map((note) => (
                <div className="note-card" key={note.id}>
                  <div className="note-card-icon">📖</div>

                  <div>
                    <h3>{note.title}</h3>
                    <p>
                      {note.subject} • Chapter {note.chapter}
                    </p>

                    {note.created_at && (
                      <small>
                        {new Date(note.created_at).toLocaleDateString()}
                      </small>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

export default TeacherDashboard;