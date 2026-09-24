import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'
import './ChangePassword.css'

function ChangePassword() {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    current_password: '',
    new_password: '',
    confirm_password: '',
  })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const updateField = (event) => {
    setForm({ ...form, [event.target.name]: event.target.value })
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError('')
    if (form.new_password.length < 8) {
      setError('New password must contain at least 8 characters.')
      return
    }
    if (form.new_password !== form.confirm_password) {
      setError('New passwords do not match.')
      return
    }

    try {
      setLoading(true)
      const response = await api.post('/auth/change-password', form)
      const role = response.data.user.role
      if (role === 'admin') navigate('/admin/dashboard', { replace: true })
      else if (role === 'teacher') navigate('/teacher/dashboard', { replace: true })
      else navigate('/student/dashboard', { replace: true })
    } catch (requestError) {
      setError(requestError.response?.data?.error || 'Unable to change password.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="change-password-page">
      <section className="change-password-card">
        <p className="change-password-eyebrow">ACCOUNT SECURITY</p>
        <h1>Choose a new password</h1>
        <p className="change-password-description">
          Your school provided a temporary password. Set a personal password to continue.
        </p>
        <form onSubmit={handleSubmit}>
          <label>
            Current password
            <input
              name="current_password"
              type="password"
              value={form.current_password}
              onChange={updateField}
              required
              disabled={loading}
            />
          </label>
          <label>
            New password
            <input
              name="new_password"
              type="password"
              minLength="8"
              value={form.new_password}
              onChange={updateField}
              required
              disabled={loading}
            />
          </label>
          <label>
            Confirm new password
            <input
              name="confirm_password"
              type="password"
              minLength="8"
              value={form.confirm_password}
              onChange={updateField}
              required
              disabled={loading}
            />
          </label>
          {error && <p className="change-password-error" role="alert">{error}</p>}
          <button type="submit" disabled={loading}>
            {loading ? 'Saving...' : 'Save password'}
          </button>
        </form>
      </section>
    </div>
  )
}

export default ChangePassword
