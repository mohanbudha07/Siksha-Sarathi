import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import api from '../api'
import './Login.css'
import '../styles/AuthExperience.css'

function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState('student')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const navigate = useNavigate()
  const location = useLocation()

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError('')
    setLoading(true)

    try {
      const response = await api.post('/login', {
        email,
        password,
        role,
      })

      const user = response.data.user

      if (user.must_change_password) {
        navigate('/change-password', { replace: true })
      } else if (user.role === 'teacher') {
        navigate('/teacher/dashboard', { replace: true })
      } else if (user.role === 'student') {
        navigate('/student/dashboard', { replace: true })
      } else {
        setError('Unknown user role.')
      }
    } catch (requestError) {
      setError(
        requestError.response?.data?.error ||
          'Login failed. Please check your email and password.'
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-layout">
        <aside className="login-intro-panel">
          <Link className="auth-brand" to="/">
            <span className="auth-brand-mark">SS</span>
            <span><strong>Siksha Sarathi</strong><small>Academic Platform</small></span>
          </Link>
          <div className="login-intro-copy">
            <p className="auth-eyebrow">LEARNING, CONNECTED</p>
            <h1>Make every class count.</h1>
            <p>Coursework, school communication, and learning progress in one secure workspace.</p>
          </div>
          <Link className="auth-home-link" to="/">← Back to the institution site</Link>
        </aside>

        <div className="login-card">
          <div className="login-heading">
            <p className="auth-eyebrow">STUDENT &amp; TEACHER PORTAL</p>
            <h2>Sign in</h2>
            <p>Use the account issued by your school.</p>
          </div>

          <form onSubmit={handleSubmit}>
            <div className="input-group">
              <label htmlFor="email">Email address</label>
              <input
                id="email"
                type="email"
                autoComplete="username"
                placeholder="name@school.edu"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </div>

            <fieldset className="login-role-group">
              <legend>Continue as</legend>
              <div className="login-role-options">
                {[['student', 'Student'], ['teacher', 'Teacher']].map(([value, label]) => (
                  <label className={role === value ? 'is-selected' : ''} key={value}>
                    <input
                      type="radio"
                      name="role"
                      value={value}
                      checked={role === value}
                      onChange={() => setRole(value)}
                    />
                    <span>{label}</span>
                  </label>
                ))}
              </div>
            </fieldset>

            <div className="input-group">
              <label htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                placeholder="Enter your password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </div>

            {error && (
              <div className="login-error" role="alert">{error}</div>
            )}
            {location.state?.notice && !error && (
              <div className="login-success" role="status">✓ {location.state.notice}</div>
            )}

            <button
              type="submit"
              className="login-button"
              disabled={loading}
            >
              {loading ? (
                <><span className="login-spinner" />Signing in...</>
              ) : (
                'Sign in'
              )}
            </button>
          </form>
          <p className="login-security-note">Your role and account access are verified securely.</p>
        </div>
      </div>
    </div>
  )
}

export default Login
