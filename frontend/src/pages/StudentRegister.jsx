import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'

function StudentRegister() {
  const navigate = useNavigate()

  const [form, setForm] = useState({
    username: '',
    full_name: '',
    email: '',
    grade: '',
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
        full_name: form.full_name,
        email: form.email,
        grade: form.grade,
        password: form.password,
        role: 'student',
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
      <h1>Student Registration</h1>

      <form onSubmit={handleSubmit}>
        <input
          name="full_name"
          placeholder="Full Name"
          value={form.full_name}
          onChange={handleChange}
          required
        />

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
          name="grade"
          placeholder="Grade"
          value={form.grade}
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
          {loading ? 'Creating Account...' : 'Create Student Account'}
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

export default StudentRegister
