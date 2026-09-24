import React, { useEffect, useState } from 'react'
import api from '../api'
import './AdminDashboard.css'

function AdminDashboard() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const loadDashboard = async () => {
      try {
        const response = await api.get('/admin/dashboard')
        setData(response.data)
      } catch (err) {
        console.error('Admin dashboard error:', err)

        if (err.response?.status === 401) {
          setError('Authentication required.')
        } else if (err.response?.status === 403) {
          setError('Access denied. Admin access required.')
        } else {
          setError('Unable to load admin dashboard.')
        }
      } finally {
        setLoading(false)
      }
    }

    loadDashboard()
  }, [])

  if (loading) {
    return (
      <div className="admin-dashboard">
        <div className="admin-loading">
          Loading admin dashboard...
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="admin-dashboard">
        <div className="admin-error">
          {error}
        </div>
      </div>
    )
  }

  const stats = data?.statistics || {}
  const setupHealth = data?.setup_health || {}
  const classOverview = data?.class_overview || []

  return (
    <div className="admin-dashboard">
      <div className="admin-header">
        <div>
          <h1>Admin Dashboard</h1>
          <p>School operations overview</p>
        </div>
      </div>

      <div className="admin-stats">
        <div className="admin-card">
          <span>Total Students</span>
          <strong>{stats.total_students ?? 0}</strong>
        </div>

        <div className="admin-card">
          <span>Total Teachers</span>
          <strong>{stats.total_teachers ?? 0}</strong>
        </div>

        <div className="admin-card">
          <span>Total Classes</span>
          <strong>{stats.total_classes ?? 0}</strong>
        </div>

        <div className="admin-card">
          <span>Total Subjects</span>
          <strong>{stats.total_subjects ?? 0}</strong>
        </div>

        <div className="admin-card">
          <span>Teacher Assignments</span>
          <strong>{stats.total_teacher_assignments ?? 0}</strong>
        </div>

        <div className="admin-card">
          <span>Total Users</span>
          <strong>{stats.total_users ?? 0}</strong>
        </div>

        <div className="admin-card">
          <span>Notes</span>
          <strong>{stats.total_notes ?? 0}</strong>
        </div>

        <div className="admin-card">
          <span>Quizzes</span>
          <strong>{stats.total_quizzes ?? 0}</strong>
        </div>
      </div>

      <section className="admin-section">
        <div className="section-header">
          <h2>Setup health</h2>
        </div>

        <div className="admin-mini-grid">
          <div className={`admin-health-card ${setupHealth.students_without_class ? 'warning' : ''}`}>
            <span>Students without class</span>
            <strong>{setupHealth.students_without_class ?? 0}</strong>
          </div>

          <div className={`admin-health-card ${setupHealth.teachers_without_assignments ? 'warning' : ''}`}>
            <span>Teachers without assignments</span>
            <strong>{setupHealth.teachers_without_assignments ?? 0}</strong>
          </div>

          <div className={`admin-health-card ${setupHealth.classes_without_class_teacher ? 'warning' : ''}`}>
            <span>Classes without class teacher</span>
            <strong>{setupHealth.classes_without_class_teacher ?? 0}</strong>
          </div>

          <div className={`admin-health-card ${setupHealth.classes_without_subject_assignments ? 'warning' : ''}`}>
            <span>Classes without subject assignments</span>
            <strong>{setupHealth.classes_without_subject_assignments ?? 0}</strong>
          </div>
        </div>
      </section>

      <section className="admin-section">
        <div className="section-header">
          <h2>Class overview</h2>
        </div>

        {classOverview.length ? (
          <div className="admin-table-wrapper">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Class</th>
                  <th>Grade</th>
                  <th>Students</th>
                  <th>Teachers</th>
                  <th>Subjects</th>
                  <th>Class Teacher</th>
                </tr>
              </thead>

              <tbody>
                {classOverview.map((classItem) => (
                  <tr key={classItem.id}>
                    <td>{classItem.name}</td>
                    <td>{classItem.grade}</td>
                    <td>{classItem.student_count ?? 0}</td>
                    <td>{classItem.assigned_teacher_count ?? 0}</td>
                    <td>{classItem.subject_count ?? 0}</td>
                    <td>{classItem.class_teacher_name || 'Unassigned'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty-state">No classes registered yet.</p>
        )}
      </section>

      <section className="admin-section">
        <div className="section-header">
          <h2>Recent Users</h2>
        </div>

        {data?.recent_users?.length ? (
          <div className="admin-table-wrapper">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Username</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Created</th>
                </tr>
              </thead>

              <tbody>
                {data.recent_users.map((user) => (
                  <tr key={user.id}>
                    <td>{user.username}</td>
                    <td>{user.email}</td>
                    <td>
                      <span className={`role-badge ${user.role}`}>
                        {user.role}
                      </span>
                    </td>
                    <td>
                      {user.created_at
                        ? new Date(user.created_at).toLocaleDateString()
                        : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty-state">No users found.</p>
        )}
      </section>
    </div>
  )
}

export default AdminDashboard
