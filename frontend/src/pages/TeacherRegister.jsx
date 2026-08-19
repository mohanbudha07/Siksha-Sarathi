import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'

function TeacherRegister() {
  const navigate = useNavigate()

  const [form, setForm] = useState({
    username: '',
    email: '',
    password: '',
    confirm_password: '',
  })

  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleChange = (event) => {
    setForm({
      ...form,
      [event.target.name]: event.target.value,
    })
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError('')

    if (form.password !== form.confirm_password) {
      setError('Passwords do not match.')
      return
    }

    setLoading(true)

    try {
      await api.post('/register', {
        username: form.username,
        email: form.email,
        password: form.password,
        role: 'teacher',
      })

      navigate('/login')
    } catch (error) {
      setError(
        error.response?.data?.error ||
          'Registration failed. Please try again.'
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <h1>Teacher Registration</h1>

      <form onSubmit={handleSubmit}>
        <input
          name="username"
          placeholder="Username"
          value={form.username}
          onChange={handleChange}
          required
        />

        <input
          name="email"
          type="email"
          placeholder="Email"
          value={form.email}
          onChange={handleChange}
          required
        />

        <input
          name="password"
          type="password"
          placeholder="Password"
          value={form.password}
          onChange={handleChange}
          required
        />

        <input
          name="confirm_password"
          type="password"
          placeholder="Confirm Password"
          value={form.confirm_password}
          onChange={handleChange}
          required
        />

        {error && <p>{error}</p>}

        <button type="submit" disabled={loading}>
          {loading ? 'Creating Account...' : 'Create Teacher Account'}
        </button>
      </form>

      <p>
        Already have an account?{' '}
        <button onClick={() => navigate('/login')}>
          Sign In
        </button>
      </p>
    </div>
  )
}

export default TeacherRegister
