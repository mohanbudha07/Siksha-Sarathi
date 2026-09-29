import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import api from '../api'
import './AdminLogin.css'
import '../styles/AuthExperience.css'

function AdminLogin() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const navigate = useNavigate()

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError('')
    setLoading(true)

    try {
      const response = await api.post('/admin/login', { email, password })
      const user = response.data.user

      if (user.role !== 'admin') {
        setError('Access denied for this portal.')
        return
      }

      if (user.must_change_password) {
        navigate('/change-password', { replace: true })
      } else {
        navigate('/admin/dashboard', { replace: true })
      }
    } catch (requestError) {
      setError(requestError.response?.data?.error || 'Unable to sign in.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="admin-login-page">
      <div className="admin-login-layout">
        <aside className="admin-login-intro">
          <Link className="auth-brand" to="/">
            <span className="auth-brand-mark">SS</span>
            <span><strong>Siksha Sarathi</strong><small>Administration</small></span>
          </Link>
          <div className="admin-login-intro-copy">
            <p className="auth-eyebrow">SCHOOL OPERATIONS</p>
            <h1>Lead with a clear view.</h1>
            <p>Manage the academic structure and school services from one secure administration workspace.</p>
          </div>
          <Link className="auth-home-link" to="/">← Back to the institution site</Link>
        </aside>

        <div className="admin-login-card">
          <div className="admin-login-heading">
            <p className="auth-eyebrow">ADMINISTRATION PORTAL</p>
            <h2>Sign in</h2>
            <p>Use your authorized administrator account.</p>
          </div>

          <form onSubmit={handleSubmit}>
            <div className="admin-input-group">
              <label htmlFor="admin-email">Email</label>
              <input
                id="admin-email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="name@school.edu"
                required
              />
            </div>

            <div className="admin-input-group">
              <label htmlFor="admin-password">Password</label>
              <input
                id="admin-password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Enter your password"
                required
              />
            </div>

            {error && <div className="admin-login-error" role="alert">{error}</div>}

            <button type="submit" className="admin-login-button" disabled={loading}>
              {loading ? 'Signing in...' : 'Sign in'}
            </button>
          </form>
          <p className="admin-login-security-note">Administrator access is checked against your school account.</p>
        </div>
      </div>
    </div>
  )
}

export default AdminLogin
