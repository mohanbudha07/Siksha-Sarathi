import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'
import './AdminLogin.css'

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
      <div className="admin-login-container">
        <div className="admin-login-brand">
          <div className="admin-brand-icon">🏫</div>
          <h1>Siksha Sarathi</h1>
          <p>Administration Portal</p>
        </div>

        <div className="admin-login-card">
          <div className="admin-login-heading">
            <h2>Principal Sign In</h2>
            <p>Access the school administration dashboard.</p>
          </div>

          <form onSubmit={handleSubmit}>
            <div className="admin-input-group">
              <label htmlFor="admin-email">Email</label>
              <input
                id="admin-email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="Enter your admin email"
                required
              />
            </div>

            <div className="admin-input-group">
              <label htmlFor="admin-password">Password</label>
              <input
                id="admin-password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Enter your password"
                required
              />
            </div>

            {error && <div className="admin-login-error">⚠️ {error}</div>}

            <button type="submit" className="admin-login-button" disabled={loading}>
              {loading ? 'Signing in...' : 'Sign In'}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}

export default AdminLogin
