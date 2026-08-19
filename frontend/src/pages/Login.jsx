import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'
import './Login.css'

function Login() {
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
      const response = await api.post('/login', {
  email,
  password,
})

const role = response.data.user.role

if (role === 'teacher') {
  navigate('/teacher/dashboard')
} else if (role === 'student') {
  navigate('/student/dashboard')
} else if (role === 'admin') {
  navigate('/admin/dashboard')
} else {
  setError('Unknown user role.')
}
    } catch (error) {
      console.error(error)

      setError(
        error.response?.data?.error ||
          'Login failed. Please check your email and password.'
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">

      <div className="login-container">

        <div className="login-brand">
          <div className="brand-icon">🎓</div>

          <h1>Siksha Sarathi</h1>

          <p>
            Your smart companion for better learning
          </p>
        </div>

        <div className="login-card">

          <div className="login-heading">
            <h2>Welcome Back</h2>
            <p>Sign in to continue your learning journey.</p>
          </div>

          <form onSubmit={handleSubmit}>

            <div className="input-group">
              <label htmlFor="email">
                Email Address
              </label>

              <input
                id="email"
                type="email"
                placeholder="Enter your email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </div>

            <div className="input-group">
              <label htmlFor="password">
                Password
              </label>

              <input
                id="password"
                type="password"
                placeholder="Enter your password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </div>

            {error && (
              <div className="login-error">
                ⚠️ {error}
              </div>
            )}

            <button
              type="submit"
              className="login-button"
              disabled={loading}
            >
              {loading ? (
                <>
                  <span className="login-spinner" />
                  Signing in...
                </>
              ) : (
                'Sign In →'
              )}
            </button>

          </form>
           <div className="register-links">
  <p>Don't have an account?</p>

  <div className="register-buttons">
    <button
      type="button"
      onClick={() => navigate('/student/register')}
    >
      👨‍🎓 Register as Student
    </button>

    <button
      type="button"
      onClick={() => navigate('/teacher/register')}
    >
      👨‍🏫 Register as Teacher
    </button>
  </div>
</div>

          <div className="login-footer">
            <span>📚</span>
            <p>
              Learn smarter. Track progress. Improve continuously.
            </p>
          </div>

        </div>

        <p className="login-copyright">
          © 2026 Siksha Sarathi
        </p>

      </div>

    </div>
  )
}

export default Login
