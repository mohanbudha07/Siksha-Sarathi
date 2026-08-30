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

  return (
    <div className="admin-dashboard">

      <div className="admin-header">
        <div>
          <h1>Admin Dashboard</h1>
          <p>System overview and platform statistics</p>
        </div>
      </div>

      <div className="admin-stats">

        <div className="admin-card">
          <span>Total Users</span>
          <strong>{stats.total_users ?? 0}</strong>
        </div>

        <div className="admin-card">
          <span>Students</span>
          <strong>{stats.total_students ?? 0}</strong>
        </div>

        <div className="admin-card">
          <span>Teachers</span>
          <strong>{stats.total_teachers ?? 0}</strong>
        </div>

        <div className="admin-card">
          <span>Admins</span>
          <strong>{stats.total_admins ?? 0}</strong>
        </div>

        <div className="admin-card">
          <span>Notes</span>
          <strong>{stats.total_notes ?? 0}</strong>
        </div>

        <div className="admin-card">
          <span>Quizzes</span>
          <strong>{stats.total_quizzes ?? 0}</strong>
        </div>

        <div className="admin-card">
          <span>Quiz Attempts</span>
          <strong>{stats.total_quiz_attempts ?? 0}</strong>
        </div>

        <div className="admin-card warning">
          <span>Needs Improvement</span>
          <strong>{stats.students_needing_improvement ?? 0}</strong>
        </div>

      </div>

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
          <p className="empty-state">
            No users found.
          </p>
        )}
      </section>

    </div>
  )
}

export default AdminDashboard
