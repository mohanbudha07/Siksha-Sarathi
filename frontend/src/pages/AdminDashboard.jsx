import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
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
  const recentAccounts = (data?.recent_accounts || []).slice(0, 10)
  const schoolSnapshot = (data?.school_snapshot || []).slice(0, 6)
  const attentionItems = [
    ['students_without_class', 'Students without class', '/admin/users'],
    ['teachers_without_assignments', 'Teachers without assignments', '/admin/school-setup'],
    ['classes_without_class_teacher', 'Classes without class teacher', '/admin/school-setup'],
    ['classes_without_subject_assignments', 'Classes without Subject assignments', '/admin/school-setup'],
  ].filter(([key]) => Number(setupHealth[key] || 0) > 0)

  return (
    <div className="admin-dashboard">
      <div className="admin-header">
        <div>
          <h1>Admin Dashboard</h1>
          <p>School operations overview</p>
        </div>
      </div>

      <div className="admin-stats">
        {[
          ['Students', stats.total_students], ['Teachers', stats.total_teachers],
          ['Classes', stats.total_classes], ['Subjects', stats.total_subjects],
        ].map(([label, value]) => <div className="admin-card" key={label}>
          <span>{label}</span><strong>{value ?? 0}</strong>
        </div>)}
      </div>

      <section className="admin-section">
        <div className="section-header">
          <h2>Setup Attention</h2>
        </div>
        {attentionItems.length === 0 ? <p className="admin-setup-good">School setup looks complete.</p> : <div className="admin-attention-list">
          {attentionItems.map(([key, label, href]) => <Link to={href} className="admin-attention-item" key={key}>
            <span>{label}</span><strong>{setupHealth[key]}</strong>
          </Link>)}
        </div>}
      </section>

      <div className="admin-dashboard-panels">
        <section className="admin-section admin-dashboard-panel">
          <div className="section-header"><h2>Recent Accounts</h2></div>
          {recentAccounts.length === 0 ? <p className="empty-state">No accounts found.</p> : <div className="admin-recent-list">
            {recentAccounts.map((account) => <article key={account.user_id}>
              <div className="admin-recent-person"><strong>{account.name}</strong><span>{account.email}</span></div>
              <span className={`role-badge ${account.role}`}>{account.role}</span>
              <div className="admin-recent-context">
                {account.role === 'student' && account.class_name
                  ? `Grade ${account.grade} · Section ${account.section}`
                  : account.role === 'teacher'
                    ? `${account.assignment_count || 0} assignment${account.assignment_count === 1 ? '' : 's'}`
                    : '—'}
              </div>
              <span className={`account-status ${account.is_active ? 'active' : 'inactive'}`}>{account.is_active ? 'Active' : 'Inactive'}</span>
              <time>{account.created_at || '—'}</time>
            </article>)}
          </div>}
          <Link className="admin-dashboard-panel-link" to="/admin/users">View All Users →</Link>
        </section>

        <section className="admin-section admin-dashboard-panel">
          <div className="section-header"><h2>School Snapshot</h2></div>
          {schoolSnapshot.length === 0 ? <p className="empty-state">No classes registered yet.</p> : <div className="admin-snapshot-list">
            {schoolSnapshot.map((schoolClass) => <article key={schoolClass.id}>
              <div className="snapshot-class-heading"><strong>{schoolClass.class_name}</strong><span>Grade {schoolClass.grade} · Section {schoolClass.section}</span></div>
              <p>{schoolClass.student_count} Students · {schoolClass.subject_count} Subjects</p>
              <small>Class Teacher: {schoolClass.class_teacher_name || 'Unassigned'}</small>
            </article>)}
          </div>}
          <Link className="admin-dashboard-panel-link" to="/admin/school-setup">View School Setup →</Link>
        </section>
      </div>
    </div>
  )
}

export default AdminDashboard
